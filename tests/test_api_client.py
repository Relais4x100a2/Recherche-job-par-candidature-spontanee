import collections
import os

# Ensure the path is set up correctly
import sys
import time
import unittest
from unittest.mock import MagicMock, call, patch
import concurrent.futures # Import for as_completed

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import api_client  # Module to test
import config  # For constants


class TestApiClient(unittest.TestCase):
    def setUp(self):
        # Reset global rate limiting structures for each test
        api_client.request_timestamps.clear()
        # If rate_limit_lock needs specific handling, do it here,
        # but usually, it's fine as long as tests don't run in parallel threads
        # within the same test method without re-acquiring/releasing.

        # It's good practice to patch constants if they might affect test behavior
        # and you want to control them, e.g., MAX_CODES_PER_API_CALL
        self.original_max_codes = api_client.MAX_CODES_PER_API_CALL
        api_client.MAX_CODES_PER_API_CALL = 2  # Smaller for easier batch testing

    def tearDown(self):
        api_client.request_timestamps.clear()
        api_client.MAX_CODES_PER_API_CALL = self.original_max_codes

    @patch("api_client.requests.get")
    def test_fetch_first_page_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [{"siren": "123"}],
            "total_pages": 2,
            "total_results": 50,
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = api_client.fetch_first_page(
            "http://fakeapi.com/search", {"param": "value"}, {}
        )

        expected_params = {"param": "value", "page": 1}
        mock_get.assert_called_once_with(
            "http://fakeapi.com/search", params=expected_params, headers={}, timeout=30
        )
        self.assertTrue(result["success"])
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["total_pages"], 2)
        self.assertEqual(result["total_results"], 50)
        self.assertIsNone(result["error_message"])

    @patch("api_client.requests.get")
    def test_fetch_first_page_timeout(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Timeout error")
        result = api_client.fetch_first_page("http://fakeapi.com/search", {}, {})
        self.assertFalse(result["success"])
        self.assertEqual(
            result["error_message"],
            "Délai d'attente dépassé lors de la connexion à l'API (page 1).",
        )

    @patch("api_client.requests.get")
    def test_fetch_first_page_http_error_with_json_message(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.reason = "Bad Request"
        mock_response.json.return_value = {"message": "Invalid parameter"}
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        mock_get.return_value = mock_response

        result = api_client.fetch_first_page("http://fakeapi.com/search", {}, {})
        self.assertFalse(result["success"])
        self.assertEqual(
            result["error_message"],
            "Erreur API (page 1): 400 Bad Request - Invalid parameter",
        )

    @patch("api_client.requests.get")
    def test_fetch_first_page_http_error_no_json_message(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.reason = "Server Error"
        mock_response.text = "<html><body>Server Error</body></html>"
        # Make response.json() raise an error to simulate non-JSON error content
        mock_response.json.side_effect = requests.exceptions.JSONDecodeError(
            "Error", "doc", 0
        )
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        mock_get.return_value = mock_response

        result = api_client.fetch_first_page("http://fakeapi.com/search", {}, {})
        self.assertFalse(result["success"])
        expected_error_prefix = "Erreur API (page 1): 500 Server Error"
        expected_error_suffix = "\nContenu brut (premiers 200 caractères): <html><body>Server Error</body></html>..."
        self.assertTrue(result["error_message"].startswith(expected_error_prefix))
        self.assertTrue(result["error_message"].endswith(expected_error_suffix))

    @patch("api_client.requests.get")
    def test_fetch_first_page_request_exception(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection failed")
        result = api_client.fetch_first_page("http://fakeapi.com/search", {}, {})
        self.assertFalse(result["success"])
        self.assertEqual(
            result["error_message"], "Erreur réseau (page 1): Connection failed"
        )

    @patch("api_client.time.sleep")  # Mock sleep to speed up tests
    @patch("api_client.requests.get")
    def test_fetch_page_with_retry_success_first_try(self, mock_get, mock_sleep):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [{"id": 1}]}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = api_client.fetch_page_with_retry(1, {}, "url", {})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["results"], [{"id": 1}])
        mock_sleep.assert_not_called()

    @patch("api_client.time.sleep")
    @patch("api_client.requests.get")
    def test_fetch_page_with_retry_handles_429(self, mock_get, mock_sleep):
        # Simulate 429 then success
        mock_response_429 = MagicMock(spec=requests.Response)
        mock_response_429.status_code = 429
        mock_response_429.headers = {}
        mock_response_429.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response_429
        )

        mock_response_success = MagicMock(spec=requests.Response)
        mock_response_success.json.return_value = {"results": [{"id": 1}]}
        mock_response_success.raise_for_status = MagicMock()

        mock_get.side_effect = [mock_response_429, mock_response_success]

        result = api_client.fetch_page_with_retry(1, {}, "url", {})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["results"], [{"id": 1}])
        mock_sleep.assert_called_once()  # Should have slept after 429

    @patch("api_client.time.sleep")
    @patch("api_client.requests.get")
    def test_fetch_page_with_retry_max_retries_429(self, mock_get, mock_sleep):
        mock_response_429 = MagicMock(spec=requests.Response)
        mock_response_429.status_code = 429
        mock_response_429.headers = {}
        mock_response_429.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response_429
        )

        # Make it fail MAX_RETRIES_ON_429 + 1 times
        mock_get.side_effect = [mock_response_429] * (config.MAX_RETRIES_ON_429 + 1)

        result = api_client.fetch_page_with_retry(1, {}, "url", {})
        self.assertEqual(result["status"], "error")
        self.assertTrue("Échec final après" in result["message"])
        self.assertEqual(mock_sleep.call_count, config.MAX_RETRIES_ON_429)

    # --- Tests for rechercher_entreprises_par_localisation_et_criteres ---
    # These will be higher-level, mocking out the actual API calls.

    @patch("api_client.st")  # Mock all streamlit calls
    @patch("api_client.fetch_first_page")
    @patch(
        "api_client.concurrent.futures.ThreadPoolExecutor"
    )  # To avoid actual threading
    def test_rechercher_empty_localisation_codes(
        self, mock_executor, mock_fetch_first, mock_st_glob
    ):
        result = api_client.rechercher_entreprises_par_localisation_et_criteres(
            [], {"activite_principale": "123"}, False, "commune"
        )
        self.assertEqual(result, [])
        mock_st_glob.warning.assert_called_once()
        mock_fetch_first.assert_not_called()

    @patch("api_client.st")
    @patch("api_client.fetch_first_page")
    @patch("api_client.concurrent.futures.ThreadPoolExecutor")
    def test_rechercher_success_single_batch_page1_only(
        self, mock_executor, mock_fetch_first, mock_st_glob
    ):
        mock_fetch_first.return_value = {
            "success": True,
            "results": [
                {"siren": "123", "matching_etablissements": [{"siret": "1230001"}]}
            ],
            "total_pages": 1,
            "total_results": 1,
            "error_message": None,
        }

        result = api_client.rechercher_entreprises_par_localisation_et_criteres(
            ["75001"], {"activite_principale": "XYZ"}, False, "commune"
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["siren"], "123")
        mock_fetch_first.assert_called_once()
        mock_executor.assert_not_called()  # No thread pool for 1 page

    @patch("api_client.st")
    @patch("api_client.fetch_first_page")
    @patch("api_client.concurrent.futures.ThreadPoolExecutor")
    def test_rechercher_success_single_batch_multiple_pages(
        self, MockThreadPoolExecutor, mock_fetch_first, mock_st_glob    
    ):
        mock_fetch_first.return_value = {
            "success": True,
            "results": [
                {"siren": "111", "matching_etablissements": [{"siret": "1110001"}]}
            ],
            "total_pages": 2,
            "total_results": 2,
            "error_message": None,
        }

        # This is what each call to the local fetcher (via future.result()) should return
        mock_page2_data = {
            "status": "success",
            "message": "",
            "results": [
                {"siren": "222", "matching_etablissements": [{"siret": "2220001"}]}
            ],
        }
        
        mock_executor_instance = MockThreadPoolExecutor.return_value.__enter__.return_value
        
        # Mock the future object that submit would return
        mock_future_page2 = MagicMock()
        mock_future_page2.result.return_value = mock_page2_data
        
        # Make executor.submit return our mock future
        # This assumes only one other page (page 2) is fetched in this scenario.
        # If more pages were fetched, submit would be called multiple times.
        mock_executor_instance.submit.return_value = mock_future_page2

        # To correctly mock as_completed, we need to ensure it yields the futures
        # that executor.submit created.
        # We also need to patch concurrent.futures.as_completed itself.
        with patch('api_client.concurrent.futures.as_completed', return_value=[mock_future_page2]) as mock_as_completed:
            # The future_to_page_batch mapping in the SUT will map mock_future_page2 to page number 2.

            result = api_client.rechercher_entreprises_par_localisation_et_criteres(
                ["75001"], {"activite_principale": "XYZ"}, False, "commune"
            )

        self.assertEqual(len(result), 2)  # siren 111 from page 1, siren 222 from page 2
        sirens = {r["siren"] for r in result}
        self.assertIn("111", sirens)
        self.assertIn("222", sirens)
        mock_fetch_first.assert_called_once()
        mock_executor_instance.submit.assert_called_once() # Check that a task was submitted
        # Check that the arguments to submit were for page 2
        args_submitted, _ = mock_executor_instance.submit.call_args
        self.assertEqual(args_submitted[1], 2) # page_num_local should be 2

    @patch("api_client.st")
    @patch("api_client.fetch_first_page")
    def test_rechercher_needs_confirmation(self, mock_fetch_first, mock_st_glob):
        mock_fetch_first.return_value = {
            "success": True,
            "results": [{"siren": "123"}],
            "total_pages": config.API_MAX_PAGES + 5,  # Exceeds max pages
            "total_results": (config.API_MAX_PAGES + 5) * 25,
            "error_message": None,
        }

        result = api_client.rechercher_entreprises_par_localisation_et_criteres(
            ["75001"], {"activite_principale": "XYZ"}, False, "commune"
        )
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status_code"], "NEEDS_USER_CONFIRMATION_OR_BREAKDOWN")
        self.assertEqual(len(result["page1_results"]), 1)

    @patch("api_client.st")
    @patch("api_client.fetch_first_page")
    def test_rechercher_deduplication_and_merge(self, mock_fetch_first, mock_st_glob):
        # Simulate two batches, each returning data for the same SIREN but different etablissements
        # Batch 1 (code1)
        results_batch1 = [
            {
                "siren": "111",
                "nom_complet": "Company A",
                "matching_etablissements": [{"siret": "1110001", "adresse": "Addr 1"}],
            },
            {
                "siren": "222",
                "nom_complet": "Company B",
                "matching_etablissements": [{"siret": "2220001", "adresse": "Addr B1"}],
            },
        ]
        # Batch 2 (code2)
        results_batch2 = [
            {
                "siren": "111",
                "nom_complet": "Company A",
                "matching_etablissements": [{"siret": "1110002", "adresse": "Addr 2"}],
            },  # Same SIREN, new etab
            {
                "siren": "333",
                "nom_complet": "Company C",
                "matching_etablissements": [{"siret": "3330001", "adresse": "Addr C1"}],
            },
        ]

        mock_fetch_first.side_effect = [
            {
                "success": True,
                "results": results_batch1,
                "total_pages": 1,
                "total_results": len(results_batch1),
            },
            {
                "success": True,
                "results": results_batch2,
                "total_pages": 1,
                "total_results": len(results_batch2),
            },
        ]

        # api_client.MAX_CODES_PER_API_CALL is 2 (from setUp).
        list_localisation_codes = ["code_b1_1", "code_b1_2", "code_b2_1"] # Creates 2 batches

        result = api_client.rechercher_entreprises_par_localisation_et_criteres(
            list_localisation_codes, {"activite_principale": "XYZ"}, False, "commune"
        )

        self.assertEqual(len(result), 3)  # 3 unique SIRENs: 111, 222, 333

        siren_111_data = next(item for item in result if item["siren"] == "111")
        self.assertEqual(
            len(siren_111_data["matching_etablissements"]), 2
        )  # Etabs merged
        etab_sirets_111 = {
            e["siret"] for e in siren_111_data["matching_etablissements"]
        }
        self.assertIn("1110001", etab_sirets_111)
        self.assertIn("1110002", etab_sirets_111)

        siren_222_data = next(item for item in result if item["siren"] == "222")
        self.assertEqual(len(siren_222_data["matching_etablissements"]), 1)
        self.assertEqual(
            siren_222_data["matching_etablissements"][0]["siret"], "2220001"
        )

        siren_333_data = next(item for item in result if item["siren"] == "333")
        self.assertEqual(len(siren_333_data["matching_etablissements"]), 1)
        self.assertEqual(
            siren_333_data["matching_etablissements"][0]["siret"], "3330001"
        )

    @patch("api_client.st")
    @patch("api_client.fetch_first_page")
    def test_rechercher_first_page_fail_initial_search(
        self, mock_fetch_first, mock_st_glob
    ):
        mock_fetch_first.return_value = {
            "success": False,
            "error_message": "Critical API error on page 1",
            "results": [],
            "total_pages": 0,
            "total_results": 0,
        }

        result = api_client.rechercher_entreprises_par_localisation_et_criteres(
            ["75001"],
            {"activite_principale": "XYZ"},
            force_full_fetch=False,
            code_type="commune",
        )
        self.assertIsNone(
            result
        )  # Indicates critical failure on first batch of initial search
        # Error message should be handled by st.status within the function, or st.error
        # We can check if st.error was called if we mock it specifically on mock_st_glob
        # For now, assume the function's internal st.status handles it.


if __name__ == "__main__":
    unittest.main()

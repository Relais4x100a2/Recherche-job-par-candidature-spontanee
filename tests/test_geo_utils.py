import json
import os

# Ensure the path is set up correctly to import modules from the parent directory
# This might be necessary if you run tests directly from the tests/ directory
import sys
import unittest
from unittest.mock import MagicMock, mock_open, patch

import requests
from geopy.exc import GeocoderServiceError, GeocoderTimedOut

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # Import config for constants like COMMUNES_CACHE_FILE
import geo_utils  # Import the module to be tested


# No class-level patch for streamlit.cache_data, will handle in test method.
class TestGeoUtils(unittest.TestCase):
    def setUp(self):
        # Reset the cache file path for testing to avoid interfering with actual cache
        self.test_cache_file = "test_communes_cache.json"
        geo_utils.COMMUNES_CACHE_FILE = self.test_cache_file

    def tearDown(self):
        # Clean up the test cache file if it was created
        if os.path.exists(self.test_cache_file):
            os.remove(self.test_cache_file)
        # Restore original cache file path if necessary, though it's modified globally in setUp
        # For robust testing, consider patching the constant within each test method
        # or using a context manager if geo_utils.COMMUNES_CACHE_FILE is imported elsewhere.

    @patch("geo_utils.st")  # Mock streamlit
    @patch("geo_utils.BANFrance")
    def test_geocoder_ban_france_success(self, mock_ban_france, mock_st):
        mock_geolocator = MagicMock()
        mock_location = MagicMock()
        mock_location.latitude = 48.8566
        mock_location.longitude = 2.3522
        mock_location.address = "Paris, France"
        mock_geolocator.geocode.return_value = mock_location
        mock_ban_france.return_value = mock_geolocator

        result = geo_utils.geocoder_ban_france("Paris")
        self.assertEqual(result, (48.8566, 2.3522))
        mock_st.success.assert_called_once()

    @patch("geo_utils.st")
    @patch("geo_utils.BANFrance")
    def test_geocoder_ban_france_not_found(self, mock_ban_france, mock_st):
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.return_value = None
        mock_ban_france.return_value = mock_geolocator

        result = geo_utils.geocoder_ban_france("NonExistentPlace123")
        self.assertIsNone(result)
        mock_st.error.assert_called_with(
            "Impossible de trouver les coordonnées pour l'adresse : 'NonExistentPlace123'. Vérifiez l'adresse et réessayez."
        )

    @patch("geo_utils.st")
    @patch("geo_utils.BANFrance")
    def test_geocoder_ban_france_timeout(self, mock_ban_france, mock_st):
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.side_effect = GeocoderTimedOut("Timeout")
        mock_ban_france.return_value = mock_geolocator

        result = geo_utils.geocoder_ban_france("Paris")
        self.assertIsNone(result)
        mock_st.error.assert_called_with(
            "Le service de géocodage (BAN France) a mis trop de temps à répondre. Réessayez plus tard."
        )

    @patch("geo_utils.st")
    @patch("geo_utils.BANFrance")
    def test_geocoder_ban_france_service_error(self, mock_ban_france, mock_st):
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.side_effect = GeocoderServiceError("Service Error")
        mock_ban_france.return_value = mock_geolocator

        result = geo_utils.geocoder_ban_france("Paris")
        self.assertIsNone(result)
        mock_st.error.assert_called_with(
            "Erreur du service de géocodage (BAN France) : Service Error"
        )

    @patch("geo_utils.st")
    def test_geocoder_ban_france_empty_address(self, mock_st):
        result = geo_utils.geocoder_ban_france("")
        self.assertIsNone(result)
        mock_st.error.assert_called_with("L'adresse ne peut pas être vide.")

    @patch("geo_utils.st")
    @patch("geo_utils.os.path.exists", return_value=False)  # Cache does not exist
    @patch("geo_utils.os.makedirs")
    @patch("geo_utils.requests.get")
    @patch("builtins.open", new_callable=mock_open)
    def test_download_all_communes_success(
        self, mock_file_open, mock_requests_get, mock_makedirs, mock_os_exists, mock_st
    ):
        mock_response = MagicMock()
        mock_response.json.return_value = [{"code": "75056", "nom": "Paris"}]
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response

        # Patch os.path.dirname to return a non-empty directory for the makedirs check
        with patch("geo_utils.os.path.dirname", return_value="some_cache_dir"):
            result = geo_utils._download_all_communes()

        self.assertEqual(result, [{"code": "75056", "nom": "Paris"}])
        mock_requests_get.assert_called_once_with(
            "https://geo.api.gouv.fr/communes?fields=code,codesPostaux,nom,type,centre,mairie",
            timeout=60,
        )
        mock_file_open.assert_called_once_with(
            self.test_cache_file, "w", encoding="utf-8"
        )
        # Check if os.makedirs was called if the cache_dir didn't exist
        # In this setup, os.path.exists for the directory is implicitly true unless also patched.
        # If dirname returns a non-empty string, and os.path.exists(that_dir) is false, makedirs is called.
        mock_makedirs.assert_called_once_with("some_cache_dir", exist_ok=True)
        mock_st.success.assert_called_once()

    @patch("geo_utils.st")
    @patch("geo_utils.requests.get")
    def test_download_all_communes_timeout(self, mock_requests_get, mock_st):
        mock_requests_get.side_effect = requests.exceptions.Timeout
        result = geo_utils._download_all_communes()
        self.assertIsNone(result)
        mock_st.error.assert_called_with(
            "Timeout lors du téléchargement des données des communes. Veuillez réessayer."
        )

    @patch("geo_utils.st")
    @patch("geo_utils.os.path.exists", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='[{"code": "75056", "nom": "Paris"}]',
    )
    def test_load_communes_from_cache_success(
        self, mock_file_open, mock_os_exists, mock_st
    ):
        result = geo_utils._load_communes_from_cache()
        self.assertEqual(result, [{"code": "75056", "nom": "Paris"}])
        mock_file_open.assert_called_once_with(
            self.test_cache_file, "r", encoding="utf-8"
        )

    @patch("geo_utils.st")
    @patch("geo_utils.os.path.exists", return_value=False)
    def test_load_communes_from_cache_not_exists(self, mock_os_exists, mock_st):
        result = geo_utils._load_communes_from_cache()
        self.assertIsNone(result)

    @patch("geo_utils.st")
    @patch("geo_utils.os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=mock_open, read_data="invalid json")
    def test_load_communes_from_cache_corrupted(
        self, mock_file_open, mock_os_exists, mock_st
    ):
        result = geo_utils._load_communes_from_cache()
        self.assertIsNone(result)
        mock_st.warning.assert_called_once()

    def test_add_commune_if_point_in_radius(self):
        target_point = (48.8566, 2.3522)  # Paris
        radius_km = 10

        # Case 1: Point data is valid and within radius
        point_data_within = {
            "type": "Point",
            "coordinates": [2.3522, 48.8566],
        }  # lon, lat
        with patch("geo_utils.geodesic") as mock_geodesic:
            mock_geodesic.return_value.km = 5  # distance < radius
            is_in, malformed, geo_err = geo_utils._add_commune_if_point_in_radius(
                point_data_within, target_point, radius_km
            )
            self.assertTrue(is_in)
            self.assertEqual(malformed, 0)
            self.assertEqual(geo_err, 0)
            mock_geodesic.assert_called_with(target_point, (48.8566, 2.3522))

        # Case 2: Point data is valid but outside radius
        point_data_outside = {"type": "Point", "coordinates": [2.4000, 48.9000]}
        with patch("geo_utils.geodesic") as mock_geodesic:
            mock_geodesic.return_value.km = 15  # distance > radius
            is_in, malformed, geo_err = geo_utils._add_commune_if_point_in_radius(
                point_data_outside, target_point, radius_km
            )
            self.assertFalse(is_in)
            self.assertEqual(malformed, 0)
            self.assertEqual(geo_err, 0)

        # Case 3: Malformed point data (coordinates not a list of 2)
        point_data_malformed1 = {"type": "Point", "coordinates": [2.3522]}
        is_in, malformed, geo_err = geo_utils._add_commune_if_point_in_radius(
            point_data_malformed1, target_point, radius_km
        )
        self.assertFalse(is_in)
        self.assertEqual(malformed, 1)
        self.assertEqual(geo_err, 0)

        # Case 4: Malformed point data (not a dict)
        point_data_malformed2 = None
        is_in, malformed, geo_err = geo_utils._add_commune_if_point_in_radius(
            point_data_malformed2, target_point, radius_km
        )
        self.assertFalse(is_in)
        self.assertEqual(malformed, 0)  # No increment because it returns early
        self.assertEqual(geo_err, 0)

        # Case 5: Geodesic error
        point_data_geo_error = {"type": "Point", "coordinates": [2.3522, 48.8566]}
        with patch("geo_utils.geodesic") as mock_geodesic:
            mock_geodesic.side_effect = ValueError("Geodesic error")
            is_in, malformed, geo_err = geo_utils._add_commune_if_point_in_radius(
                point_data_geo_error, target_point, radius_km
            )
            self.assertFalse(is_in)
            self.assertEqual(malformed, 0)
            self.assertEqual(geo_err, 1)

    @patch("geo_utils._load_communes_from_cache")
    @patch("geo_utils._download_all_communes")
    @patch("geo_utils._add_commune_if_point_in_radius")  # Mock the helper
    @patch("geo_utils.st")
    def test_get_communes_in_radius_cached_logic(
        self, mock_st, mock_add_commune, mock_download, mock_load_cache
    ):
        # Attempt to get the unwrapped function to bypass the @st.cache_data decorator
        try:
            unwrapped_get_communes_func = geo_utils.get_communes_in_radius_cached.__wrapped__
        except AttributeError:
            self.fail(
                "geo_utils.get_communes_in_radius_cached does not have __wrapped__ attribute. "
                "Cannot disable cache for this test. Ensure Streamlit's cache decorator is used in a way that preserves __wrapped__."
            )

        # Patch the original function name to point to the unwrapped version for this test's scope
        with patch('geo_utils.get_communes_in_radius_cached', new=unwrapped_get_communes_func):
            # --- Test Data ---
            sample_communes_data = [
                {
                    "code": "75001",
                    "nom": "Paris 1er",
                    "codesPostaux": ["75001"],
                    "centre": {"type": "Point", "coordinates": [2.34, 48.86]},
                    "mairie": None,
                },
                {
                    "code": "92000",
                    "nom": "Nanterre",
                    "codesPostaux": ["92000"],
                    "centre": {"type": "Point", "coordinates": [2.20, 48.89]}, # Outside typical test radius
                    "mairie": None,
                },
                {
                    "code": "93000",
                    "nom": "Bobigny",
                    "codesPostaux": ["93000", "93001"],
                    "centre": {"type": "Point", "coordinates": [2.44, 48.91]},
                    "mairie": None,
                },
            ]

            # --- Mock Configurations ---
            mock_load_cache.side_effect = [
                sample_communes_data,  # Scenario 1: Cache hit (but cache is disabled by 'new' patch)
                None,                  # Scenario 2: Cache miss
                None                   # Scenario 3: Cache miss
            ]

            def side_effect_add_commune(point_data, target_point, radius_km_val):
                if point_data and point_data["coordinates"] == [2.34, 48.86]:  # Paris 1er
                    return True, 0, 0
                if point_data and point_data["coordinates"] == [2.44, 48.91]:  # Bobigny
                    return True, 0, 0
                return False, 0, 0
            mock_add_commune.side_effect = side_effect_add_commune

            # Scenario 1: Cache hit (effectively, as _load_communes_from_cache returns data)
            # The call to geo_utils.get_communes_in_radius_cached will use the unwrapped_get_communes_func
            result1 = geo_utils.get_communes_in_radius_cached(48.85, 2.35, 5.0)
            self.assertListEqual(sorted(result1), sorted(["75001", "93000", "93001"]))
            mock_download.assert_not_called() # Download should not be called

            # Scenario 2: Cache miss, download success
            mock_download.reset_mock() 
            mock_download.return_value = sample_communes_data
            
            result2 = geo_utils.get_communes_in_radius_cached(48.85, 2.35, 5.0)
            self.assertListEqual(sorted(result2), sorted(["75001", "93000", "93001"]))
            mock_download.assert_called_once() # Download should be called once

            # Scenario 3: Download fails
            mock_download.reset_mock() 
            mock_st.error.reset_mock() 
            mock_download.return_value = None  # Simulate download failure
            
            result3 = geo_utils.get_communes_in_radius_cached(48.85, 2.35, 5.0)
            self.assertEqual(result3, [])
            mock_download.assert_called_once() # Download is attempted
            mock_st.error.assert_called_with(
                "Impossible de récupérer les données des communes. La recherche ne peut continuer."
            )


if __name__ == "__main__":
    unittest.main()

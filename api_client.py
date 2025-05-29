import requests
import streamlit as st
import concurrent.futures
import threading
import time
import collections
import datetime as dt

import config

# --- Ressources partagées pour le Rate Limiting (spécifiques à ce client API) ---
request_timestamps = collections.deque()
rate_limit_lock = threading.Lock()

# Constant for batching codes (commune or postal) per API call
MAX_CODES_PER_API_CALL = 5 # Adjustable, API doc says "liste de valeurs séparées par des virgules"

# --- Fonctions API ---
def fetch_first_page(url, params, headers):
    """Récupère la première page de résultats de l'API."""
    # Ensure 'page' parameter is set to 1 for the first page request.
    params_page1 = params.copy()
    params_page1['page'] = 1
    # print(f"{dt.datetime.now()} - DEBUG - Fetching first page. URL: {url}, Params: {params_page1}")
    try:
        response = requests.get(url, params=params_page1, headers=headers, timeout=30)
        # print(f"{dt.datetime.now()} - DEBUG - First page response status code: {response.status_code}")
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        results_count = len(data.get('results', []))
        total_pages = data.get('total_pages', 1)
        total_results = data.get('total_results', results_count)
        # print(f"{dt.datetime.now()} - DEBUG - First page fetch successful. Results: {results_count}, Total Pages: {total_pages}, Total Results: {total_results}")
        return {
            # Standardized response structure for API calls.
            # 'success': boolean indicating if the call was successful.
            # 'results': list of results from the API.
            # 'total_pages': total number of pages available.
            # 'total_results': total number of results available.
            # 'error_message': string containing error details if success is False.
            "success": True,
            "results": data.get('results', []),
            "total_pages": total_pages,
            "total_results": total_results,
            "error_message": None
        }
    except requests.exceptions.Timeout as e:
        error_msg = "Délai d'attente dépassé lors de la connexion à l'API (page 1)."
        # print(f"{dt.datetime.now()} - ERROR - First page fetch error: {error_msg} - {e}")
        return {"success": False, "error_message": error_msg}
    except requests.exceptions.HTTPError as e:
        error_message = f"Erreur API (page 1): {e.response.status_code} {e.response.reason}"
        try:
            # Attempt to parse more detailed error message from JSON response
            error_content = e.response.json()
            if isinstance(error_content, dict) and 'message' in error_content:
                error_message += f" - {error_content['message']}"
            else:
                 error_message += f"\nContenu brut (premiers 200 caractères): {e.response.text[:200]}..."
        except Exception:
             error_message += f"\nContenu brut (premiers 200 caractères): {e.response.text[:200]}..."
        # print(f"{dt.datetime.now()} - ERROR - First page fetch HTTPError: {error_message}")
        return {"success": False, "error_message": error_message}
    except requests.exceptions.RequestException as e:
        error_msg = f"Erreur réseau (page 1): {e}"
        # print(f"{dt.datetime.now()} - ERROR - First page fetch RequestException: {error_msg}")
        return {"success": False, "error_message": error_msg}

def rechercher_entreprises_par_localisation_et_criteres(list_localisation_codes, api_params_from_app, force_full_fetch=False, code_type="commune"):
    """
    Recherche les entreprises via l'API /search en utilisant les codes de localisation (communes ou postaux) et autres critères.
    Itère sur les codes de localisation par lots.
    Args:
        list_localisation_codes (list[str]): Liste des codes INSEE des communes ou des codes postaux.
        api_params_from_app (dict): Dictionnaire contenant les paramètres de l'API depuis l'application,
                                    devrait inclure 'activite_principale' ou 'section_activite_principale',
                                    et 'tranche_effectif_salarie'.
        force_full_fetch (bool): Si True, tente de récupérer toutes les pages jusqu'à config.API_MAX_PAGES
                                 pour chaque lot de codes. Si False et que le premier lot est trop grand,
                                 retourne un statut spécial.
        code_type (str): Type de code fourni dans list_localisation_codes. "commune" ou "postal".
    Returns:
        list or dict: Liste d'objets "entreprise" si succès, ou un dictionnaire avec status_code
                      "NEEDS_USER_CONFIRMATION_OR_BREAKDOWN" si la recherche initiale est trop large.
    """
    # print(f"{dt.datetime.now()} - DEBUG - rechercher_entreprises_par_localisation_et_criteres called with {len(list_localisation_codes)} {code_type} codes, api_params_from_app={api_params_from_app}, force_full_fetch={force_full_fetch}")
    url = f"{config.API_BASE_URL}/search" # CHANGED endpoint
    
    # Base parameters from app (NAF, effectifs)
    # api_params_from_app should contain:
    # - 'activite_principale' or 'section_activite_principale'
    # - 'tranche_effectif_salarie' (comma-separated string of codes)
    
    base_api_params_for_search = api_params_from_app.copy() 
    base_api_params_for_search.update({
        'per_page': 25,
        'minimal': 'true',
        'include': 'matching_etablissements,finances',
        'limite_matching_etablissements': 100 
    })
    headers = {'accept': 'application/json'}
    
    all_entreprises_global = [] # Stores "entreprise" objects from all successful calls
    # all_processed_sirets_global = set() # To deduplicate establishments across all calls - not used here, deduplication happens on entreprise objects by SIREN later

    # Clear the request timestamps deque only for a new, non-forced search operation.
    # For breakdown calls (force_full_fetch=True), app.py should manage clearing it once before the batch.
    if not force_full_fetch:
        with rate_limit_lock:
            request_timestamps.clear()
            # print(f"{dt.datetime.now()} - DEBUG - Request timestamps deque cleared for new search.")

    if not list_localisation_codes:
        st.warning(f"Aucun code de localisation ({code_type}) fourni pour la recherche.")
        return []

    localisation_code_batches = [
        list_localisation_codes[i:i + MAX_CODES_PER_API_CALL]
        for i in range(0, len(list_localisation_codes), MAX_CODES_PER_API_CALL)
    ]
    total_batches = len(localisation_code_batches)

    progress_bar = st.progress(0)
    status_text_global = st.empty() # For global status updates
    status_text_global.text(f"Initialisation de la recherche sur {len(list_localisation_codes)} codes {code_type} ({total_batches} lots)...")

    api_code_param_key = "code_commune" if code_type == "commune" else "code_postal"

    for batch_idx, code_batch in enumerate(localisation_code_batches):
        current_codes_str = ",".join(code_batch)
        status_text_global.text(f"Lot {batch_idx + 1}/{total_batches}: Codes {code_type} {current_codes_str[:50]}...")

        params_for_current_batch = base_api_params_for_search.copy()
        params_for_current_batch[api_code_param_key] = current_codes_str

        # This st.status is for the current batch of codes
        batch_status_message = f"Recherche pour codes {code_type}: {current_codes_str[:30]}..."
        with st.status(batch_status_message, expanded=(total_batches == 1)) as status_batch: # Expand if only one batch
            # === Étape 1: Récupérer la première page pour CE LOT DE CODES ===
            status_batch.update(label=f"Lot {batch_idx+1}, Page 1: Récupération...")
            page1_result_batch = fetch_first_page(url, params_for_current_batch, headers)

            if not page1_result_batch["success"]:
                error_msg_batch = f"Lot {batch_idx+1} (Codes {code_type}: {current_codes_str[:30]}...): Erreur page 1 - {page1_result_batch['error_message']}"
                status_batch.update(label=error_msg_batch, state="error")
                # st.error(error_msg_batch) # Also show as main error
                progress_bar.progress((batch_idx + 1) / total_batches)
                # If the first batch fails for a non-forced fetch, we might want to stop and report.
                # For forced fetch (breakdown), we continue to try other batches.
                if batch_idx == 0 and not force_full_fetch:
                    return None # Indicates critical failure on first batch of initial search
                continue # Try next batch if this isn't the first batch of an initial search

            results_page1_batch = page1_result_batch['results']
            total_pages_batch = page1_result_batch['total_pages']
            total_results_batch = page1_result_batch['total_results']
            
            status_batch.update(label=f"Lot {batch_idx+1}, Page 1: {len(results_page1_batch)} résultats. Total estimé pour lot: {total_results_batch} sur {total_pages_batch} pages.")

            if not results_page1_batch and total_results_batch == 0:
                status_batch.update(label=f"Lot {batch_idx+1}: Aucun résultat.", state="complete")
                progress_bar.progress((batch_idx + 1) / total_batches)
                continue
            
            all_entreprises_global.extend(results_page1_batch)

            # Handle "NEEDS_USER_CONFIRMATION_OR_BREAKDOWN"
            # Trigger if *any batch* of an *initial (non-forced)* call is too large.
            if not force_full_fetch and total_pages_batch >= config.API_MAX_PAGES:
                status_batch.update(label=f"Lot {batch_idx+1}: Recherche trop large ({total_results_batch} résultats). Suggestion d'affinage.", state="complete")
                status_text_global.empty() # Clear global text
                progress_bar.empty()
                return {
                    "status_code": "NEEDS_USER_CONFIRMATION_OR_BREAKDOWN",
                    "page1_results": results_page1_batch,
                    "total_pages_estimated": total_pages_batch,
                    "total_results_estimated": total_results_batch,
                    "original_query_params": params_for_current_batch.copy()
                }

            pages_to_target_for_fetching_batch = min(total_pages_batch, config.API_MAX_PAGES)

            if pages_to_target_for_fetching_batch >= 2:
                pages_a_recuperer_batch = list(range(2, pages_to_target_for_fetching_batch + 1))
                total_pages_to_process_batch = len(pages_a_recuperer_batch)
                status_batch.update(label=f"Lot {batch_idx+1}: Récupération parallèle des pages 2 à {pages_to_target_for_fetching_batch}...")
                
                # Local fetch_page_with_retry for this batch's context
                def fetch_page_with_retry_local(page_num_local, current_batch_params_local, batch_identifier_str):
                    params_page_local = current_batch_params_local.copy()
                    params_page_local['page'] = page_num_local
                    current_retry_delay_local = config.INITIAL_RETRY_DELAY
                    for attempt_local in range(config.MAX_RETRIES_ON_429 + 1):
                        try:
                            with rate_limit_lock:
                                now = time.time()
                                while request_timestamps and request_timestamps[0] <= now - 1.0:
                                    request_timestamps.popleft()
                                if len(request_timestamps) >= config.MAX_REQUESTS_PER_SECOND:
                                    time_since_oldest_in_window = now - request_timestamps[0]
                                    wait_time = 1.0 - time_since_oldest_in_window + config.MIN_DELAY_BETWEEN_REQUESTS
                                    if wait_time > 0: time.sleep(wait_time)
                                request_timestamps.append(time.time())

                            response_local = requests.get(url, params=params_page_local, headers=headers, timeout=20)
                            response_local.raise_for_status()
                            data_local = response_local.json()
                            return {"status": "success", "message": "", "results": data_local.get('results', [])}
                        except requests.exceptions.HTTPError as e_local:
                            if e_local.response.status_code == 429:
                                if attempt_local >= config.MAX_RETRIES_ON_429:
                                    return {"status": "error", "message": f"Page {page_num_local} ({batch_identifier_str}): Échec final 429", "results": []}
                                # Simplified retry logic for brevity, use original logic from global fetch_page_with_retry
                                retry_after_header = e_local.response.headers.get("Retry-After")
                                wait_duration = current_retry_delay_local
                                if retry_after_header:
                                    try: wait_duration = float(retry_after_header)
                                    except ValueError: pass # Could parse HTTP-date here
                                time.sleep(max(wait_duration, current_retry_delay_local) + 0.1)
                                current_retry_delay_local *= 1.5 # Less aggressive backoff
                                continue
                            else:
                                return {"status": "error", "message": f"Page {page_num_local} ({batch_identifier_str}): Erreur HTTP {e_local.response.status_code}", "results": []}
                        except requests.exceptions.Timeout:
                            if attempt_local >= config.MAX_RETRIES_ON_429:
                                return {"status": "error", "message": f"Page {page_num_local} ({batch_identifier_str}): Timeout final", "results": []}
                            time.sleep(current_retry_delay_local)
                            current_retry_delay_local *= 2
                            continue
                        except requests.exceptions.RequestException as e_local:
                            return {"status": "error", "message": f"Page {page_num_local} ({batch_identifier_str}): Erreur réseau {e_local}", "results": []}
                    return {"status": "error", "message": f"Page {page_num_local} ({batch_identifier_str}): Échec inattendu après toutes les tentatives.", "results": []}

                results_paralleles_batch = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=config.MAX_REQUESTS_PER_SECOND) as executor: # Max workers tied to rate limit
                    batch_id_for_msg = f"Lot {batch_idx+1}"
                    future_to_page_batch = {
                        executor.submit(fetch_page_with_retry_local, page, params_for_current_batch, batch_id_for_msg): page 
                        for page in pages_a_recuperer_batch
                    }
                    processed_pages_count_batch = 0
                    for future_batch in concurrent.futures.as_completed(future_to_page_batch):
                        page_num_batch = future_to_page_batch[future_batch]
                        processed_pages_count_batch += 1
                        try:
                            result_data_batch = future_batch.result()
                            if result_data_batch["status"] == "success":
                                if result_data_batch["results"]:
                                    results_paralleles_batch.extend(result_data_batch["results"])
                                status_batch.update(label=f"Lot {batch_idx+1}: {processed_pages_count_batch}/{total_pages_to_process_batch} pages traitées (Page {page_num_batch} OK).")
                            elif result_data_batch["status"] == "error":
                                st.error(result_data_batch['message']) # Show error for specific page
                                status_batch.update(label=f"Lot {batch_idx+1}: {processed_pages_count_batch}/{total_pages_to_process_batch} pages (Erreur page {page_num_batch}).")
                        except Exception as exc_batch:
                            st.error(f'Lot {batch_idx+1}, Page {page_num_batch} a généré une exception: {exc_batch}')
                            status_batch.update(label=f"Lot {batch_idx+1}: {processed_pages_count_batch}/{total_pages_to_process_batch} pages (Exception page {page_num_batch}).")
                
                all_entreprises_global.extend(results_paralleles_batch)
            status_batch.update(label=f"Lot {batch_idx+1} terminé. {total_results_batch if total_results_batch else 0} résultats estimés, {pages_to_target_for_fetching_batch} pages ciblées.", state="complete")
        progress_bar.progress((batch_idx + 1) / total_batches)

    status_text_global.text(f"Recherche terminée sur {len(list_localisation_codes)} codes {code_type}. Traitement des {len(all_entreprises_global)} résultats bruts...")
    progress_bar.empty()

    # Deduplicate 'entreprise' objects by SIREN, merging 'matching_etablissements'
    unique_entreprises_by_siren = {}
    for entreprise_obj in all_entreprises_global:
        siren = entreprise_obj.get("siren")
        if siren:
            if siren not in unique_entreprises_by_siren:
                # Ensure matching_etablissements is a list, even if None or empty initially
                entreprise_obj["matching_etablissements"] = entreprise_obj.get("matching_etablissements") or []
                unique_entreprises_by_siren[siren] = entreprise_obj
            else:
                # Merge matching_etablissements
                existing_etabs_sirets = {
                    etab.get("siret") for etab in unique_entreprises_by_siren[siren].get("matching_etablissements", []) if etab.get("siret")
                }
                new_etabs_to_add = [
                    new_etab for new_etab in entreprise_obj.get("matching_etablissements", [])
                    if new_etab.get("siret") and new_etab.get("siret") not in existing_etabs_sirets
                ]
                if new_etabs_to_add:
                    unique_entreprises_by_siren[siren]["matching_etablissements"].extend(new_etabs_to_add)
        else: # No SIREN, add it using a unique key if it's truly an "entreprise" object without SIREN
             # This case should be rare for valid data.
            unique_key_no_siren = f"no_siren_{len(unique_entreprises_by_siren)}"
            unique_entreprises_by_siren[unique_key_no_siren] = entreprise_obj

    deduplicated_entreprise_list = list(unique_entreprises_by_siren.values())
    # print(f"{dt.datetime.now()} - INFO - Deduplicated 'entreprise' items by SIREN: {len(deduplicated_entreprise_list)}")
    status_text_global.text(f"Traitement final de {len(deduplicated_entreprise_list)} entreprises uniques (par SIREN).")
    
    return deduplicated_entreprise_list


# The global fetch_page_with_retry is kept for reference or if needed by other parts,
# but the new main search function uses a localized version for clarity with batch parameters.
def fetch_page_with_retry(page_num, base_params_for_retry, url_for_retry, headers_for_retry):
            """
            Fetches a single page from the API with retry logic for 429 (Too Many Requests) and timeouts.
            Implements rate limiting using a shared deque of timestamps.
            Args:
                page_num (int): The page number to fetch.
                base_params_for_retry (dict): Base parameters for the API call (excluding 'page').
                url_for_retry (str): The API endpoint URL.
                headers_for_retry (dict): Headers for the API call.
            """
            # print(f"{dt.datetime.now()} - DEBUG - [Page {page_num}] Starting fetch.")
            params_page = base_params_for_retry.copy()
            params_page['page'] = page_num
            current_retry_delay = config.INITIAL_RETRY_DELAY
            for attempt in range(config.MAX_RETRIES_ON_429 + 1):
                # print(f"{dt.datetime.now()} - DEBUG - [Page {page_num}] Attempt {attempt + 1}/{config.MAX_RETRIES_ON_429 + 1}.")
                try:
                    # --- Rate Limiting Logic ---
                    # Uses a thread-safe lock and a deque to track request timestamps.
                    # Ensures that the number of requests per second does not exceed MAX_REQUESTS_PER_SECOND.
                    with rate_limit_lock:
                        now = time.time()
                        # Remove timestamps older than 1 second from the window
                        while request_timestamps and request_timestamps[0] <= now - 1.0:
                            request_timestamps.popleft()
                        if len(request_timestamps) >= config.MAX_REQUESTS_PER_SECOND:
                            time_since_oldest_in_window = now - request_timestamps[0]
                            wait_time = 1.0 - time_since_oldest_in_window + config.MIN_DELAY_BETWEEN_REQUESTS
                            if wait_time > 0:
                                # print(f"{dt.datetime.now()} - DEBUG - [Page {page_num}] Rate limiting: sleeping for {wait_time:.2f}s.")
                                time.sleep(wait_time)
                        request_timestamps.append(time.time())

                    # --- API Call ---
                    response = requests.get(url_for_retry, params=params_page, headers=headers_for_retry, timeout=20)
                    # print(f"{dt.datetime.now()} - DEBUG - [Page {page_num}] Response status code: {response.status_code}")
                    response.raise_for_status()
                    data = response.json()
                    # print(f"{dt.datetime.now()} - DEBUG - [Page {page_num}] Fetch successful. Results: {len(data.get('results', []))}")
                    return {"status": "success", "message": "", "results": data.get('results', [])}

                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 429:
                        if attempt >= config.MAX_RETRIES_ON_429:
                            error_msg = f"Page {page_num}: Échec final après {config.MAX_RETRIES_ON_429 + 1} tentatives (429 Too Many Requests)."
                            # print(f"{dt.datetime.now()} - ERROR - [Page {page_num}] {error_msg}")
                            return {"status": "error", "message": error_msg, "results": []}
                        retry_after_header = e.response.headers.get("Retry-After")
                        wait_duration = current_retry_delay
                        header_used = False
                        if retry_after_header:
                            try: wait_duration = float(retry_after_header); header_used = True
                            except ValueError:
                                # Attempt to parse HTTP-date format for Retry-After
                                try:
                                    retry_date = dt.datetime.strptime(retry_after_header, '%a, %d %b %Y %H:%M:%S GMT').replace(tzinfo=dt.timezone.utc)
                                    now_utc = dt.datetime.now(dt.timezone.utc)
                                    wait_duration = (retry_date - now_utc).total_seconds()
                                    if wait_duration < 0: wait_duration = 0
                                    header_used = True
                                except ValueError: pass
                        wait_duration = max(wait_duration + 0.1, current_retry_delay if not header_used else 0)
                        # print(f"{dt.datetime.now()} - WARNING - [Page {page_num}] HTTP 429 (Too Many Requests). Attempt {attempt + 1}. Waiting {wait_duration:.2f}s. Header used: {header_used}")
                        time.sleep(wait_duration)
                        current_retry_delay *= 2 # Exponential backoff for subsequent retries
                        continue
                    else:
                        error_msg = f"Page {page_num}: Erreur HTTP {e.response.status_code}: {e}"
                        # print(f"{dt.datetime.now()} - ERROR - [Page {page_num}] {error_msg}")
                        return {"status": "error", "message": error_msg, "results": []}
                except requests.exceptions.Timeout:
                    if attempt >= config.MAX_RETRIES_ON_429:
                         error_msg = f"Page {page_num}: Échec final après {config.MAX_RETRIES_ON_429 + 1} tentatives (Timeout)."
                         # print(f"{dt.datetime.now()} - ERROR - [Page {page_num}] {error_msg}")
                         return {"status": "error", "message": error_msg, "results": []}
                    # print(f"{dt.datetime.now()} - WARNING - [Page {page_num}] Timeout. Attempt {attempt + 1}. Waiting {current_retry_delay:.2f}s.")
                    time.sleep(current_retry_delay)
                    current_retry_delay *= 2
                    continue
                except requests.exceptions.RequestException as e:
                    error_msg = f"Page {page_num}: Erreur réseau/requête: {e}"
                    # print(f"{dt.datetime.now()} - ERROR - [Page {page_num}] {error_msg}")
                    return {"status": "error", "message": error_msg, "results": []}
            error_msg_final = f"Page {page_num}: Échec inattendu après toutes les tentatives."
            # print(f"{dt.datetime.now()} - ERROR - [Page {page_num}] {error_msg_final}")
            return {"status": "error", "message": error_msg_final, "results": []}

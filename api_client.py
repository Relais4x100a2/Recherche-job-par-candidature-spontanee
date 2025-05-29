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

def rechercher_geographiquement_entreprises(lat, long, radius, api_params_from_app, force_full_fetch=False):
    """
    Recherche les entreprises via l'API en utilisant les paramètres fournis.
    Parallélise les appels après la première page, respecte le rate limit et gère les erreurs 429.
    Si la recherche initiale est trop large (atteint config.API_MAX_PAGES) et force_full_fetch est False,
    retourne un statut spécial pour que l'application principale gère la suite (ex: proposer un affinage ou une recherche décomposée).
    Si force_full_fetch est True, tente de récupérer toutes les pages jusqu'à config.API_MAX_PAGES.
    """
    # print(f"{dt.datetime.now()} - DEBUG - rechercher_geographiquement_entreprises called with lat={lat}, long={long}, radius={radius}, api_params_from_app={api_params_from_app}, force_full_fetch={force_full_fetch}")
    url = f"{config.API_BASE_URL}/near_point"
    base_params = api_params_from_app.copy() # NAF params etc. from app
    base_params.update({
        'lat': lat,
        'long': long,
        'radius': radius,
        'per_page': 25,
        'minimal': 'true', # Added: Request minimal response
        'include': 'matching_etablissements,finances', # Added: Include specific data
        'limite_matching_etablissements': 100 # Added: Limit matching establishments

    })
    headers = {'accept': 'application/json'}
    entreprises_detaillees = []
    total_pages = 1
    total_results = 0

    # Clear the request timestamps deque only for a new, non-forced search operation.
    # For breakdown calls (force_full_fetch=True), app.py should manage clearing it once before the batch.
    if not force_full_fetch:
        with rate_limit_lock:
            request_timestamps.clear()
            # print(f"{dt.datetime.now()} - DEBUG - Request timestamps deque cleared for new search.")

    initial_status_message = f"Initialisation de la recherche d'entreprises autour de ({lat:.4f}, {long:.4f})..."
    with st.status(initial_status_message, expanded=True) as status:

        # === Étape 1: Récupérer la première page ===
        status.update(label="Récupération de la première page...")
        # print(f"{dt.datetime.now()} - DEBUG - Starting fetch for page 1.")
        start_time_page1 = time.time()
        page1_result = fetch_first_page(url, base_params, headers)

        if not page1_result["success"]:
            # print(f"{dt.datetime.now()} - ERROR - Failed to fetch page 1: {page1_result['error_message']}")
            status.update(label=f"Erreur lors de la récupération de la première page: {page1_result['error_message']}", state="error")
            return None # Critical failure, cannot proceed.

        results_page1 = page1_result['results']
        total_pages = page1_result['total_pages']
        total_results = page1_result['total_results']

        if not results_page1 and total_results == 0:
             # print(f"{dt.datetime.now()} - INFO - No results found on page 1 and total_results is 0.")
             status.update(label=f"Aucun résultat trouvé pour les critères spécifiés.", state="complete")
             return []

        # results_page1 are added to entreprises_detaillees below, only if not returning early.
        elapsed_time_page1 = time.time() - start_time_page1
        # print(f"{dt.datetime.now()} - DEBUG - Page 1 fetch completed in {elapsed_time_page1:.2f}s. Results: {len(results_page1)}, Est. Total Pages: {total_pages}, Est. Total Results: {total_results}")
        st.write(f"Page 1 ({len(results_page1)} rés.) récupérée en {elapsed_time_page1:.2f}s. Total pages estimé: {total_pages}, Total résultats API: {total_results}")

        # If the query is too large (hits API page limit), return to app.py to handle.
        # This applies if force_full_fetch is False (initial query)
        # OR if force_full_fetch is True but the (sub)query is still too large (e.g., a whole NAF section).
        if total_pages >= config.API_MAX_PAGES: # Removed 'and not force_full_fetch'
            status.update(label=f"Estimation: {total_results} résultats sur {total_pages} pages. Options de recherche affinées vont être proposées.", state="complete")
            # The actual st.warning message will be shown by app.py
            return {
                "status_code": "NEEDS_USER_CONFIRMATION_OR_BREAKDOWN",
                "page1_results": results_page1,
                "total_pages_estimated": total_pages,
                "total_results_estimated": total_results,
                "original_query_params": base_params.copy() # Full params used for page 1
            }

        # Proceed with fetching all pages if:
        # 1. The query is not "too large" (total_pages < config.API_MAX_PAGES)
        # 2. Or, force_full_fetch is True (even if total_pages >= config.API_MAX_PAGES)
        entreprises_detaillees.extend(results_page1)

        # Determine the actual number of pages to fetch, respecting API limits
        pages_to_target_for_fetching_actually = min(total_pages, config.API_MAX_PAGES)

        # === Étape 2: Vérifier si d'autres pages sont nécessaires ===
        if pages_to_target_for_fetching_actually < 2:
            status.update(label=f"Recherche terminée. {len(entreprises_detaillees)} entreprises trouvées ({pages_to_target_for_fetching_actually} page).", state="complete")
            return entreprises_detaillees

        # === Étape 3: Préparer et exécuter les appels parallèles (pages 2 à N) ===
        pages_a_recuperer = list(range(2, pages_to_target_for_fetching_actually + 1))
        total_pages_to_process = len(pages_a_recuperer)
        # print(f"{dt.datetime.now()} - DEBUG - Starting parallel fetch for {total_pages_to_process} pages (from 2 to {pages_to_target_for_fetching_actually}).")
        status.update(label=f"Récupération parallèle des pages 2 à {pages_to_target_for_fetching_actually} ({total_pages_to_process} pages sur {total_pages} estimées)...")
        start_time_parallel = time.time()

        def fetch_page_with_retry(page_num):
            """
            Fetches a single page from the API with retry logic for 429 (Too Many Requests) and timeouts.
            Implements rate limiting using a shared deque of timestamps.
            """
            # print(f"{dt.datetime.now()} - DEBUG - [Page {page_num}] Starting fetch.")
            params_page = base_params.copy()
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
                    response = requests.get(url, params=params_page, headers=headers, timeout=20)
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


        results_paralleles = []
        max_workers = 10
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_page = {executor.submit(fetch_page_with_retry, page): page for page in pages_a_recuperer}
            # Keep track of processed pages for progress updates.
            processed_pages = 0

            for future in concurrent.futures.as_completed(future_to_page):
                page_num = future_to_page[future]
                processed_pages += 1
                try:
                    result_data = future.result()
                    if result_data["status"] == "success":
                        if result_data["results"]:
                            results_paralleles.extend(result_data["results"])
                            # print(f"{dt.datetime.now()} - DEBUG - [Page {page_num}] Success. Added {len(result_data['results'])} results. Processed: {processed_pages}/{total_pages_to_process}.")
                            status.update(label=f"Récupération parallèle... {processed_pages}/{total_pages_to_process} pages traitées (Page {page_num} OK).")
                        else:
                            # print(f"{dt.datetime.now()} - DEBUG - [Page {page_num}] Success but no results. Processed: {processed_pages}/{total_pages_to_process}.")
                            status.update(label=f"Récupération parallèle... {processed_pages}/{total_pages_to_process} pages traitées (Page {page_num} vide).")
                    elif result_data["status"] == "error":
                         # print(f"{dt.datetime.now()} - ERROR - [Page {page_num}] Failed: {result_data['message']}. Processed: {processed_pages}/{total_pages_to_process}.")
                         st.error(result_data['message'])
                         status.update(label=f"Récupération parallèle... {processed_pages}/{total_pages_to_process} pages traitées (Erreur page {page_num}).")

                except Exception as exc:
                    # print(f"{dt.datetime.now()} - CRITICAL - [Page {page_num}] Unexpected exception in future.result(): {exc}. Processed: {processed_pages}/{total_pages_to_process}.")
                    st.error(f'La tâche pour la page {page_num} a généré une exception inattendue: {exc}')
                    status.update(label=f"Récupération parallèle... {processed_pages}/{total_pages_to_process} pages traitées (Exception page {page_num}).")


        elapsed_time_parallel = time.time() - start_time_parallel
        # print(f"{dt.datetime.now()} - DEBUG - Parallel fetching completed in {elapsed_time_parallel:.2f}s. Processed {processed_pages}/{total_pages_to_process} pages.")
        st.write(f"{total_pages_to_process} pages à traiter ({processed_pages} effectivement traitées) en parallèle (limité à {config.MAX_REQUESTS_PER_SECOND}/s) en {elapsed_time_parallel:.2f}s.")

        # === Étape 4: Combiner tous les résultats ===
        entreprises_detaillees.extend(results_paralleles)

        # Final status message, accounting for potential discrepancies.
        final_count = len(entreprises_detaillees)
        # print(f"{dt.datetime.now()} - INFO - Total entreprises retrieved: {final_count}. API reported total: {total_results}.")
        
        final_message = f"Recherche terminée. {final_count} entreprises récupérées."

        if total_pages > pages_to_target_for_fetching_actually: # We capped the fetching
            final_message += (
                f" L'API estimait {total_results} résultats sur {total_pages} pages. "
                f"La récupération a été limitée à {pages_to_target_for_fetching_actually} pages "
                f"(jusqu'à {config.API_MAX_TOTAL_RESULTS} résultats)."
            )
            status.update(label=f"⚠️ {final_message}", state="complete")
        elif total_results > final_count and pages_to_target_for_fetching_actually > 1 : # Fetched all targeted pages, but got less than API's initial estimate
            discrepancy = total_results - final_count # Calculate potential missing results
            final_message += (
                f" (L'API annonçait {total_results} résultats au total. "
                f"{discrepancy} résultat(s) manquant(s) par rapport à l'estimation)."
            )
            status.update(label=f"⚠️ {final_message}", state="complete")
        else:
            pages_display_text = f"sur {pages_to_target_for_fetching_actually} page{'s' if pages_to_target_for_fetching_actually > 1 else ''}"
            final_message += f" {pages_display_text}."
            status.update(label=final_message, state="complete")

    return entreprises_detaillees

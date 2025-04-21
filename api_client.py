import requests
import streamlit as st
import concurrent.futures
import threading
import time
import collections
from datetime import datetime, timezone

# Importer la configuration et les utils
import config

# --- Ressources partagées pour le Rate Limiting (spécifiques à ce client API) ---
request_timestamps = collections.deque()
rate_limit_lock = threading.Lock()

# --- Fonctions API ---
def fetch_first_page(url, params, headers):
    """Récupère la première page de résultats de l'API."""
    params_page1 = params.copy()
    params_page1['page'] = 1
    try:
        response = requests.get(url, params=params_page1, headers=headers, timeout=30)
        response.raise_for_status() # Lève une exception pour les codes 4xx/5xx
        data = response.json()
        return {
            "success": True,
            "results": data.get('results', []),
            "total_pages": data.get('total_pages', 1),
            "total_results": data.get('total_results', len(data.get('results', []))),
            "error_message": None
        }
    except requests.exceptions.Timeout:
        return {"success": False, "error_message": "Délai d'attente dépassé lors de la connexion à l'API (page 1)."}
    except requests.exceptions.HTTPError as e:
        error_message = f"Erreur API (page 1): {e.response.status_code} {e.response.reason}"
        try:
            error_content = e.response.json()
            if isinstance(error_content, dict) and 'message' in error_content:
                error_message += f" - {error_content['message']}"
            else:
                 error_message += f"\nContenu brut: {e.response.text[:200]}..."
        except Exception:
             error_message += f"\nContenu brut: {e.response.text[:200]}..."
        return {"success": False, "error_message": error_message}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error_message": f"Erreur réseau (page 1): {e}"}

def rechercher_geographiquement_entreprises(lat, long, radius, api_params):
    """
    Recherche les entreprises via l'API en utilisant les paramètres fournis.
    Parallélise les appels après la première page, respecte le rate limit et gère les erreurs 429.
    """
    url = f"{config.API_BASE_URL}/near_point" # Utiliser config
    base_params = api_params.copy()
    base_params.update({
        'lat': lat,
        'long': long,
        'radius': radius,
        'per_page': 25,
    })
    headers = {'accept': 'application/json'}
    entreprises_detaillees = []
    total_pages = 1
    total_results = 0

    # Vider la deque au début de chaque recherche
    with rate_limit_lock:
        request_timestamps.clear()

    search_type = "codes NAF spécifiques" # Toujours le cas maintenant
    initial_status_message = f"Initialisation de la recherche ({search_type}) autour de ({lat:.4f}, {long:.4f})..."
    with st.status(initial_status_message, expanded=True) as status:

        # === Étape 1: Récupérer la première page ===
        status.update(label="Récupération de la première page...")
        start_time_page1 = time.time()
        page1_result = fetch_first_page(url, base_params, headers) # Utilise la fonction locale

        if not page1_result["success"]:
            status.update(label=f"Erreur lors de la récupération de la première page: {page1_result['error_message']}", state="error")
            return None # Échec critique

        results_page1 = page1_result['results']
        total_pages = page1_result['total_pages']
        total_results = page1_result['total_results']

        if not results_page1 and total_results == 0:
             status.update(label=f"Aucun résultat trouvé pour les critères spécifiés.", state="complete")
             return []

        entreprises_detaillees.extend(results_page1)
        elapsed_time_page1 = time.time() - start_time_page1
        st.write(f"Page 1 ({len(results_page1)} rés.) récupérée en {elapsed_time_page1:.2f}s. Total pages estimé: {total_pages}, Total résultats API: {total_results}")

        # === Étape 2: Vérifier si d'autres pages sont nécessaires ===
        if total_pages < 2:
            status.update(label=f"Recherche terminée. {len(entreprises_detaillees)} entreprises trouvées ({total_pages} page).", state="complete")
            return entreprises_detaillees

        # === Étape 3: Préparer et exécuter les appels parallèles (pages 2 à N) ===
        pages_a_recuperer = list(range(2, total_pages + 1))
        total_pages_to_process = len(pages_a_recuperer)
        status.update(label=f"Récupération parallèle limitée des pages 2 à {total_pages} ({total_pages_to_process} pages)...")
        start_time_parallel = time.time()

        # Fonction interne fetch_page_with_retry
        def fetch_page_with_retry(page_num):
            params_page = base_params.copy()
            params_page['page'] = page_num
            current_retry_delay = config.INITIAL_RETRY_DELAY # Utiliser config
            for attempt in range(config.MAX_RETRIES_ON_429 + 1): # Utiliser config
                try:
                    # Rate Limiting
                    with rate_limit_lock:
                        now = time.time()
                        while request_timestamps and request_timestamps[0] <= now - 1.0:
                            request_timestamps.popleft()
                        if len(request_timestamps) >= config.MAX_REQUESTS_PER_SECOND: # Utiliser config
                            time_since_oldest_in_window = now - request_timestamps[0]
                            wait_time = 1.0 - time_since_oldest_in_window + config.MIN_DELAY_BETWEEN_REQUESTS # Utiliser config
                            if wait_time > 0:
                                time.sleep(wait_time)
                        request_timestamps.append(time.time())

                    # Appel API
                    response = requests.get(url, params=params_page, headers=headers, timeout=20)
                    response.raise_for_status()
                    data = response.json()
                    return {"status": "success", "message": "", "results": data.get('results', [])}

                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 429:
                        if attempt >= config.MAX_RETRIES_ON_429: # Utiliser config
                            error_msg = f"Page {page_num}: Échec final après {config.MAX_RETRIES_ON_429 + 1} tentatives (429 Too Many Requests)."
                            return {"status": "error", "message": error_msg, "results": []}
                        retry_after_header = e.response.headers.get("Retry-After")
                        wait_duration = current_retry_delay
                        header_used = False
                        if retry_after_header:
                            try: wait_duration = float(retry_after_header); header_used = True
                            except ValueError:
                                try:
                                    retry_date = datetime.strptime(retry_after_header, '%a, %d %b %Y %H:%M:%S GMT').replace(tzinfo=timezone.utc)
                                    now_utc = datetime.now(timezone.utc)
                                    wait_duration = (retry_date - now_utc).total_seconds()
                                    if wait_duration < 0: wait_duration = 0
                                    header_used = True
                                except ValueError: pass
                        wait_duration = max(wait_duration + 0.1, current_retry_delay if not header_used else 0)
                        time.sleep(wait_duration)
                        current_retry_delay *= 2
                        continue
                    else:
                        error_msg = f"Page {page_num}: Erreur HTTP {e.response.status_code}: {e}"
                        return {"status": "error", "message": error_msg, "results": []}
                except requests.exceptions.Timeout:
                    if attempt >= config.MAX_RETRIES_ON_429: # Utiliser config
                         error_msg = f"Page {page_num}: Échec final après {config.MAX_RETRIES_ON_429 + 1} tentatives (Timeout)."
                         return {"status": "error", "message": error_msg, "results": []}
                    time.sleep(current_retry_delay)
                    current_retry_delay *= 2
                    continue
                except requests.exceptions.RequestException as e:
                    error_msg = f"Page {page_num}: Erreur réseau/requête: {e}"
                    return {"status": "error", "message": error_msg, "results": []}
            return {"status": "error", "message": f"Page {page_num}: Échec inattendu après toutes les tentatives.", "results": []}


        results_paralleles = []
        max_workers = 10
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_page = {executor.submit(fetch_page_with_retry, page): page for page in pages_a_recuperer}
            processed_pages = 0

            for future in concurrent.futures.as_completed(future_to_page):
                page_num = future_to_page[future]
                processed_pages += 1
                try:
                    result_data = future.result()
                    if result_data["status"] == "success":
                        if result_data["results"]:
                            results_paralleles.extend(result_data["results"])
                            status.update(label=f"Récupération parallèle... {processed_pages}/{total_pages_to_process} pages traitées (Page {page_num} OK).")
                        else:
                            status.update(label=f"Récupération parallèle... {processed_pages}/{total_pages_to_process} pages traitées (Page {page_num} vide).")
                    elif result_data["status"] == "error":
                         st.error(result_data['message'])
                         status.update(label=f"Récupération parallèle... {processed_pages}/{total_pages_to_process} pages traitées (Erreur page {page_num}).")

                except Exception as exc:
                    st.error(f'La tâche pour la page {page_num} a généré une exception inattendue: {exc}')
                    status.update(label=f"Récupération parallèle... {processed_pages}/{total_pages_to_process} pages traitées (Exception page {page_num}).")


        elapsed_time_parallel = time.time() - start_time_parallel
        st.write(f"{total_pages_to_process} pages à traiter ({processed_pages} effectivement traitées) en parallèle (limité à {config.MAX_REQUESTS_PER_SECOND}/s) en {elapsed_time_parallel:.2f}s.")

        # === Étape 4: Combiner tous les résultats ===
        entreprises_detaillees.extend(results_paralleles)

        # Message final
        final_count = len(entreprises_detaillees)
        final_message = f"Recherche terminée. {final_count} entreprises récupérées."
        expected_results_approx = len(results_page1) + len(results_paralleles)
        if total_results > expected_results_approx and total_pages > 1:
             final_message += f" (L'API annonçait {total_results} résultats. {total_results - expected_results_approx} manquant(s), possiblement dû à des erreurs)."
             status.update(label=f"⚠️ {final_message}", state="complete") # Garder state="complete", ajouter emoji au label
        else:
             total_pages_display = f"sur {total_pages} page{'s' if total_pages > 1 else ''}" if total_pages > 1 else ""
             final_message += f" {total_pages_display}."
             status.update(label=final_message, state="complete") # État correct ici

    return entreprises_detaillees

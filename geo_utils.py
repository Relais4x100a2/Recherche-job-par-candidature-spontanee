import streamlit as st
from geopy.geocoders import BANFrance
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from geopy.distance import geodesic
import datetime
import requests
import json
import os

# Chemin où stocker le fichier cache des communes
COMMUNES_CACHE_FILE = "communes_cache.json"

def geocoder_ban_france(adresse: str):
    """
    Géocode une adresse en utilisant le service BANFrance via geopy.

    Args:
        adresse (str): L'adresse à géocoder.

    Returns:
        tuple: (latitude, longitude) si le géocodage réussit, None sinon.
    """
    # print(f"{datetime.datetime.now()} - DEBUG - geocoder_ban_france called with address: '{adresse}'")
    if not adresse:
        # print(f"{datetime.datetime.now()} - WARNING - Address is empty or None.")
        st.error("L'adresse ne peut pas être vide.")
        return None

    # Initialize the geolocator with a specific user agent.
    geolocator = BANFrance(user_agent="streamlit_app_recherche_entreprises/1.0")

    try:
        with st.spinner(f"Géocodage de l'adresse '{adresse}'..."):
            # Attempt to geocode the address with a specified timeout.
            location = geolocator.geocode(adresse, exactly_one=True, timeout=15)

        if location:
            # print(f"{datetime.datetime.now()} - INFO - Location found for '{adresse}': {location.address} | Lat: {location.latitude}, Lon: {location.longitude}")
            st.success(f"Adresse trouvée : {location.address} - Coordonnées utilisées : Latitude={location.latitude:.6f}, Longitude={location.longitude:.6f}")
            return location.latitude, location.longitude
        else:
            # print(f"{datetime.datetime.now()} - WARNING - Location not found for address: '{adresse}'")
            st.error(f"Impossible de trouver les coordonnées pour l'adresse : '{adresse}'. Vérifiez l'adresse et réessayez.")
            return None
    except GeocoderTimedOut as e:
        # print(f"{datetime.datetime.now()} - ERROR - GeocoderTimedOut for address '{adresse}': {e}")
        st.error("Le service de géocodage (BAN France) a mis trop de temps à répondre. Réessayez plus tard.")
        return None
    except GeocoderServiceError as e:
        # print(f"{datetime.datetime.now()} - ERROR - GeocoderServiceError for address '{adresse}': {e}")
        st.error(f"Erreur du service de géocodage (BAN France) : {e}")
        return None
    except Exception as e:
        # print(f"{datetime.datetime.now()} - ERROR - Unexpected error during geocoding for address '{adresse}': {e}")
        st.error(f"Erreur inattendue lors du géocodage : {e}")
        return None

def _download_all_communes():
    """Télécharge toutes les communes depuis l'API Géo et les sauvegarde."""
    # print(f"{datetime.datetime.now()} - INFO - Downloading all communes from Géo API...")
    st.info("Téléchargement initial des données des communes françaises... (peut prendre quelques instants la première fois)")
    try:
        response = requests.get("https://geo.api.gouv.fr/communes?fields=code,codesPostaux,nom,type,centre,mairie", timeout=60) # Added timeout
        response.raise_for_status()
        communes_data = response.json()
        # Create cache directory if it doesn't exist
        cache_dir = os.path.dirname(COMMUNES_CACHE_FILE)
        if cache_dir and not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
            
        with open(COMMUNES_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(communes_data, f, ensure_ascii=False, indent=2)
        # print(f"{datetime.datetime.now()} - INFO - Download complete. {len(communes_data)} communes saved to {COMMUNES_CACHE_FILE}.")
        st.success(f"Données de {len(communes_data)} communes téléchargées et mises en cache.")
        return communes_data
    except requests.exceptions.Timeout:
        st.error("Timeout lors du téléchargement des données des communes. Veuillez réessayer.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Erreur lors du téléchargement des communes : {e}")
        return None

def _load_communes_from_cache():
    """Charge les communes depuis le fichier cache local."""
    if os.path.exists(COMMUNES_CACHE_FILE):
        # print(f"{datetime.datetime.now()} - INFO - Loading communes from cache: {COMMUNES_CACHE_FILE}")
        try:
            with open(COMMUNES_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            # print(f"{datetime.datetime.now()} - ERROR - Error decoding communes cache file: {e}. Will attempt to re-download.")
            st.warning(f"Fichier cache des communes corrompu ({e}). Tentative de re-téléchargement.")
            return None # Trigger re-download
        except Exception as e:
            # print(f"{datetime.datetime.now()} - ERROR - Unexpected error loading communes cache: {e}. Will attempt to re-download.")
            st.warning(f"Erreur inattendue lors du chargement du cache des communes ({e}). Tentative de re-téléchargement.")
            return None # Trigger re-download
    return None

def _add_commune_if_point_in_radius(
    point_data: dict | None,
    target_point_tuple: tuple[float, float],
    radius_km_val: float
) -> tuple[bool, int, int]:
    """
    Helper function to check if a GeoJSON Point (centre or mairie) is within a given radius

    Args:
        point_data: The dictionary for the 'centre' or 'mairie' field of a commune.
        target_point_tuple: (latitude, longitude) of the search center.
        radius_km_val: Radius in kilometers.

    Returns:
        A tuple (is_in_radius, malformed_increment, geodesic_error_increment).
        is_in_radius is True if the point is within the radius, False otherwise.
        The increments indicate if errors occurred.
    """
    malformed_count_increment = 0
    geodesic_error_count_increment = 0

    if not isinstance(point_data, dict):
        return False, malformed_count_increment, geodesic_error_count_increment # Point data missing or not a dict

    if point_data.get('type') == 'Point' and 'coordinates' in point_data:
        coords = point_data.get('coordinates')
        if isinstance(coords, list) and len(coords) == 2 and \
           all(isinstance(c, (int, float)) and c is not None for c in coords):
            commune_lon_api, commune_lat_api = coords  # API provides [lon, lat]
            current_commune_point = (commune_lat_api, commune_lon_api)  # geodesic expects (lat, lon)
            try:
                distance = geodesic(target_point_tuple, current_commune_point).km
                if distance <= radius_km_val:
                    return True, malformed_count_increment, geodesic_error_count_increment
            except (ValueError, TypeError): # Errors from geodesic, e.g., non-finite values
                geodesic_error_count_increment = 1
        else: # 'coordinates' key exists but value is not a list of 2 valid numbers
            malformed_count_increment = 1
    elif point_data: # point_data exists and is a dict, but not a valid Point structure
        malformed_count_increment = 1
        
    return False, malformed_count_increment, geodesic_error_count_increment

@st.cache_data(ttl=86400) # Cache the list of commune codes for a day for given lat/lon/radius
def get_communes_in_radius_cached(target_lat: float, target_lon: float, radius_km: float) -> list[str]: # Returns list of POSTAL CODES
    """
    Récupère les codes POSTAUX des communes françaises dans un rayon donné, 
    en utilisant un cache local pour les données de toutes les communes.

    Args:
        target_lat (float): Latitude du point central.
        target_lon (float): Longitude du point central.
        radius_km (float): Rayon de recherche en kilomètres.
    Returns:
        list[str]: Une liste de codes POSTAUX uniques des communes se trouvant dans le rayon.
    """
    communes_data = _load_communes_from_cache()
    if communes_data is None:
        communes_data = _download_all_communes()
        if communes_data is None:
            st.error("Impossible de récupérer les données des communes. La recherche ne peut continuer.")
            return [] # Impossible de récupérer les données

    postal_codes_in_radius_set = set()
    target_point = (target_lat, target_lon)

    # print(f"{datetime.datetime.now()} - DEBUG - Identifying communes and their postal codes within {radius_km}km for {len(communes_data)} communes...")
    with st.spinner(f"Identification des communes et codes postaux dans un rayon de {radius_km} km..."):
        skipped_due_to_malformed_coords = 0
        errors_in_geodesic_calculation = 0

        for commune in communes_data:
            commune_in_radius_flag = False

            # Check 'centre' coordinates
            is_centre_in, malformed_c, geo_err_c = _add_commune_if_point_in_radius(
                commune.get('centre'),
                target_point,
                radius_km
            )
            skipped_due_to_malformed_coords += malformed_c
            errors_in_geodesic_calculation += geo_err_c
            if is_centre_in:
                commune_in_radius_flag = True

            # Check 'mairie' coordinates
            # Only check mairie if centre wasn't already in radius, to avoid double processing for postal codes
            # Or, always check both if you want to be absolutely sure (though it shouldn't matter for postal code collection)
            if not commune_in_radius_flag:
                is_mairie_in, malformed_m, geo_err_m = _add_commune_if_point_in_radius(
                    commune.get('mairie'),
                    target_point,
                    radius_km
                )
                skipped_due_to_malformed_coords += malformed_m
                errors_in_geodesic_calculation += geo_err_m
                if is_mairie_in:
                    commune_in_radius_flag = True
            
            if commune_in_radius_flag:
                current_commune_postal_codes = commune.get('codesPostaux')
                if isinstance(current_commune_postal_codes, list):
                    for cp in current_commune_postal_codes:
                        if isinstance(cp, str) and cp.strip():
                            postal_codes_in_radius_set.add(cp.strip())

    # print(f"{datetime.datetime.now()} - DEBUG - Found {len(postal_codes_in_radius_set)} unique postal codes in radius.")
    # if skipped_due_to_malformed_coords > 0:
    #     print(f"{datetime.datetime.now()} - INFO - Skipped {skipped_due_to_malformed_coords} communes due to malformed coordinate structures.")
    # if errors_in_geodesic_calculation > 0:
    #     print(f"{datetime.datetime.now()} - INFO - Encountered {errors_in_geodesic_calculation} ValueErrors during geodesic distance calculation.")
    return sorted(list(postal_codes_in_radius_set)) # Return sorted unique postal codes

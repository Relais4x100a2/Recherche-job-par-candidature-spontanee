import streamlit as st
from geopy.geocoders import BANFrance
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import datetime

def geocoder_ban_france(adresse):
    """Géocode une adresse en utilisant l'API BANFrance via geopy."""
    print(f"{datetime.datetime.now()} - INFO - geocoder_ban_france called with address: '{adresse}'")
    if not adresse:
        print(f"{datetime.datetime.now()} - WARNING - Address is empty or None.")
        st.error("L'adresse ne peut pas être vide.")
        return None

    print(f"{datetime.datetime.now()} - INFO - Initializing BANFrance geolocator.")
    geolocator = BANFrance(user_agent="streamlit_app_recherche_entreprises/1.0") # Nom d'agent utilisateur simple
    print(f"{datetime.datetime.now()} - INFO - BANFrance geolocator initialized.")

    try:
        with st.spinner(f"Géocodage de l'adresse '{adresse}'..."):
            print(f"{datetime.datetime.now()} - INFO - Calling geolocator.geocode for address: '{adresse}'")
            # Augmenter légèrement le timeout
            location = geolocator.geocode(adresse, exactly_one=True, timeout=15)

        if location:
            print(f"{datetime.datetime.now()} - INFO - Location found for '{adresse}': {location.address} | Lat: {location.latitude}, Lon: {location.longitude}")
            st.success(f"Adresse trouvée : {location.address}")
            st.info(f"Coordonnées utilisées : Latitude={location.latitude:.6f}, Longitude={location.longitude:.6f}")
            return location.latitude, location.longitude
        else:
            print(f"{datetime.datetime.now()} - WARNING - Location not found for address: '{adresse}'")
            st.error(f"Impossible de trouver les coordonnées pour l'adresse : '{adresse}'. Vérifiez l'adresse et réessayez.")
            return None
    except GeocoderTimedOut as e:
        print(f"{datetime.datetime.now()} - ERROR - GeocoderTimedOut for address '{adresse}': {e}")
        st.error("Le service de géocodage (BAN France) a mis trop de temps à répondre. Réessayez plus tard.")
        return None
    except GeocoderServiceError as e:
        print(f"{datetime.datetime.now()} - ERROR - GeocoderServiceError for address '{adresse}': {e}")
        st.error(f"Erreur du service de géocodage (BAN France) : {e}")
        return None
    except Exception as e:
        print(f"{datetime.datetime.now()} - ERROR - Unexpected error during geocoding for address '{adresse}': {e}")
        st.error(f"Erreur inattendue lors du géocodage : {e}")
        return None

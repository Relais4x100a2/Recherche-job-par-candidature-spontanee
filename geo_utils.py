import streamlit as st
from geopy.geocoders import BANFrance
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

def geocoder_ban_france(adresse):
    """Géocode une adresse en utilisant l'API BANFrance via geopy."""
    if not adresse:
        st.error("L'adresse ne peut pas être vide.")
        return None

    geolocator = BANFrance(user_agent="streamlit_app_recherche_entreprises/1.0") # Nom d'agent utilisateur simple

    try:
        with st.spinner(f"Géocodage de l'adresse '{adresse}'..."):
            # Augmenter légèrement le timeout
            location = geolocator.geocode(adresse, exactly_one=True, timeout=15)

        if location:
            st.success(f"Adresse trouvée : {location.address}")
            st.info(f"Coordonnées utilisées : Latitude={location.latitude:.6f}, Longitude={location.longitude:.6f}")
            return location.latitude, location.longitude
        else:
            st.error(f"Impossible de trouver les coordonnées pour l'adresse : '{adresse}'. Vérifiez l'adresse et réessayez.")
            return None
    except GeocoderTimedOut:
        st.error("Le service de géocodage (BAN France) a mis trop de temps à répondre. Réessayez plus tard.")
        return None
    except GeocoderServiceError as e:
        st.error(f"Erreur du service de géocodage (BAN France) : {e}")
        return None
    except Exception as e:
        st.error(f"Erreur inattendue lors du géocodage : {e}")
        return None

import streamlit as st
import requests
import pandas as pd
import datetime
from geopy.geocoders import BANFrance
from geopy.exc import GeocoderTimedOut, GeocoderServiceError 
import pydeck as pdk


# --- CONFIGURATION DE LA PAGE (DOIT ÊTRE LA PREMIÈRE COMMANDE STREAMLIT) ---
st.set_page_config(layout="wide")
# -------------------------------------------------------------------------

# --- Dictionnaires NAF et Effectifs (inchangés) ---
naf_sections = {
    "A": "A - Agriculture, sylviculture et pêche", "B": "B - Industries extractives", "C": "C - Industrie manufacturière",
    "D": "D - Production et distribution d'électricité, gaz, vapeur/eau chaude, air conditionné ", "E": "E - Production et distribution d'eau ; assainissement, gestion des déchets et dépollution",
    "F": "F - Construction", "G": "G - Commerce de gros et de détail ; réparation d'automobiles et de motocycles", "H": "H - Transports et entreposage",
    "I": "I - Hébergement et restauration", "J": "J - Information et communication", "K": "K - Activités financières et d'assurance",
    "L": "L - Activités immobilières", "M": "M - Activités spécialisées, scientifiques et techniques",
    "N": "N - Activités de services administratifs et de soutien aux activités générales des entreprises",
    "Q": "Q - Santé humaine et action sociale", "R": "R - Arts, spectacles et activités récréatives"
    # Note: Sections O, P, S, T, U are less common for typical business searches but exist
}


effectifs_tranches = {
    "NN": "Non employeuse", "00": "0 salarié", "01": "1 ou 2 salariés", "02": "3 à 5 salariés",
    "03": "6 à 9 salariés", "11": "10 à 19 salariés", "12": "20 à 49 salariés", "21": "50 à 99 salariés",
    "22": "100 à 199 salariés", "31": "200 à 249 salariés", "32": "250 à 499 salariés",
    "41": "500 à 999 salariés", "42": "1 000 à 1 999 salariés", "51": "2 000 à 4 999 salariés",
    "52": "5 000 à 9 999 salariés", "53": "10 000 salariés et plus"
}

# --- Mappings pour Pydeck ---

# Mapping des lettres NAF vers des couleurs RGB
naf_color_mapping = {
    "A": [210, 4, 45], "B": [139, 69, 19], "C": [255, 140, 0], "D": [255, 215, 0],
    "E": [173, 255, 47], "F": [255, 105, 180], "G": [0, 191, 255], "H": [70, 130, 180],
    "I": [255, 0, 0], "J": [128, 0, 128], "K": [0, 128, 0], "L": [160, 82, 45],
    "M": [0, 0, 128], "N": [128, 128, 128], "O": [0, 0, 0], "P": [255, 255, 0],
    "Q": [0, 255, 0], "R": [255, 20, 147], "S": [192, 192, 192], "T": [245, 245, 220],
    "U": [112, 128, 144], "N/A": [220, 220, 220]
}

# Mapping des codes d'effectifs vers un rayon en mètres pour Pydeck
size_mapping = {
    "NN": 15, "00": 20, "01": 30, "02": 40, "03": 50, "11": 70, "12": 90,
    "21": 120, "22": 150, "31": 180, "32": 220, "41": 260, "42": 300,
    "51": 350, "52": 400, "53": 450, "N/A": 10
}

# --- Chargement et préparation des données NAF détaillées ---
NAF_FILE_PATH = 'NAF.csv'  # Assurez-vous que ce chemin est correct

@st.cache_data # Met en cache le résultat pour ne pas relire le fichier à chaque interaction
def load_naf_dictionary(file_path):
    """Charge le fichier NAF et retourne un dictionnaire Code -> Libellé."""
    try:
        # Essayez avec ';' puis avec ',' comme séparateur, et spécifiez l'encodage UTF-8
        try:
            # Try UTF-8 first, common encoding
            df_naf = pd.read_csv(file_path, sep=',', dtype={'Code': str}, encoding='utf-8')
            if 'Code' not in df_naf.columns or 'Libellé' not in df_naf.columns:
                 raise ValueError("Colonnes 'Code' ou 'Libellé' manquantes avec sep=';'")
        except (ValueError, pd.errors.ParserError, UnicodeDecodeError):
            try:
                st.warning(f"Échec lecture de {file_path} avec sep=';' et encodage utf-8. Essai avec ','.")
                df_naf = pd.read_csv(file_path, sep=',', dtype={'Code': str}, encoding='utf-8')
                if 'Code' not in df_naf.columns or 'Libellé' not in df_naf.columns:
                    raise ValueError("Colonnes 'Code' ou 'Libellé' manquantes avec sep=','")
            except (ValueError, pd.errors.ParserError, UnicodeDecodeError):
                try:
                     # Fallback to latin-1 if UTF-8 fails
                     st.warning(f"Échec lecture de {file_path} avec sep=',' et encodage utf-8. Essai avec latin-1.")
                     df_naf = pd.read_csv(file_path, sep=';', dtype={'Code': str}, encoding='latin-1')
                     if 'Code' not in df_naf.columns or 'Libellé' not in df_naf.columns:
                         raise ValueError("Colonnes 'Code' ou 'Libellé' manquantes avec sep=';', latin-1")
                except (ValueError, pd.errors.ParserError, UnicodeDecodeError):
                     st.warning(f"Échec lecture de {file_path} avec sep=';' et encodage latin-1. Essai avec ','.")
                     df_naf = pd.read_csv(file_path, sep=',', dtype={'Code': str}, encoding='latin-1')
                     if 'Code' not in df_naf.columns or 'Libellé' not in df_naf.columns:
                         st.error(f"Colonnes 'Code' et 'Libellé' introuvables dans {file_path} avec les séparateurs et encodages testés.")
                         return None # Échec définitif

        # Vérifier si le DataFrame est vide après chargement
        if df_naf.empty:
            st.error(f"Le fichier NAF '{file_path}' est vide ou n'a pas pu être lu correctement.")
            return None

        # Nettoyer les espaces potentiels dans les noms de colonnes
        df_naf.columns = df_naf.columns.str.strip()

        # S'assurer que la colonne 'Code' est bien de type string
        df_naf['Code'] = df_naf['Code'].astype(str)
        # Optionnel: Nettoyer les codes (enlever espaces etc.) si nécessaire
        # df_naf['Code'] = df_naf['Code'].str.strip()

        # Créer le dictionnaire : Code -> Libellé
        if df_naf['Code'].duplicated().any():
            st.warning(f"Attention : Codes NAF dupliqués trouvés dans {file_path}. Seul le dernier sera conservé.")
            # df_naf = df_naf.drop_duplicates(subset='Code', keep='last') # Optionnel: dédoublonner

        naf_dict = df_naf.set_index('Code')['Libellé'].to_dict()

        return naf_dict

    except FileNotFoundError:
        st.error(f"Erreur critique : Le fichier NAF '{file_path}' est introuvable. Vérifiez le chemin.")
        return None
    except pd.errors.EmptyDataError:
        st.error(f"Erreur critique : Le fichier NAF '{file_path}' est vide.")
        return None
    except Exception as e:
        st.error(f"Erreur critique lors du chargement du fichier NAF '{file_path}': {e}")
        return None

# Charger le dictionnaire NAF au démarrage de l'application
naf_detailed_lookup = load_naf_dictionary(NAF_FILE_PATH)

# --- Fonction de correspondance NAF ---
def correspondance_NAF(code_naf_input):
    """
    Retourne le libellé NAF détaillé pour un code donné.
    """
    if naf_detailed_lookup is None:
        return f"{code_naf_input} (Dico NAF non chargé)"

    if not code_naf_input or not isinstance(code_naf_input, str):
        return "Code NAF invalide"

    # Nettoyer le code NAF en entrée (au cas où)
    code_naf_clean = code_naf_input.strip()
    return naf_detailed_lookup.get(code_naf_clean, f"{code_naf_clean} (Libellé non trouvé)")


# --- Fonctions Géocodage, API, Traitement ---
def geocoder_ban_france(adresse):
    """
    Géocode une adresse en utilisant l'API BANFrance via geopy.
    """
    if not adresse:
        st.error("L'adresse ne peut pas être vide.")
        return None
    # Utiliser une user_agent statique ou avec moins de variabilité
    geolocator = BANFrance(user_agent="streamlit_app_recherche_entreprises/1.0")
    try:
        with st.spinner(f"Géocodage de l'adresse '{adresse}'..."):
            location = geolocator.geocode(adresse, exactly_one=True, timeout=10)
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

def rechercher_geographiquement_entreprises(lat, long, radius, section_activite_principale):
    """
    Recherche les entreprises via l'API recherche-entreprises.api.gouv.fr.
    """
    url = "https://recherche-entreprises.api.gouv.fr/near_point"
    params = {
        'lat': lat,
        'long': long,
        'radius': radius,
        'section_activite_principale': section_activite_principale,
        'per_page': 25  #Le nombre de résultats par page, défault à 10, limité à 25.
    }
    headers = {'accept': 'application/json'}
    entreprises_detaillees = []
    page = 1
    total_pages = 1 # Initialisation

    # Utiliser st.status au lieu de st.spinner
    initial_status_message = f"Initialisation de la recherche (NAF: {section_activite_principale}) autour de ({lat:.4f}, {long:.4f})..."
    with st.status(initial_status_message, expanded=True) as status: # expanded=True pour voir les messages internes
        while True:
            params['page'] = page
            # Mettre à jour le statut AVANT l'appel API pour la page actuelle
            current_status_message = f"Recherche page {page}/{total_pages if total_pages > 1 else '?'}... (NAF: {section_activite_principale}, {len(entreprises_detaillees)} trouvés)"
            status.update(label=current_status_message)
            try:
                response = requests.get(url, params=params, headers=headers, timeout=20) # Ajout timeout
                response.raise_for_status() # Lève une exception pour les codes d'erreur HTTP (4xx, 5xx)
                data = response.json()
            except requests.exceptions.Timeout:
                 st.error(f"Erreur lors de l'appel API Entreprises : Timeout (délai dépassé) à la page {page}.")
                 return None # Ou retourner les résultats partiels: entreprises_detaillees
            except requests.exceptions.RequestException as e:
                st.error(f"Erreur lors de l'appel API Entreprises : {e}")
                # Essayer de donner plus d'infos si possible (ex: contenu de la réponse si pas JSON)
                try:
                    error_content = response.text
                    st.error(f"Contenu de la réponse (erreur): {error_content[:500]}...") # Limiter la taille
                except Exception:
                    pass # Ignorer si on ne peut pas lire la réponse
                return None # Ou retourner les résultats partiels: entreprises_detaillees

            results = data.get('results', [])
            current_total_pages = data.get('total_pages', page) # Lire total_pages à chaque page

            if not results:
                if page == 1:
                    st.info("Aucun résultat trouvé pour cette recherche.")
                break # Sortir si pas de résultats sur la page actuelle

            entreprises_detaillees.extend(results)

            # Mise à jour du message spinner seulement si total_pages change ou pour la page suivante
            if current_total_pages != total_pages or page < current_total_pages:
                 total_pages = current_total_pages # Mettre à jour le total connu
                 spinner_message = f"Recherche des entreprises (NAF: {section_activite_principale}) autour de ({lat:.4f}, {long:.4f}) - Page {page}/{total_pages} ({len(entreprises_detaillees)} trouvés)..."
                 # Note: La mise à jour dynamique du texte du spinner Streamlit a ses limites

            if page >= total_pages:
                break # Sortir si on a atteint la dernière page

            page += 1
            # Mise à jour du message pour la page suivante (avant la requête suivante)
            spinner_message = f"Recherche des entreprises (NAF: {section_activite_principale}) autour de ({lat:.4f}, {long:.4f}) - Page {page}/{total_pages} ({len(entreprises_detaillees)} trouvés)..."


    return entreprises_detaillees

def traitement_reponse_api(entreprises, selected_effectifs_codes):
    """
    Prépare les données pour l'affichage et le téléchargement,
    en filtrant sur les codes de tranches d'effectifs sélectionnés.
    """
    data = []
    if not entreprises:
        return pd.DataFrame(data)

    # Pour éviter les logs répétitifs (si nécessaire)
    # print_debug_once = True

    for entreprise in entreprises:
        siren = entreprise.get('siren', 'N/A')
        nom_complet = entreprise.get('nom_complet', 'N/A')
        nom_sociale = entreprise.get('nom_raison_sociale', 'N/A') # Garder pour info entreprise
        date_creation = entreprise.get('date_creation', 'N/A')
        nombre_etablissements_ouverts = entreprise.get('nombre_etablissements_ouverts', 'N/A')
        matching_etablissements = entreprise.get('matching_etablissements', [])

        code_naf_entreprise = entreprise.get('activite_principale', 'N/A') # NAF niveau entreprise
        tranche_effectif_salarie_entreprise = entreprise.get('tranche_effectif_salarie')
        tranche_description_entreprise = effectifs_tranches.get(tranche_effectif_salarie_entreprise, 'N/A')

        # --- Extraction des données financières les plus récentes ---
        finances = entreprise.get("finances", {})
        latest_year_str = 'N/A'
        ca_latest = 'N/A'
        resultat_net_latest = 'N/A'

        if finances and isinstance(finances, dict):
            try:
                available_years = [year for year in finances.keys() if year.isdigit()]
                if available_years:
                    latest_year_str = max(available_years)
                    latest_year_data = finances.get(latest_year_str, {})
                    ca_latest = latest_year_data.get("ca") # Garder numérique si possible
                    resultat_net_latest = latest_year_data.get("resultat_net") # Garder numérique
                    # Mettre 'N/A' si None ou vide après .get()
                    if ca_latest is None: ca_latest = 'N/A'
                    if resultat_net_latest is None: resultat_net_latest = 'N/A'

            except Exception as e:
                st.warning(f"Erreur lors de l'extraction des données financières pour SIREN {siren}: {e}")
                latest_year_str = 'Erreur'
                ca_latest = 'Erreur'
                resultat_net_latest = 'Erreur'
        # --- Fin Extraction Finances ---

        for etablissement in matching_etablissements:
            etat_administratif_etablissement = etablissement.get('etat_administratif', 'N/A')
            tranche_effectif_salarie_etablissement = etablissement.get('tranche_effectif_salarie')
            annee_tranche_effectif_salarie_etablissement = etablissement.get('annee_tranche_effectif_salarie')

            # Filtrer sur état actif ET tranche d'effectif sélectionnée
            if etat_administratif_etablissement == 'A' and selected_effectifs_codes and tranche_effectif_salarie_etablissement in selected_effectifs_codes:

                # --- Logique NAF Améliorée ---
                code_naf_etablissement = etablissement.get('activite_principale')
                # Utiliser NAF établissement si dispo, sinon NAF entreprise
                code_naf_a_utiliser = code_naf_etablissement if code_naf_etablissement else code_naf_entreprise
                libelle_naf_a_utiliser = correspondance_NAF(code_naf_a_utiliser)
                # -----------------------------

                siret = etablissement.get('siret', 'N/A')
                adresse = etablissement.get('adresse', 'N/A')
                latitude = etablissement.get('latitude')
                longitude = etablissement.get('longitude')
                liste_enseignes = etablissement.get('liste_enseignes', [])
                est_siege = etablissement.get('est_siege', False)

                tranche_description_etablissement = effectifs_tranches.get(tranche_effectif_salarie_etablissement, 'N/A')
                enseignes_str = ', '.join(liste_enseignes) if liste_enseignes else 'N/A'

                # --- Préparation pour Pydeck ---
                # --- CORRECTION: Déterminer la lettre de section NAF à partir des 2 premiers chiffres ---
                naf_section_letter = 'N/A' # Default
                if code_naf_a_utiliser and isinstance(code_naf_a_utiliser, str) and len(code_naf_a_utiliser) >= 2:
                    two_digits = code_naf_a_utiliser[:2]
                    if two_digits.isdigit():
                        division = int(two_digits)
                        if 1 <= division <= 3: naf_section_letter = "A"
                        elif 5 <= division <= 9: naf_section_letter = "B"
                        elif 10 <= division <= 33: naf_section_letter = "C"
                        elif division == 35: naf_section_letter = "D"
                        elif 36 <= division <= 39: naf_section_letter = "E"
                        elif 41 <= division <= 43: naf_section_letter = "F"
                        elif 45 <= division <= 47: naf_section_letter = "G"
                        elif 49 <= division <= 53: naf_section_letter = "H"
                        elif 55 <= division <= 56: naf_section_letter = "I"
                        elif 58 <= division <= 63: naf_section_letter = "J"
                        elif 64 <= division <= 66: naf_section_letter = "K"
                        elif division == 68: naf_section_letter = "L"
                        elif 69 <= division <= 75: naf_section_letter = "M"
                        elif 77 <= division <= 82: naf_section_letter = "N"
                        elif division == 84: naf_section_letter = "O" # Section O existe
                        elif division == 85: naf_section_letter = "P" # Section P existe
                        elif 86 <= division <= 88: naf_section_letter = "Q"
                        elif 90 <= division <= 93: naf_section_letter = "R"
                        elif 94 <= division <= 96: naf_section_letter = "S" # Section S existe
                        elif 97 <= division <= 98: naf_section_letter = "T" # Section T existe
                        elif division == 99: naf_section_letter = "U" # Section U existe
                        # else: reste 'N/A' si division inconnue

                # --- Fin de la CORRECTION ---


                color = naf_color_mapping.get(naf_section_letter, naf_color_mapping['N/A'])
                radius = size_mapping.get(tranche_effectif_salarie_etablissement, size_mapping['N/A'])
                # -----------------------------

                data.append({
                    # --- Infos Établissement ---
                    'SIRET': siret,
                    'Nom complet': nom_complet, # Utiliser nom_complet de l'entreprise
                    'Enseignes': enseignes_str,
                    'Activité NAF/APE': libelle_naf_a_utiliser,
                    'Code NAF': code_naf_a_utiliser,
                    'Est siège social': est_siege,
                    'Adresse établissement': adresse,
                    'Code effectif établissement': tranche_effectif_salarie_etablissement,
                    'Nb salariés établissement': tranche_description_etablissement, # <-- Nom utilisé ici
                    'Année nb salariés établissement': annee_tranche_effectif_salarie_etablissement if annee_tranche_effectif_salarie_etablissement else 'N/A',
                    'Latitude': latitude,
                    'Longitude': longitude,
                    # --- Infos Entreprise ---
                    'SIREN': siren,
                    'Raison sociale': nom_sociale, # <-- Nom utilisé ici
                    'Date de création': date_creation,
                    'Nb total établissements ouverts': nombre_etablissements_ouverts, # <-- Nom utilisé ici
                    'Nb salariés entreprise': tranche_description_entreprise, # <-- Nom utilisé ici
                    # --- Infos Financières (Entreprise) ---
                    'Année Finances': latest_year_str,
                    'Chiffre d\'Affaires': ca_latest,
                    'Résultat Net': resultat_net_latest,
                     # --- Colonnes pour Pydeck ---
                    'Color': color,
                    'Radius': radius,
                    'Section NAF': naf_section_letter
                })

    if not data: # Si aucune donnée n'a été ajoutée (aucun établissement ne correspondait aux filtres)
        return pd.DataFrame(data) # Retourner un DataFrame vide avec les bonnes colonnes si possible

    df = pd.DataFrame(data)

    # Conversion en numérique après création du DataFrame
    df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
    df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')

    # Convertir les colonnes financières en numérique, gérant les erreurs ('N/A', 'Erreur' -> NaN)
    if 'Chiffre d\'Affaires' in df.columns:
        df['Chiffre d\'Affaires'] = pd.to_numeric(df['Chiffre d\'Affaires'], errors='coerce')
    if 'Résultat Net' in df.columns:
        df['Résultat Net'] = pd.to_numeric(df['Résultat Net'], errors='coerce')

    # Réorganiser les colonnes pour une meilleure lisibilité - CORRIGÉ
    cols_ordre = [
        'SIRET', 'Nom complet', 'Enseignes', 'Activité NAF/APE', 'Code NAF', 'Est siège social', 'Adresse établissement',
        'Nb salariés établissement', # <-- Nom corrigé
        'Année nb salariés établissement', # <-- Ajouté
        'Code effectif établissement', # Optionnel: garder le code aussi
        'SIREN', 'Raison sociale', # <-- Nom corrigé (était déjà ok)
        'Date de création',
        'Nb total établissements ouverts', # <-- Nom corrigé
        'Nb salariés entreprise', # <-- Nom corrigé
        'Année Finances', 'Chiffre d\'Affaires', 'Résultat Net',
        'Latitude', 'Longitude', 'Section NAF' # Garder Lat/Lon pour info, même si utilisées par Pydeck
    ]
    # Garder seulement les colonnes qui existent réellement dans le DataFrame créé
    cols_existantes = [col for col in cols_ordre if col in df.columns]

    # Ajouter les colonnes Pydeck si elles ne sont pas déjà dans la liste ordonnée (normalement non)
    for pydeck_col in ['Color', 'Radius']:
         if pydeck_col in df.columns and pydeck_col not in cols_existantes:
             cols_existantes.append(pydeck_col)

    # Retourner le DataFrame avec les colonnes existantes dans l'ordre souhaité
    return df[cols_existantes]


# --- Interface Streamlit ---
st.title("🔎 Recherche d'entreprises pour candidatures spontannées")
st.markdown("Trouvez des entreprises en fonction d'une adresse, d'un rayon, de secteurs d'activité (NAF) et de tranches d'effectifs salariés.")

# --- Zone de saisie des paramètres ---
with st.sidebar:
    st.header("Paramètres de Recherche")

    # --- Localisation (par Adresse) ---
    st.subheader("📍 Localisation")
    # Supprimer la valeur par défaut, rendre le champ obligatoire via la logique de validation
    adresse_input = st.text_input(
        "Adresse de référence",
        placeholder="Ex: 1 Rue de la Paix, 75002 Paris", # Utiliser un placeholder
        help="Veuillez saisir une adresse complète pour lancer la recherche." # Mettre à jour l'aide
    )
    # default_adresse = "Avenue du Général de Gaulle, 94100 Saint-Maur-des-Fossés" # <-- LIGNE SUPPRIMÉE
    # adresse_input = st.text_input("Adresse de référence", value=default_adresse, help="Ex: 1 Rue de la Paix, 75002 Paris") # <-- LIGNE MODIFIÉE CI-DESSUS

    default_radius = 5.0
    radius_input = st.number_input("Rayon de recherche (km)", min_value=0.1, max_value=50.0, value=default_radius, step=0.5, format="%.1f")

    st.markdown("---")

    # --- Filtres Entreprise ---
    st.subheader("🏢 Filtres Entreprise")

    # --- Définir les valeurs par défaut AVANT l'expander ---
    default_naf_letters_list = "C,G,I,J".split(',')
    default_effectifs_summary = ">= 10 salariés" # Ou adaptez si la sélection par défaut change

    # --- Créer des descriptions brèves pour le label ---
    # Prend le premier mot significatif après le " - "
    naf_sections_brief = {
        letter: description.split(' - ')[1].split(' ')[0].replace(',', '').replace(';', '')
        for letter, description in naf_sections.items()
    }
    # Obtenir les descriptions brèves pour les lettres par défaut
    default_naf_briefs = [naf_sections_brief.get(letter, letter) for letter in default_naf_letters_list]
    naf_summary_brief = ', '.join(default_naf_briefs) # Ex: "Industrie, Commerce, Hébergement, Information"

    # --- Créer le label dynamique pour l'expander ---
    # --- Afficher le résumé des filtres par défaut AVANT l'expander ---
    st.caption("Filtres par défaut appliqués :") # Titre pour le résumé
    st.caption(f"- Activités : {naf_summary_brief}") # Ligne pour les activités
    st.caption(f"- Effectifs : {default_effectifs_summary}") # Ligne pour les effectifs

    # Utilisation des descriptions brèves
    expander_label = "Modifier les filtres"

    # --- Utiliser st.expander avec le label dynamique ---
    # Remplacement de la ligne précédente par celle-ci
    with st.expander(expander_label, expanded=False):
        # --- NAF Sections (Checkbox Implementation) ---
        st.markdown("**Sections d'activité NAF**")
        st.caption("Cochez les sections d'activité qui vous intéressent.")

        default_naf_letters = "C,G,I,J".split(',')
        selected_naf_letters_cb = []

        cols_naf = st.columns(2)
        col_idx_naf = 0
        for letter, description in sorted(naf_sections.items()):
            is_checked_by_default_naf = letter in default_naf_letters
            with cols_naf[col_idx_naf]:
                is_selected_naf = st.checkbox(
                    description,
                    value=is_checked_by_default_naf,
                    key=f"naf_{letter}"
                )
            if is_selected_naf:
                selected_naf_letters_cb.append(letter)
            col_idx_naf = (col_idx_naf + 1) % len(cols_naf)
        # --- Fin NAF Checkboxes ---

        st.markdown("---") # Séparateur visuel à l'intérieur de l'expander

        # --- Tranches d'effectifs (Checkbox Implementation) --- # Déplacé à l'intérieur de l'expander
        st.markdown("**Tranches d'effectifs salariés (Établissement)**")
        st.caption("Cochez les tranches d'effectifs qui vous intéressent.")

        default_effectifs_codes = ['11', '12', '21', '22', '31', '32', '41', '42', '51', '52', '53']
        selected_effectifs_codes_cb = []

        cols_eff = st.columns(2)
        col_idx_eff = 0
        for code, description in effectifs_tranches.items():
            is_checked_by_default_eff = code in default_effectifs_codes
            with cols_eff[col_idx_eff]:
                is_selected_eff = st.checkbox(
                    description,
                    value=is_checked_by_default_eff,
                    key=f"eff_{code}"
                )
            if is_selected_eff:
                selected_effectifs_codes_cb.append(code)
            col_idx_eff = (col_idx_eff + 1) % len(cols_eff)
        # --- Fin Effectifs Checkboxes ---

    # --- Fin de l'expander ---


    st.markdown("---")

    # Bouton pour lancer la recherche
    lancer_recherche = st.button("🚀 Rechercher les Entreprises")

# --- Zone d'affichage des résultats ---
results_container = st.container()

if lancer_recherche:
    # --- Vérification #0 : Dictionnaire NAF chargé ---
    if naf_detailed_lookup is None:
        st.error("Impossible de lancer la recherche car le fichier NAF détaillé n'a pas pu être chargé.")
        st.stop()

    # --- Vérification #1 : Adresse saisie --- AJOUTÉ ICI ---
    if not adresse_input or not adresse_input.strip(): # Vérifie si vide ou contient seulement des espaces
        st.error("⚠️ Veuillez saisir une adresse de référence pour lancer la recherche.")
        st.stop() # Arrête l'exécution si l'adresse est manquante
    # --- FIN AJOUT ---

    # --- Vérification #2 : Filtres NAF et Effectifs (déplacé après validation adresse) ---
    if not selected_naf_letters_cb:
        st.warning("⚠️ Veuillez sélectionner au moins une section NAF (dans 'Affiner les filtres').")
        st.stop()
    sections_str = ",".join(sorted(selected_naf_letters_cb))

    if not selected_effectifs_codes_cb:
        st.warning("⚠️ Veuillez sélectionner au moins une tranche d'effectifs (dans 'Affiner les filtres').")
        st.stop()

    # Si toutes les validations sont passées :
    st.info(f"Recherche pour NAF Sections : {sections_str}")
    st.info(f"Filtrage sur effectifs établissement (codes) : {', '.join(selected_effectifs_codes_cb)}")

    # 1. Géocodage (maintenant on sait que adresse_input n'est pas vide)
    coordonnees = geocoder_ban_france(adresse_input)
    if coordonnees is None:
        # Les messages d'erreur sont déjà affichés dans la fonction geocoder
        # On peut ajouter un message générique ici si besoin
        st.error("Le géocodage de l'adresse a échoué. Vérifiez l'adresse fournie.")
        st.stop()
    lat_centre, lon_centre = coordonnees

    # 3. Appel API (le numéro d'étape change car validation filtres est avant)
    entreprises_trouvees = rechercher_geographiquement_entreprises(lat_centre, lon_centre, radius_input, sections_str)


    # Vider les anciens résultats avant d'afficher les nouveaux
    results_container.empty()
    with results_container:
        if entreprises_trouvees is not None:
            # 4. Traitement (utilise la fonction modifiée)
            df_resultats = traitement_reponse_api(entreprises_trouvees, selected_effectifs_codes_cb)

            # 5. Affichage
            st.success(f"📊 {len(df_resultats)} établissements trouvés correspondant à tous les critères.")

            if not df_resultats.empty:
                st.subheader("Résultats Détaillés")
                # Colonnes à afficher dans le tableau Streamlit (choisir parmi celles de cols_existantes)
                cols_a_afficher_dans_tableau = [
                    'SIRET', 'Nom complet', 'Enseignes',
                    'Est siège social', 'Adresse établissement',
                    'Activité NAF/APE', 'Nb salariés établissement', 'Année nb salariés établissement',
                    'Date de création',
                    'Chiffre d\'Affaires', 'Résultat Net', 'Année Finances'
                ]
                # Filtrer les colonnes existantes pour éviter les erreurs KeyErrors
                cols_existantes_pour_tableau = [col for col in cols_a_afficher_dans_tableau if col in df_resultats.columns]

                # Formater les colonnes numériques pour l'affichage (optionnel)
                df_display = df_resultats[cols_existantes_pour_tableau].copy()
                # Exemple: Formater CA et Résultat Net en milliers d'euros avec séparateur
                # Note: Cela transforme les colonnes en strings pour l'affichage
                # if 'Chiffre d\'Affaires' in df_display.columns:
                #     df_display['Chiffre d\'Affaires'] = df_display['Chiffre d\'Affaires'].map('{:,.0f}'.format, na_action='ignore').str.replace(',', ' ', regex=False)
                # if 'Résultat Net' in df_display.columns:
                #     df_display['Résultat Net'] = df_display['Résultat Net'].map('{:,.0f}'.format, na_action='ignore').str.replace(',', ' ', regex=False)

                st.dataframe(df_display) # Affiche le DataFrame formaté ou non

                # --- Carte Pydeck ---
                st.subheader("Carte des établissements trouvés")
                # Filtrer les données pour la carte (lignes sans lat/lon/radius/color valides)
                # Utilise df_resultats qui contient 'Color' et 'Radius'
                df_map = df_resultats.dropna(subset=['Latitude', 'Longitude', 'Radius', 'Color']).copy()

                if not df_map.empty:
                    # --- Débogage Pydeck (Commenté par défaut) ---
                    # st.subheader("🕵️‍♀️ Vérification des données pour la carte")
                    # st.write("Extrait des données utilisées pour la carte (`df_map`):")
                    # st.dataframe(df_map[['SIRET', 'Code NAF', 'Color', 'Code effectif établissement', 'Radius', 'Nom complet']].head())
                    # st.write("Informations sur les colonnes 'Color' et 'Radius':")
                    # try:
                    #      st.write(f"Valeurs uniques dans 'Color' (max 5): {df_map['Color'].astype(str).unique()[:5]}")
                    # except TypeError:
                    #      st.write("Impossible d'afficher les uniques de 'Color' (probablement des listes).")
                    # st.write(f"Valeurs uniques dans 'Radius' (max 5): {df_map['Radius'].unique()[:5]}")
                    # --- Fin Débogage Pydeck ---

                    # Définir la vue initiale de la carte
                    zoom_level = 11
                    if radius_input <= 1: zoom_level = 14
                    elif radius_input <= 5: zoom_level = 12
                    elif radius_input <= 10: zoom_level = 11
                    elif radius_input <= 25: zoom_level = 10
                    else: zoom_level = 9

                    initial_view_state = pdk.ViewState(
                        latitude=lat_centre, longitude=lon_centre,
                        zoom=zoom_level, pitch=0, bearing=0 # Ajout pitch pour perspective
                    )

                    # Définir la couche de points
                    layer = pdk.Layer(
                        'ScatterplotLayer',
                        data=df_map,
                        get_position='[Longitude, Latitude]',
                        get_color='Color',
                        get_radius='Radius',
                        radius_min_pixels=3,
                        radius_max_pixels=60,
                        pickable=True,
                        auto_highlight=True,
                    )

                    # Définir le tooltip (CORRIGÉ)
                    tooltip = {
                        "html": "<b>{Nom complet}</b><br/>" # <-- Nom corrigé
                                "SIRET: {SIRET}<br/>"
                                "Activité: {Activité NAF/APE}<br/>"
                                "Effectif Étab.: {Nb salariés établissement}", # <-- Nom vérifié
                        "style": {
                            "backgroundColor": "rgba(0, 0, 0, 0.7)", # Fond plus sombre
                            "color": "white",
                            "border": "1px solid white",
                            "padding": "5px"
                        }
                    }

                    # Créer l'objet Deck
                    deck = pdk.Deck(
                        layers=[layer],
                        initial_view_state=initial_view_state,
                        map_style='mapbox://styles/mapbox/light-v9',
                        tooltip=tooltip,
                        height=800
                    )

                    # Afficher la carte
                    st.pydeck_chart(deck)

                    # Légende
                    st.subheader("Légende")
                    cols_legende = st.columns([1, 2]) # Ajuster ratio si besoin
                    with cols_legende[0]:
                        st.markdown("**Taille ≈ Effectif Étab.**") # Changed => to ≈ for clarity

                        # Define pixel sizes for the legend circles (adjust as needed)
                        legend_pixel_sizes = {'01': 8, '12': 12, '32': 18, '53': 24}
                        # Base style for the circles
                        base_circle_style = "display: inline-block; border-radius: 50%; background-color: #808080; margin-right: 5px; vertical-align: middle;"

                        # Use the same representative codes as before
                        legend_sizes = {'01': 'Petit', '12': 'Moyen', '32': 'Grand', '53': 'Très Grand'}

                        for code, label in legend_sizes.items():
                             if code in effectifs_tranches:
                                 # Get the pixel size for this category, default to smallest if not found
                                 pixel_size = legend_pixel_sizes.get(code, 8)
                                 # Create the HTML span for the circle with specific size
                                 circle_html = f'<span style="{base_circle_style} height: {pixel_size}px; width: {pixel_size}px;"></span>'
                                 # Display the circle and the text using markdown
                                 st.markdown(f"{circle_html} {label} ({effectifs_tranches[code]})", unsafe_allow_html=True)


                    with cols_legende[1]:
                        st.markdown("**Couleur = Section NAF**")
                        # --- CORRECTION: Utiliser la colonne 'Section NAF' ---
                        if 'Section NAF' in df_map.columns: # Vérifier que la colonne existe
                            active_sections = df_map['Section NAF'].unique() # Obtenir les lettres uniques présentes
                            # --- FIN CORRECTION ---

                            # Itérer sur les lettres NAF sélectionnées par l'utilisateur
                            for letter in sorted(selected_naf_letters_cb):
                                # Afficher la couleur seulement si la section a été sélectionnée ET est présente dans les résultats
                                if letter in naf_sections and letter in active_sections:
                                    color_rgb = naf_color_mapping.get(letter, [0,0,0])
                                    color_hex = '#%02x%02x%02x' % tuple(color_rgb)
                                    # Utiliser st.markdown pour la couleur
                                    st.markdown(f"<span style='color:{color_hex}; font-size: 1.5em;'>⬤</span> {naf_sections[letter]}", unsafe_allow_html=True)
                        else:
                            st.warning("Colonne 'Section NAF' non trouvée dans les données pour générer la légende des couleurs.") # Message d'erreur si besoin
                else:
                    st.info("Aucun établissement avec des coordonnées géographiques valides à afficher sur la carte.")
                # --- Fin Carte Pydeck ---


                # Téléchargement CSV (utilise df_resultats qui a toutes les colonnes avant sélection pour affichage)
                st.subheader("Télécharger les résultats")
                csv = df_resultats.to_csv(index=False, encoding='utf-8-sig', sep=';') # Utiliser ; pour Excel FR
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                adresse_safe = "".join(c if c.isalnum() else "_" for c in adresse_input[:30])
                # Utiliser les codes effectifs sélectionnés dans le nom de fichier
                eff_codes_str = '_'.join(sorted(selected_effectifs_codes_cb))
                nom_fichier_csv = f"entreprises_{adresse_safe}_R{radius_input}km_naf_{sections_str.replace(',', '_')}_eff_{eff_codes_str}_{timestamp}.csv"
                st.download_button(
                    label="📥 Télécharger en CSV (séparateur ';')",
                    data=csv,
                    file_name=nom_fichier_csv,
                    mime='text/csv',
                )
            # Gérer le cas où l'API a renvoyé des entreprises, mais le filtrage n'a laissé aucun établissement
            elif entreprises_trouvees and len(df_resultats) == 0:
                st.info("Des entreprises ont été trouvées dans la zone et pour les sections NAF, mais aucun de leurs établissements actifs ne correspond aux tranches d'effectifs sélectionnées.")
            # Gérer le cas où l'API n'a renvoyé aucune entreprise dès le départ (message déjà affiché dans la fonction API)
            # elif not entreprises_trouvees:
            #    st.info("Aucune entreprise trouvée pour les critères de localisation et de section NAF.")

        else:
             # Ce cas est atteint si rechercher_geographiquement_entreprises retourne None (erreur API)
             st.error("La recherche d'entreprises a échoué en raison d'une erreur lors de la communication avec l'API.")

# Pied de page
st.sidebar.markdown("---")
st.sidebar.info(f"🗓️ {datetime.date.today().strftime('%d/%m/%Y')}")
st.sidebar.info("API: recherche-entreprises.api.gouv.fr & BAN France")
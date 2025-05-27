import datetime
import json
import os

import pandas as pd
import pydeck as pdk
import streamlit as st
import api_client
import config
import data_utils
import geo_utils

# --- SCRIPT START LOG ---
# print(f"{datetime.datetime.now()} - INFO - app.py script started.") # Optional: uncomment for runtime debugging
# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(layout="wide")

# --- STYLES CSS PERSONNALISÉS ---
st.markdown(
    """
<style>
    /* Cible les boutons primaires de Streamlit */
    /* Cible les boutons primaires de Streamlit */
    .stButton > button[kind="primary"] {
        font-weight: bold !important;
        border: 1px solid #2980B9 !important; /* Bleu plus foncé pour la bordure */
        padding: 0.6em 1.2em !important;
        box-shadow: 0px 2px 3px rgba(0, 0, 0, 0.2) !important;
        background-color: #3498DB !important;  /* Bleu principal */
        color: white !important;
    }

    .stButton > button[kind="primary"]:hover {
        border-color: #1F618D !important; /* Bleu encore plus foncé */
        background-color: #2E86C1 !important; /* Bleu légèrement plus foncé */
    }
</style>
""",
    unsafe_allow_html=True,
)

# --- ERM DATA HANDLING FUNCTIONS ---
def load_global_erm_data(file_path=config.DEFAULT_ERM_FILE_PATH):
    """
    Charges les données ERM (Entreprises, Contacts, Actions) depuis un fichier JSON global.
    Initialise des DataFrames vides avec les schémas définis dans config.py si le fichier n'existe pas ou est corrompu.
    """
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            df_e = pd.DataFrame(data.get("entreprises", []))
            df_c = pd.DataFrame(data.get("contacts", []))
            df_a = pd.DataFrame(data.get("actions", []))

            # Convert specific columns to datetime objects
            date_cols_entreprise = ["Date de création Entreprise"]
            date_cols_action = ["Date Action", "Date Échéance"]

            for col in date_cols_entreprise:
                if col in df_e.columns:
                    df_e[col] = pd.to_datetime(df_e[col], errors='coerce')
            for col in date_cols_action:
                if col in df_a.columns:
                    df_a[col] = pd.to_datetime(df_a[col], errors='coerce')

        except (json.JSONDecodeError, KeyError) as e:
            st.error(f"Erreur de lecture ou format incorrect du fichier ERM ({file_path}): {e}. Un nouveau fichier sera utilisé/créé si des données sont sauvegardées.")
            df_e = pd.DataFrame(columns=config.ENTREPRISES_ERM_COLS)
            df_c = pd.DataFrame(columns=config.CONTACTS_ERM_COLS)
            df_a = pd.DataFrame(columns=config.ACTIONS_ERM_COLS)
    else:
        df_e = pd.DataFrame(columns=config.ENTREPRISES_ERM_COLS)
        df_c = pd.DataFrame(columns=config.CONTACTS_ERM_COLS)
        df_a = pd.DataFrame(columns=config.ACTIONS_ERM_COLS)

    # Ensure all expected columns are present and in correct order
    df_e = df_e.reindex(columns=config.ENTREPRISES_ERM_COLS)
    df_c = df_c.reindex(columns=config.CONTACTS_ERM_COLS)
    df_a = df_a.reindex(columns=config.ACTIONS_ERM_COLS)
    
    return df_e, df_c, df_a

def save_global_erm_data(df_e, df_c, df_a, file_path=config.DEFAULT_ERM_FILE_PATH):
    """
    Sauvegarde les DataFrames ERM (Entreprises, Contacts, Actions) dans un fichier JSON global.
    Convertit les DataFrames en dictionnaires, gérant les NaNs pour la sérialisation JSON.
    Utilise default=str pour gérer la sérialisation des objets datetime.
    """
    data_to_save = {
        "entreprises": df_e.astype(object).where(pd.notnull(df_e), None).to_dict(orient="records"),
        "contacts": df_c.astype(object).where(pd.notnull(df_c), None).to_dict(orient="records"),
        "actions": df_a.astype(object).where(pd.notnull(df_a), None).to_dict(orient="records"),
    }
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde des données ERM : {e}")

# --- CALLBACKS FOR ERM DATA MODIFICATION ---
def on_erm_data_changed():
    """Callback pour sauvegarder les données ERM lorsque des modifications sont détectées."""
    save_global_erm_data(st.session_state.get('df_entreprises_erm'), st.session_state.get('df_contacts_erm'), st.session_state.get('df_actions_erm'))


# --- INITIALISATION DE L'ÉTAT DE SESSION POUR L'AUTHENTIFICATION ET ERM ---
# print(f"{datetime.datetime.now()} - INFO - Initializing session state variables.") # Optional: uncomment for runtime debugging
# Initialisation des DataFrames ERM s'ils n'existent pas encore dans la session.
# Sera rempli par load_global_erm_data plus tard.
if "df_entreprises_erm" not in st.session_state:
    st.session_state.df_entreprises_erm = pd.DataFrame(columns=config.ENTREPRISES_ERM_COLS)
if "df_contacts_erm" not in st.session_state:
    st.session_state.df_contacts_erm = pd.DataFrame(columns=config.CONTACTS_ERM_COLS)
if "df_actions_erm" not in st.session_state:
    st.session_state.df_actions_erm = pd.DataFrame(columns=config.ACTIONS_ERM_COLS)
if "confirm_flush" not in st.session_state:
    st.session_state.confirm_flush = False
if "editor_key_version" not in st.session_state:
    st.session_state.editor_key_version = 0
if "df_search_results" not in st.session_state:
    st.session_state.df_search_results = None
if "search_coordinates" not in st.session_state:
    st.session_state.search_coordinates = None
if "search_radius" not in st.session_state:
    st.session_state.search_radius = None

# --- GESTION DE L'ÉTAT DE SESSION POUR LES PARAMÈTRES DE RECHERCHE ---
# Initialise les sélections par défaut pour les filtres NAF et effectifs
# si elles ne sont pas déjà présentes dans l'état de session.
# --- TITRE ET DESCRIPTION (Toujours visible) ---
st.title(
    "🔎 Application de recherche d'employeurs potentiels pour candidatures spontanées"
)
st.markdown(
    "Trouvez des entreprises en fonction d'une adresse, d'un rayon, de secteurs d'activité (NAF) et de tranches d'effectifs salariés."
)


st.header("Paramètres de recherche")

# --- Gestion état session pour les filtres de recherche ---
if "selected_naf_letters" not in st.session_state:
    st.session_state.selected_naf_letters = ["F", "G", "J"]
if "selected_effectifs_codes" not in st.session_state:
    st.session_state.selected_effectifs_codes = [
        "11",
        "12",
        "21",
        "22",
        "31",
        "32",
        "41",
        "42",
        "51",
        "52",
        "53",
    ]
if "selected_specific_naf_codes" not in st.session_state:
    st.session_state.selected_specific_naf_codes = set()
else:
    if not isinstance(st.session_state.selected_specific_naf_codes, set):
        st.session_state.selected_specific_naf_codes = set(
            st.session_state.selected_specific_naf_codes
        )

# --- Initialisation et Vérification du chargement des données NAF ---
# This call will trigger load_naf_dictionary (and its caching) 
# and populate data_utils.naf_detailed_lookup
data_utils.get_naf_lookup()

if data_utils.naf_detailed_lookup is None: # Check if loading was successful
    st.error(
        "Erreur critique : Le dictionnaire NAF n'a pas pu être chargé. "
        "Vérifiez la présence et le format du fichier NAF.csv. L'application ne peut pas continuer."   
    )
    st.stop()

# --- Chargement des données ERM dans l'état de session ---
if "erm_data_loaded" not in st.session_state:
    st.session_state.df_entreprises_erm, \
    st.session_state.df_contacts_erm, \
    st.session_state.df_actions_erm = load_global_erm_data()
    st.session_state.erm_data_loaded = True    

col_gauche, col_droite = st.columns(2)

with col_gauche:
    st.subheader("📍 Localisation")
    # Utilisation de sous-colonnes pour contrôler la largeur des champs de saisie
    input_col_loc, _ = st.columns(
        [2, 1]
    )  # Les champs prendront 2/3 de la largeur de col_gauche
    with input_col_loc:
        adresse_input = st.text_input(
            "Adresse ou commune de référence",
            placeholder="Ex: 1, avenue du docteur Gley 75020 Paris",
            help="Veuillez saisir une adresse, idéalement complète, pour lancer la recherche.",
        )
        default_radius = 5.0
        radius_input = st.number_input(
            "Rayon de recherche (km)",
            min_value=0.1,
            max_value=50.0,
            value=default_radius,
            step=0.5,
            format="%.1f",
        )

    st.subheader("📊 Tranches d'effectifs salariés (Établissement)")

    def on_effectif_change(group_key_arg, codes_in_group_arg):
        """
        Callback pour la sélection des groupes de tranches d'effectifs.
        Met à jour st.session_state.selected_effectifs_codes en fonction de la sélection du groupe.
        """
        eff_key = f"eff_group_{group_key_arg}"
        is_selected = st.session_state[eff_key]
        current_selection_codes_eff = set(st.session_state.selected_effectifs_codes)
        if is_selected:
            current_selection_codes_eff.update(codes_in_group_arg)
        else:
            current_selection_codes_eff.difference_update(codes_in_group_arg)
        st.session_state.selected_effectifs_codes = sorted(
            list(current_selection_codes_eff)
        )
        # Streamlit gère le rerun après l'exécution du callback on_change.

    cols_eff = st.columns(2)
    col_idx_eff = 0
    for group_key, details in config.effectifs_groupes_details.items():
        is_group_currently_selected = any(
            code in st.session_state.selected_effectifs_codes
            for code in details["codes"]
        )
        with cols_eff[col_idx_eff % len(cols_eff)]:
            st.checkbox(
                f"{details['icon']} {details['label']}",
                value=is_group_currently_selected,
                key=f"eff_group_{group_key}",
                on_change=on_effectif_change,
                args=(group_key, details["codes"]),
            )
        col_idx_eff += 1

with col_droite:
    st.subheader("📂 Secteurs d'activité NAF")
    st.caption(
        "Sélectionnez les sections larges. Vous pourrez affiner par codes spécifiques ci-dessous (optionnel)."
    )

    def on_section_change():
        """
        Callback pour la sélection des sections NAF.
        Met à jour st.session_state.selected_naf_letters.
        Si une section est désélectionnée, les codes NAF spécifiques associés à cette section sont retirés de la sélection.
        """
        current_sections = []
        for letter in config.naf_sections_details:  # Utiliser la nouvelle structure
            if st.session_state.get(f"naf_section_{letter}", False):
                current_sections.append(letter)
        if set(current_sections) != set(st.session_state.selected_naf_letters):
            st.session_state.selected_naf_letters = current_sections
            st.session_state.selected_specific_naf_codes = {
                code
                for code in st.session_state.selected_specific_naf_codes
                if data_utils.get_section_for_code(code)
                in st.session_state.selected_naf_letters
            }
            # Streamlit gère le rerun.

    cols_naf = st.columns(2)
    col_idx_naf = 0
    for letter, details in sorted(config.naf_sections_details.items()):
        with cols_naf[col_idx_naf]:
            st.checkbox(
                f"{details['icon']} {details['description']}",
                value=(letter in st.session_state.selected_naf_letters),
                key=f"naf_section_{letter}",
                on_change=on_section_change,
            )
        col_idx_naf = (col_idx_naf + 1) % len(cols_naf)

    # --- Affinage Optionnel par Codes NAF Spécifiques ---
    with st.expander("Affiner par codes NAF spécifiques (Optionnel)", expanded=False):
        selected_sections_sorted = sorted(st.session_state.selected_naf_letters)
        if not selected_sections_sorted:
            st.caption(
                "Sélectionnez au moins une section NAF ci-dessus pour pouvoir affiner par code."
            )
        else:

            def on_specific_naf_change(change_type, section_letter=None, code=None):
                """
                Callback pour la sélection des codes NAF spécifiques.
                Gère la sélection/désélection de tous les codes d'une section ou d'un code individuel.
                """
                if change_type == "select_all":
                    select_all_key = f"select_all_{section_letter}"
                    should_select_all = st.session_state[select_all_key]
                    codes_in_section = set(
                        data_utils.get_codes_for_section(section_letter)
                    )
                    if should_select_all:
                        st.session_state.selected_specific_naf_codes.update(
                            codes_in_section
                        )
                    else:
                        st.session_state.selected_specific_naf_codes.difference_update(
                            codes_in_section
                        )
                elif change_type == "individual":
                    cb_key = f"specific_naf_cb_{code}"
                    is_selected = st.session_state[cb_key]
                    if is_selected:
                        st.session_state.selected_specific_naf_codes.add(code)
                    else:
                        st.session_state.selected_specific_naf_codes.discard(code)
                # Streamlit gère le rerun.

            for section_letter in selected_sections_sorted:
                section_details = config.naf_sections_details.get(section_letter)
                section_description = (
                    section_details["description"]
                    if section_details
                    else section_letter
                )
                st.markdown(
                    f"##### Codes spécifiques pour Section {section_description}"
                )
                codes_in_this_section = data_utils.get_codes_for_section(section_letter)
                if not codes_in_this_section:
                    st.caption("_Aucun code détaillé trouvé pour cette section._")
                    st.markdown("---")
                    continue
                all_codes_in_section_set = set(codes_in_this_section)
                are_all_selected = all_codes_in_section_set.issubset(
                    st.session_state.selected_specific_naf_codes
                )
                st.checkbox(
                    "Tout sélectionner / Désélectionner pour cette section",
                    value=are_all_selected,
                    key=f"select_all_{section_letter}",
                    on_change=on_specific_naf_change,
                    args=("select_all", section_letter),
                )
                st.markdown("---")
                cols_specific_naf = st.columns(2)
                col_idx_specific = 0
                for code in codes_in_this_section:
                    libelle = data_utils.naf_detailed_lookup.get(
                        code, "Libellé inconnu"
                    )
                    with cols_specific_naf[col_idx_specific % len(cols_specific_naf)]:
                        st.checkbox(
                            f"{code} - {libelle}",
                            value=(
                                code in st.session_state.selected_specific_naf_codes
                            ),
                            key=f"specific_naf_cb_{code}",
                            on_change=on_specific_naf_change,
                            args=("individual", None, code),
                        )
                    col_idx_specific += 1
                st.markdown("---")
        if st.session_state.selected_specific_naf_codes:
            st.caption(
                f"{len(st.session_state.selected_specific_naf_codes)} code(s) NAF spécifique(s) sélectionné(s) au total."
            )


st.markdown("---") # Séparateur avant la section du bouton de recherche

# Section pour le bouton de recherche et les informations associées
# Le bouton est centré en utilisant des colonnes "spacer"
col_spacer_gauche, col_contenu_bouton, col_spacer_droit = st.columns([2, 3, 2]) # Ajustez les ratios si besoin (ex: [1,1,1] ou [2,3,2])

with col_contenu_bouton:
    lancer_recherche = st.button(
        "🚀 Rechercher les entreprises", 
        type="primary", 
        key="main_search_button", 
        use_container_width=True # Le bouton prendra toute la largeur de col_contenu_bouton
    )

# Le message d'information est placé sous le bouton, occupant la pleine largeur
st.info(
    "Note : Les résultats d'une nouvelle recherche sont **ajoutés** au tableau ci-dessous. "
    "Utilisez le bouton 'Effacer le tableau des établissements' dans la 'Zone de danger' pour repartir d'une liste vide."
    )
st.markdown("---")

# --- ZONE D'AFFICHAGE DES RÉSULTATS ---
results_container = st.container()

# --- LOGIQUE PRINCIPALE DE RECHERCHE ---
if lancer_recherche:
    results_container.empty()  # Nettoyer les anciens résultats
    
    # --- Vérifications initiales ---
    if not adresse_input or not adresse_input.strip():
        st.error("⚠️ Veuillez saisir une adresse de référence pour lancer la recherche.")
        st.stop()
    if not st.session_state.selected_naf_letters:
        st.error("⚠️ Veuillez sélectionner au moins une section NAF.")
        st.stop()
    if not st.session_state.selected_effectifs_codes:
        st.warning("⚠️ Veuillez sélectionner au moins une tranche d'effectifs.")
        st.stop()

    # Construction de la liste finale des codes NAF pour l'appel API.
    # Si des codes spécifiques sont sélectionnés pour une section, ils sont utilisés.
    # Sinon, tous les codes de la section sélectionnée sont utilisés.
    final_codes_for_api = set()
    selected_specifics = st.session_state.selected_specific_naf_codes
    
    for section_letter in st.session_state.selected_naf_letters:
        specifics_in_section = {
            code
            for code in selected_specifics
            if data_utils.get_section_for_code(code) == section_letter
        }
        if specifics_in_section:
            final_codes_for_api.update(specifics_in_section)
        else:
            all_codes_in_section = data_utils.get_codes_for_section(section_letter)
            final_codes_for_api.update(all_codes_in_section)

    if not final_codes_for_api:
        st.error(
            "⚠️ Aucun code NAF résultant de votre sélection. Vérifiez vos choix de sections et de codes spécifiques."
        )
        st.stop()

    # Préparer les paramètres API
    final_api_params = {
        "activite_principale": ",".join(sorted(list(final_codes_for_api)))
    }

    # --- Début du processus dans le conteneur de résultats ---
    with results_container:
        st.info(
            f"Recherche pour {len(final_codes_for_api)} code(s) NAF spécifique(s) résultant de la sélection."
        )
        codes_display = final_api_params["activite_principale"]
        if len(codes_display) > 200:
            codes_display = codes_display[:200] + "..."
        # 1. Géocodage
        coordonnees = geo_utils.geocoder_ban_france(adresse_input)
        if coordonnees is None:
            # L'erreur est déjà affichée par geocoder_ban_france
            st.stop()
        lat_centre, lon_centre = coordonnees

        # 2. Lancer la recherche API
        entreprises_trouvees = api_client.rechercher_geographiquement_entreprises(
            lat_centre, lon_centre, radius_input, final_api_params
        )

        # --- Traitement et Affichage des résultats ---
        if entreprises_trouvees is not None:
            df_resultats = data_utils.traitement_reponse_api(
                entreprises_trouvees, st.session_state.selected_effectifs_codes
            )

            # Stocker les résultats et le contexte de la recherche dans l'état de session
            # pour permettre un affichage persistant même après des reruns (ex: ajout à l'ERM).
            st.session_state.df_search_results = df_resultats.copy()
            st.session_state.search_coordinates = (lat_centre, lon_centre)
            st.session_state.search_radius = radius_input

            # Les messages de succès, la carte et la légende sont gérés en dehors de ce bloc `if lancer_recherche`,
            # en utilisant l'état de session, pour persister à travers les reruns (par exemple,
            # après un rerun déclenché par l'ajout d'une entreprise à l'ERM).

            # Display messages for no results or API errors (these don't need to persist beyond the initial search action)
            if entreprises_trouvees is not None:
                if (
                    len(df_resultats) == 0
                ):  # df_resultats is defined from session_state or fresh search
                    if (
                        entreprises_trouvees == []
                    ):  # API returned empty list for the geo search with NAF
                        st.info(
                            "Aucune entreprise trouvée correspondant aux critères NAF/APE dans la zone spécifiée."
                        )
                    else:  # API returned results, but filtering by effectifs reduced to zero
                        st.info(
                            "Des entreprises ont été trouvées dans la zone pour les critères NAF/APE, mais aucun de leurs établissements actifs ne correspond aux tranches d'effectifs sélectionnées."
                        )
            else:  # entreprises_trouvees is None, indicating an API call failure
                st.error(
                    "La recherche d'entreprises a échoué en raison d'une erreur lors de la communication avec l'API. Vérifiez les messages d'erreur ci-dessus."
                )

        # --- Ajout automatique des nouvelles entreprises à l'ERM en session ---
        if not df_resultats.empty:  # Uniquement si des résultats de recherche existent
            # S'assurer que df_entreprises existe et a la colonne SIRET, sinon initialiser comme vide.
            if "SIRET" not in st.session_state.df_entreprises_erm.columns: # Devrait être initialisé avec les colonnes
                sirets_in_erm = pd.Series(dtype="object") # Cas de sécurité si df_entreprises_erm est mal initialisé
            else:
                sirets_in_erm = st.session_state.df_entreprises_erm["SIRET"]

            # Identifier les nouvelles entreprises
            df_new_entreprises = df_resultats[
                ~df_resultats["SIRET"].isin(sirets_in_erm)
            ].copy()  # Use .copy() to avoid SettingWithCopyWarning

            if (
                not df_new_entreprises.empty
            ):  # Si de nouvelles entreprises sont trouvées

                df_to_add = df_new_entreprises.copy()

                # S'assurer que toutes les colonnes de config.ENTREPRISES_ERM_COLS existent dans df_to_add
                # Les colonnes non présentes dans df_new_entreprises (issues de la recherche)
                # mais attendues dans l'ERM (comme 'Notes Personnelles', 'Statut Piste') seront ajoutées avec NA.
                for col in config.ENTREPRISES_ERM_COLS:
                    if col not in df_to_add.columns:
                        df_to_add[col] = pd.NA
                
                # Sélectionner et ordonner les colonnes selon config.ENTREPRISES_ERM_COLS
                df_to_add = df_to_add.reindex(columns=config.ENTREPRISES_ERM_COLS)

                st.session_state.df_entreprises_erm = pd.concat(
                    [st.session_state.df_entreprises_erm, df_to_add], ignore_index=True
                ).reindex(columns=config.ENTREPRISES_ERM_COLS) # Assurer l'ordre et la présence de toutes les colonnes ERM

                # Ensure 'Date de création Entreprise' is datetime after concatenation
                if "Date de création Entreprise" in st.session_state.df_entreprises_erm.columns:
                    st.session_state.df_entreprises_erm["Date de création Entreprise"] = pd.to_datetime(
                        st.session_state.df_entreprises_erm["Date de création Entreprise"],
                        errors='coerce'  # Convert unparseable dates to NaT
                    )

                on_erm_data_changed() # Sauvegarder les modifications

                st.success(
                    f"{len(df_new_entreprises)} nouvelle(s) entreprise(s) automatiquement ajoutée(s) à votre ERM. N'oubliez pas de sauvegarder vos modifications !"
                )
                st.session_state.editor_key_version += 1
                st.rerun()

            elif not df_resultats.empty:
                st.info(
                    "✔️ Toutes les entreprises trouvées dans cette recherche sont déjà dans votre ERM ou la recherche n'a pas retourné de nouvelles entreprises à ajouter."
                )

    # --- SECTION ERM ---


# --- AFFICHAGE PERSISTANT DES RÉSULTATS DE RECHERCHE (SI EXISTANTS) ---
with results_container:
    if (
        st.session_state.df_search_results is not None
        and not st.session_state.df_search_results.empty
        and st.session_state.search_coordinates is not None
        and st.session_state.search_radius is not None
    ):
        # Utiliser les variables de session pour afficher les résultats
        df_search_results_display = st.session_state.df_search_results
        lat_centre_display, lon_centre_display = st.session_state.search_coordinates
        radius_display = st.session_state.search_radius

        st.success(
            f"📊 {len(df_search_results_display)} établissements trouvés correspondant à tous les critères."
        )

        # Affichage Carte
        # La carte est affichée si des résultats valides (avec coordonnées) existent.
        st.subheader("Carte des établissements trouvés")
        df_map_display = df_search_results_display.dropna(
            subset=["Latitude", "Longitude", "Radius", "Color"]
        ).copy()

        if not df_map_display.empty:
            zoom_level = 11
            # Ajustement du niveau de zoom initial en fonction du rayon de recherche
            if radius_display <= 1:
                zoom_level = 14
            elif radius_display <= 5:
                zoom_level = 12
            elif radius_display <= 10:
                zoom_level = 11
            elif radius_display <= 25:
                zoom_level = 10
            else:
                zoom_level = 9

            initial_view_state = pdk.ViewState(
                latitude=lat_centre_display,
                longitude=lon_centre_display,
                zoom=zoom_level,
                pitch=0,
                bearing=0,
            )
            layer = pdk.Layer(
                "ScatterplotLayer",
                data=df_map_display,
                get_position="[Longitude, Latitude]",
                get_color="Color",
                get_radius="Radius",
                radius_min_pixels=3,
                radius_max_pixels=60,
                pickable=True,
                auto_highlight=True,
            )
            tooltip = {
                "html": "<b>{Dénomination - Enseigne}</b><br/>SIRET: {SIRET}<br/>Activité Étab.: {Activité NAF/APE Etablissement}<br/>Effectif Étab.: {Nb salariés établissement}",
                "style": {
                    "backgroundColor": "rgba(0,0,0,0.7)",
                    "color": "white",
                    "border": "1px solid white",
                    "padding": "5px",
                },
            }
            deck = pdk.Deck(
                layers=[layer],
                initial_view_state=initial_view_state,
                map_style="mapbox://styles/mapbox/light-v9",
                tooltip=tooltip,
                height=600,
            )
            st.pydeck_chart(deck)

            # Affichage Légende
            # La légende est générée dynamiquement en fonction des données affichées sur la carte.
            st.subheader("Légende")
            cols_legende = st.columns([1, 2])
            with cols_legende[0]:
                st.markdown("**Taille ≈ Effectif établissement**")
                legend_pixel_sizes = {"01": 8, "12": 12, "32": 18, "53": 24}
                base_circle_style = "display: inline-block; border-radius: 50%; background-color: #808080; margin-right: 5px; vertical-align: middle;"
                legend_sizes = {
                    "01": "Petit",
                    "12": "Moyen",
                    "32": "Grand",
                    "53": "Très Grand",
                }
                active_eff_codes = set(
                    st.session_state.selected_effectifs_codes
                )
                displayed_legend_sizes = set()
                for (
                    group_label,
                    group_codes,
                ) in config.effectifs_groupes.items():
                    if any(code in active_eff_codes for code in group_codes):
                        rep_code = next(
                            (c for c in ["01", "12", "32", "53"] if c in group_codes),
                            None,
                        )
                        if rep_code and rep_code not in displayed_legend_sizes:
                            displayed_legend_sizes.add(rep_code)
                            label = legend_sizes[rep_code]
                            pixel_size = legend_pixel_sizes.get(rep_code, 8)
                            circle_html = f'<span style="{base_circle_style} height: {pixel_size}px; width: {pixel_size}px;"></span>'
                            st.markdown(
                                f"{circle_html} {label} ({group_label})",
                                unsafe_allow_html=True,
                            )
            with cols_legende[1]:
                st.markdown("**Couleur = Secteur d'activité**")
                if "Section NAF" in df_map_display.columns:
                    sections_in_final_results = sorted(
                        list(set(df_map_display["Section NAF"].unique()) - {"N/A"})
                    )
                    if not sections_in_final_results:
                        st.caption("Aucune section NAF trouvée dans les résultats.")
                    else:
                        # Créer 3 colonnes pour la légende des couleurs NAF
                        legend_color_cols = st.columns(3)
                        col_idx_legend_color = 0
                        for letter in sections_in_final_results:
                            if letter in config.naf_sections_details:
                                # Placer chaque élément de la légende dans une colonne
                                with legend_color_cols[
                                    col_idx_legend_color % len(legend_color_cols)
                                ]:
                                    color_rgb = config.naf_color_mapping.get(
                                        letter, [128, 128, 128]
                                    )
                                    color_hex = "#%02x%02x%02x" % tuple(color_rgb)
                                    desc_legende = config.naf_sections_details[letter][
                                        "description"
                                    ]
                                    st.markdown(
                                        f"<span style='color:{color_hex}; font-size: 1.2em; display: inline-block; margin-right: 4px;'>⬤</span>{desc_legende}",  # Ajustement taille et espacement
                                        unsafe_allow_html=True,
                                    )
                                col_idx_legend_color += 1

                else:
                    st.warning(
                        "Colonne 'Section NAF' non trouvée pour la légende des couleurs."
                    )
        else:
            st.info(
                "Aucun établissement avec des coordonnées géographiques valides à afficher sur la carte."
            )

    # Les messages "aucun résultat" ou "erreur API" sont gérés dans le bloc `if lancer_recherche:`
    # car ils sont un retour direct à l'action de recherche et n'ont pas besoin de persister
    # de la même manière que la carte pour des résultats réussis après un rerun.

# --- AFFICHAGE DU TABLEAU ERM ---
# Ce tableau affiche les entreprises stockées dans st.session_state.df_entreprises_erm.
if st.session_state.df_entreprises_erm.empty:
    st.info(
        "Aucune entreprise dans votre liste pour le moment. Lancez une recherche pour en ajouter."
    )
        # The clear button is hidden if the table is already empty
else:  # df_entreprises_erm is not empty
    st.subheader("Tableau des établissements trouvés")

    # Create a copy for display modifications
    df_display_erm = st.session_state.df_entreprises_erm.copy()

    # Assurer que 'Effectif Numérique' est correctement peuplé pour le formatage de l'affichage
    # et le tri potentiel (bien que le tri ne soit pas directement implémenté ici pour l'affichage).
    if 'Code effectif établissement' in df_display_erm.columns:
        df_display_erm['Effectif Numérique'] = df_display_erm['Code effectif établissement'] \
            .map(config.effectifs_numerical_mapping) \
            .fillna(0) # Default to 0 if mapping fails or code is NA
        # Ensure it's integer type
        df_display_erm['Effectif Numérique'] = pd.to_numeric(df_display_erm['Effectif Numérique'], errors='coerce').fillna(0).astype(int)
    elif 'Effectif Numérique' not in df_display_erm.columns:
        # If 'Code effectif établissement' is also missing, and 'Effectif Numérique' is missing, create it with default
        df_display_erm['Effectif Numérique'] = 0
    else:
        # If 'Effectif Numérique' exists but 'Code effectif établissement' does not, ensure it's the correct type and fill NAs
        df_display_erm['Effectif Numérique'] = pd.to_numeric(df_display_erm['Effectif Numérique'], errors='coerce').fillna(0).astype(int)


    if 'Effectif Numérique' in df_display_erm.columns and 'Nb salariés établissement' in df_display_erm.columns:
        # Formate la colonne "Nb salariés établissement" pour l'affichage en préfixant avec une lettre basée sur l'effectif numérique.
        def format_effectif_for_display(row):
            num_val = row.get('Effectif Numérique') # Ex: 0, 1, 3, 10...
            text_val = row.get('Nb salariés établissement') # Ex: "1 ou 2 salariés"

            letter_prefix = ""
            if pd.notna(num_val):
                try:
                    # Assurer que num_val est un entier pour la clé du dictionnaire
                    num_val_int = int(num_val) 
                    letter_prefix = config.effectif_numeric_to_letter_prefix.get(num_val_int, "")
                except (ValueError, TypeError):
                    pass # Si num_val n'est pas convertible en int, letter_prefix reste ""
            
            text_upper = str(text_val).upper() if pd.notna(text_val) else "N/A"

            return f"{letter_prefix} - {text_upper}" if letter_prefix else text_upper
        
        df_display_erm['Nb salariés établissement'] = df_display_erm.apply(format_effectif_for_display, axis=1)

    # Génération des colonnes de liens pour LinkedIn, Google Maps, et Indeed.
    if "Dénomination - Enseigne" in df_display_erm.columns:
        df_display_erm["LinkedIn"] = df_display_erm["Dénomination - Enseigne"].apply(
            lambda x: f"https://www.google.com/search?q={x}+site%3Alinkedin.com"
            if pd.notna(x) and x.strip() != "" 
            else None
        )
    if (
        "Dénomination - Enseigne" in df_display_erm.columns
        and "Adresse établissement" in df_display_erm.columns
    ):
        df_display_erm["Google Maps"] = df_display_erm.apply(
            lambda row: f"https://www.google.com/maps/search/?api=1&query={row['Dénomination - Enseigne']},{row['Adresse établissement']}"
            if pd.notna(row["Dénomination - Enseigne"])
            and row["Dénomination - Enseigne"].strip() != ""
            and pd.notna(row["Adresse établissement"])
            and row["Adresse établissement"].strip() != ""
            else None,
            axis=1,
        )
        if "Dénomination - Enseigne" in df_display_erm.columns:
            df_display_erm["Indeed"] = df_display_erm[
                "Dénomination - Enseigne"
            ].apply(
                lambda x: f"https://www.google.com/search?q={x}+site%3Aindeed.com"
                if pd.notna(x) and x.strip() != ""
                else None
            )
    # Définir les colonnes à afficher et leur ordre
    # "Effectif Numérique" n'est pas affiché directement mais utilisé pour formater "Nb salariés établissement".
    display_order_base = [
        "SIRET", "Dénomination - Enseigne", 
        "Activité NAF/APE Etablissement", "Adresse établissement", 
        "Nb salariés établissement", # Colonne formatée
        "Est siège social", "Date de création Entreprise",
        "Chiffre d'Affaires Entreprise", "Résultat Net Entreprise", "Année Finances Entreprise"
    ]
    cols_to_display_erm_tab = display_order_base[:]
    
    # Insert link columns at a specific position
    link_insert_index = cols_to_display_erm_tab.index("Dénomination - Enseigne") + 1
    if "Indeed" in df_display_erm.columns and "Indeed" not in cols_to_display_erm_tab:
        cols_to_display_erm_tab.insert(link_insert_index, "Indeed")
    if "Google Maps" in df_display_erm.columns and "Google Maps" not in cols_to_display_erm_tab:
        cols_to_display_erm_tab.insert(link_insert_index, "Google Maps")
    if "LinkedIn" in df_display_erm.columns and "LinkedIn" not in cols_to_display_erm_tab:
        cols_to_display_erm_tab.insert(link_insert_index, "LinkedIn")

    cols_existantes_in_display_tab = [
        col for col in cols_to_display_erm_tab if col in df_display_erm.columns
    ]

    # Configuration des colonnes pour st.dataframe, incluant les types de colonnes et les labels.
    column_config_map = {
        "LinkedIn": st.column_config.LinkColumn("LinkedIn", display_text="🔗 LinkedIn"),
        "Google Maps": st.column_config.LinkColumn("Google Maps", display_text="📍 Google Maps"),
        "Indeed": st.column_config.LinkColumn("Indeed", display_text="🔗 Indeed"),
        "Est siège social": st.column_config.CheckboxColumn(disabled=True),
        "Date de création Entreprise": st.column_config.DateColumn(format="DD/MM/YYYY", disabled=True),
        "Chiffre d'Affaires Entreprise": st.column_config.NumberColumn(label="CA Ent.", format="%d €", disabled=True),
        "Nb salariés établissement": st.column_config.TextColumn(label="Nb salariés établissement"), # Displays the new combined string
        "Résultat Net Entreprise": st.column_config.NumberColumn(label="Rés. Net Ent.", format="%d €", disabled=True),
    }

    st.dataframe(
        df_display_erm[cols_existantes_in_display_tab],
        column_config=column_config_map,
        hide_index=True,
        use_container_width=True,
    )

# --- BOUTON DE TÉLÉCHARGEMENT ERM ---
download_button_key = "download_user_erm_excel_button"
try:
    user_erm_excel_data = data_utils.generate_user_erm_excel(
        st.session_state.df_entreprises_erm,
        st.session_state.df_contacts_erm,
        st.session_state.df_actions_erm,
    )
    st.download_button(
        label="📥 Télécharger les résultats dans un classeur Excel)",
        data=user_erm_excel_data,
        file_name=f"mon_erm_global_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=download_button_key,
    )
except Exception as e:
    st.error(f"Erreur lors de la préparation du téléchargement ERM : {e}")
st.markdown("---")
st.markdown(" Propulsé avec les API Data Gouv : [API Recherche d’Entreprises](https://www.data.gouv.fr/fr/dataservices/api-recherche-dentreprises/) & [API BAN France](https://www.data.gouv.fr/fr/dataservices/api-adresse-base-adresse-nationale-ban/)")
st.markdown("---")
# --- Bouton pour effacer le tableau des établissements ---
if not st.session_state.df_entreprises_erm.empty:
    with st.expander("Zone de danger", expanded=True):
        st.warning("Attention : Cette action effacera **toutes** les entreprises actuellement affichées dans le tableau.")
        if st.button("🗑️ Effacer le tableau des établissements", key="clear_table_button_in_danger_zone"): # Ajout d'une clé unique
            st.session_state.df_entreprises_erm = pd.DataFrame(columns=config.ENTREPRISES_ERM_COLS) # Réinitialise le DataFrame
            # Optionnel: effacer aussi contacts et actions si liés, ou laisser pour une gestion manuelle
            # st.session_state.df_contacts_erm = pd.DataFrame(columns=config.CONTACTS_ERM_COLS)
            # st.session_state.df_actions_erm = pd.DataFrame(columns=config.ACTIONS_ERM_COLS)
            on_erm_data_changed() # Sauvegarder le fait que c'est vide
            st.session_state.editor_key_version += 1 # Increment key to force editor refresh if it were used
            st.session_state.df_search_results = None # Clear search results display as well
            st.rerun() # Rerun to update the display immediately

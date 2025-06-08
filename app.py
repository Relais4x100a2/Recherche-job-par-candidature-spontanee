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

# --- ERM DATA HANDLING FUNCTIONS (REMOVED - Data is now session-only) ---
def load_global_erm_data(file_path=config.DEFAULT_ERM_FILE_PATH):
    """
    Charges les données ERM (Entreprises, Contacts, Actions) depuis un fichier JSON global.
    Initialise des DataFrames vides avec les schémas définis dans config.py si le fichier n'existe pas ou est corrompu.
    """
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Initialize with loaded data, then ensure schema and dtypes
            df_e = pd.DataFrame(data.get("entreprises", [])).reindex(columns=config.ENTREPRISES_ERM_COLS)
            df_c = pd.DataFrame(data.get("contacts", [])).reindex(columns=config.CONTACTS_ERM_COLS)
            df_a = pd.DataFrame(data.get("actions", [])).reindex(columns=config.ACTIONS_ERM_COLS)
        except (json.JSONDecodeError, KeyError) as e:
            st.error(f"Erreur de lecture ou format incorrect du fichier ERM ({file_path}): {e}. Un nouveau fichier sera utilisé/créé si des données sont sauvegardées.")
            df_e = pd.DataFrame(columns=config.ENTREPRISES_ERM_COLS).astype(config.ENTREPRISES_ERM_DTYPES)
            df_c = pd.DataFrame(columns=config.CONTACTS_ERM_COLS) # Add dtypes if defined
            df_a = pd.DataFrame(columns=config.ACTIONS_ERM_COLS)   # Add dtypes if defined
    else:
        df_e = pd.DataFrame(columns=config.ENTREPRISES_ERM_COLS).astype(config.ENTREPRISES_ERM_DTYPES)
        df_c = pd.DataFrame(columns=config.CONTACTS_ERM_COLS) # Add dtypes if defined
        df_a = pd.DataFrame(columns=config.ACTIONS_ERM_COLS)   # Add dtypes if defined

    # Apply/Ensure dtypes for df_e
    if not df_e.empty:
        for col_name, target_dtype in config.ENTREPRISES_ERM_DTYPES.items():
            if col_name in df_e.columns:
                if target_dtype == "datetime64[ns]":
                    df_e[col_name] = pd.to_datetime(df_e[col_name], errors='coerce')
                else:
                    try:
                        df_e[col_name] = df_e[col_name].astype(target_dtype)
                    except Exception as e_astype:
                        # Fallback for columns that might be all None from JSON if astype fails
                        if df_e[col_name].isnull().all():
                            df_e[col_name] = pd.Series(index=df_e.index, dtype=target_dtype)
                        else:
                            st.warning(f"Could not convert column {col_name} to {target_dtype} during load: {e_astype}")
    elif df_e.empty and not hasattr(df_e, '_is_astype_applied_custom_tag'): # Ensure dtypes for initially empty df_e
        df_e = df_e.astype(config.ENTREPRISES_ERM_DTYPES)
        df_e._is_astype_applied_custom_tag = True # Mark that astype was applied

    # TODO: Apply similar dtype logic for df_c and df_a if CONTACTS_ERM_DTYPES and ACTIONS_ERM_DTYPES are defined in config.py

    
    # This function is no longer used. Initialization happens directly in session state.
    # return df_e, df_c, df_a
    pass

def save_global_erm_data(df_e, df_c, df_a, file_path=config.DEFAULT_ERM_FILE_PATH):
    """
    Sauvegarde les DataFrames ERM (Entreprises, Contacts, Actions) dans un fichier JSON global.
    Convertit les DataFrames en dictionnaires, gérant les NaNs pour la sérialisation JSON.
    Utilise default=str pour gérer la sérialisation des objets datetime.
    """    
    # This function is no longer used. Data is not saved to a global file.
    pass

# --- INITIALISATION DE L'ÉTAT DE SESSION POUR L'AUTHENTIFICATION ET ERM ---
# print(f"{datetime.datetime.now()} - INFO - Initializing session state variables.") # Optional: uncomment for runtime debugging
# Initialisation des DataFrames ERM s'ils n'existent pas encore dans la session.
if "df_entreprises_erm" not in st.session_state:
    st.session_state.df_entreprises_erm = pd.DataFrame(columns=config.ENTREPRISES_ERM_COLS).astype(config.ENTREPRISES_ERM_DTYPES)
if "df_contacts_erm" not in st.session_state:
    st.session_state.df_contacts_erm = pd.DataFrame(columns=config.CONTACTS_ERM_COLS)
    if hasattr(config, 'CONTACTS_ERM_DTYPES') and isinstance(config.CONTACTS_ERM_DTYPES, dict) and config.CONTACTS_ERM_DTYPES:
        st.session_state.df_contacts_erm = st.session_state.df_contacts_erm.astype(config.CONTACTS_ERM_DTYPES)
if "df_actions_erm" not in st.session_state:
    st.session_state.df_actions_erm = pd.DataFrame(columns=config.ACTIONS_ERM_COLS)
    if hasattr(config, 'ACTIONS_ERM_DTYPES') and isinstance(config.ACTIONS_ERM_DTYPES, dict) and config.ACTIONS_ERM_DTYPES:
        st.session_state.df_actions_erm = st.session_state.df_actions_erm.astype(config.ACTIONS_ERM_DTYPES)
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

# === NEW SESSION STATE VARIABLES FOR SEARCH HISTORY AND VISIBILITY ===
if "past_searches" not in st.session_state:
    st.session_state.past_searches = [] # List of dicts, each representing a search
if "next_search_id" not in st.session_state:
    st.session_state.next_search_id = 0
if "global_show_all_searches" not in st.session_state:
    st.session_state.global_show_all_searches = True # Default to showing all
# === END NEW SESSION STATE VARIABLES ===

# === NEW SESSION STATE VARIABLES FOR BREAKDOWN SEARCH ===
if "show_breakdown_options" not in st.session_state:
    st.session_state.show_breakdown_options = False
if "breakdown_search_pending" not in st.session_state:
    st.session_state.breakdown_search_pending = False
if "original_search_context_for_breakdown" not in st.session_state:
    st.session_state.original_search_context_for_breakdown = None
# === END NEW SESSION STATE VARIABLES ===


# --- HELPER FUNCTION FOR VISIBLE ERM DATA ---
def get_visible_erm_data():
    """
    Filters the main ERM DataFrame (st.session_state.df_entreprises_erm)
    to include only companies from 'past_searches' marked as visible.
    Returns a DataFrame.
    """
    if not st.session_state.get("past_searches") or st.session_state.df_entreprises_erm.empty:
        # If no search history or ERM is empty, return an empty DataFrame with correct schema
        return pd.DataFrame(columns=config.ENTREPRISES_ERM_COLS).astype(config.ENTREPRISES_ERM_DTYPES)

    active_sirets = set()
    any_search_marked_visible = False
    for search_item in st.session_state.past_searches:
        if search_item.get("is_visible", True): # Default to True if 'is_visible' is missing for some reason
            active_sirets.update(search_item.get("sirets_found", set()))
            any_search_marked_visible = True

    if not any_search_marked_visible or not active_sirets:
        # If no searches are marked visible or no SIRETs collected, return empty
        return pd.DataFrame(columns=config.ENTREPRISES_ERM_COLS).astype(config.ENTREPRISES_ERM_DTYPES)

    # Filter the main ERM DataFrame
    df_visible = st.session_state.df_entreprises_erm[
        st.session_state.df_entreprises_erm["SIRET"].isin(active_sirets)
    ].copy()
    return df_visible

def create_search_params_description(adresse, radius, naf_sections, naf_specific_codes, effectifs_codes):
    """Creates a human-readable description of the search parameters."""
    params_desc_parts = [f"📍 {adresse[:25]}... ({radius}km)"]
    if naf_specific_codes:
        params_desc_parts.append(f"📂 {len(naf_specific_codes)} codes NAF spéc.")
    elif naf_sections:
        params_desc_parts.append(f"📂 Sections: {', '.join(naf_sections)}")
    params_desc_parts.append(f"📊 {len(effectifs_codes)} tranches d'eff.")
    return ", ".join(params_desc_parts)

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
    results_container.empty()  # Nettoyer les anciens messages/résultats dans ce conteneur
    st.session_state.show_breakdown_options = False # Reset flag
    st.session_state.breakdown_search_pending = False # Reset flag
    st.session_state.df_search_results = None # Clear previous results display

    # --- Address Check ---
    # print(f"{datetime.datetime.now()} - DEBUG - Lancer recherche: Address input: '{adresse_input}'")
    if not adresse_input or not adresse_input.strip():
        st.error("⚠️ Veuillez saisir une adresse de référence pour lancer la recherche.")
        st.stop()

    # --- NAF Parameter Logic ---
    final_api_params = {}
    naf_criteria_message_part = "" # For the st.info message

    has_selected_sections = bool(st.session_state.selected_naf_letters)
    has_selected_specific_codes = bool(st.session_state.selected_specific_naf_codes)

    if not has_selected_sections:
        # print(f"{datetime.datetime.now()} - DEBUG - Lancer recherche: No NAF sections selected.")
        # If no sections are selected, specific codes cannot be valid (as they are filtered by section in the UI callbacks)
        # on_section_change should clear selected_specific_naf_codes if selected_naf_letters becomes empty.
        st.error("⚠️ Veuillez sélectionner au moins une section NAF.")
        st.stop()

    if has_selected_specific_codes:
        # User has chosen specific NAF codes. These take precedence.
        # print(f"{datetime.datetime.now()} - DEBUG - Lancer recherche: Using specific NAF codes.")
        # st.session_state.selected_specific_naf_codes is already filtered by selected sections due to on_section_change.
        codes_to_use = sorted(list(st.session_state.selected_specific_naf_codes))
        
        if not codes_to_use:
            # This can happen if selected_specific_naf_codes was non-empty but then all its codes were removed
            # (e.g., by deselecting their parent sections), making it empty.
            # Fallback to pure section search if sections are still selected.
            # has_selected_sections should be true here if we passed the first check.
            sections_for_api = sorted(list(st.session_state.selected_naf_letters))
            final_api_params["section_activite_principale"] = ",".join(sections_for_api)
            
            section_descs = [f"{s} ({config.naf_sections_details.get(s, {}).get('description', 'Section')})" for s in sections_for_api]
            if len(section_descs) == 1:
                naf_criteria_message_part = f"la section NAF : {section_descs[0]}"
            else:
                naf_criteria_message_part = f"les sections NAF : {', '.join(section_descs)}"
        else:
            final_api_params["activite_principale"] = ",".join(codes_to_use)
            if len(codes_to_use) == 1:
                naf_criteria_message_part = f"le code NAF spécifique : {codes_to_use[0]}"
            else:
                display_codes = codes_to_use
                if len(display_codes) > 3: # Show first 3 and "..."
                    display_codes = display_codes[:3] + ["..."]
                naf_criteria_message_part = f"{len(codes_to_use)} codes NAF spécifiques (ex: {', '.join(display_codes)})"
    
    elif has_selected_sections: # And not has_selected_specific_codes
        # Purely section-based search
        # print(f"{datetime.datetime.now()} - DEBUG - Lancer recherche: Using NAF sections.")
        sections_for_api = sorted(list(st.session_state.selected_naf_letters))
        final_api_params["section_activite_principale"] = ",".join(sections_for_api)
        
        section_descs = [f"{s} ({config.naf_sections_details.get(s, {}).get('description', 'Section')})" for s in sections_for_api]
        if len(section_descs) == 1:
            naf_criteria_message_part = f"la section NAF : {section_descs[0]}"
        else:
            naf_criteria_message_part = f"les sections NAF : {', '.join(section_descs)}"
    else:
        # This case (no sections, no specific codes) is caught by the initial `if not has_selected_sections:`
        # print(f"{datetime.datetime.now()} - DEBUG - Lancer recherche: Invalid NAF criteria (no sections/codes).")
        st.error("⚠️ Veuillez sélectionner des critères NAF valides.")
        st.stop()

    # Check for effectifs selection (common to all NAF paths)
    if not st.session_state.selected_effectifs_codes:
        # print(f"{datetime.datetime.now()} - DEBUG - Lancer recherche: No effectifs selected.")
        st.warning("⚠️ Veuillez sélectionner au moins une tranche d'effectifs.")
        st.stop()

    # --- Début du processus dans le conteneur de résultats ---
    with results_container:
        st.info(f"Recherche en cours pour {naf_criteria_message_part}.")

        # print(f"{datetime.datetime.now()} - DEBUG - Lancer recherche: Geocoding address.")
        # 1. Géocodage
        coordonnees = geo_utils.geocoder_ban_france(adresse_input)
        if coordonnees is None:
            # L'erreur est déjà affichée par geocoder_ban_france
            st.stop()
        lat_centre, lon_centre = coordonnees

        # Get POSTAL codes in radius
        st.write(f"Recherche des codes postaux dans un rayon de {radius_input:.1f} km autour de l'adresse...")
        postal_codes_in_radius = geo_utils.get_communes_in_radius_cached(lat_centre, lon_centre, radius_input) # This now returns postal codes
        print(f"{datetime.datetime.now()} - DEBUG - Postal codes in radius: {postal_codes_in_radius}")
        
        if not postal_codes_in_radius:
            st.warning(f"Aucun code postal trouvé pour les communes dans un rayon de {radius_input:.1f} km autour de l'adresse spécifiée. Essayez un rayon plus large ou une autre adresse.")
            st.stop()
        
        st.write(f"{len(postal_codes_in_radius)} codes postaux trouvés dans le rayon. Lancement de la recherche d'entreprises pour ces codes postaux...")

        # Prepare API params for the client function
        # `final_api_params` currently holds NAF criteria. Add effectifs.
        if st.session_state.selected_effectifs_codes:
            final_api_params["tranche_effectif_salarie"] = ",".join(st.session_state.selected_effectifs_codes)
        else:
            # This should have been caught earlier by the UI check, but as a safeguard:
            st.error("⚠️ Aucune tranche d'effectifs sélectionnée.") 
            st.stop()

        print(f"{datetime.datetime.now()} - DEBUG - Calling API client with postal_codes: {postal_codes_in_radius}, api_params: {final_api_params}")
        # 2. Lancer la recherche API
        # The api_client function will use st.status internally
        api_response = api_client.rechercher_entreprises_par_localisation_et_criteres(
            postal_codes_in_radius,
            final_api_params, # Contains NAF and effectifs
            force_full_fetch=False,
            code_type="postal"
        )

        if isinstance(api_response, dict) and api_response.get("status_code") == "NEEDS_USER_CONFIRMATION_OR_BREAKDOWN":
            # print(f"{datetime.datetime.now()} - DEBUG - Lancer recherche: API response needs user confirmation/breakdown.")
            st.session_state.original_search_context_for_breakdown = {
                "localisation_codes": postal_codes_in_radius, # List of all postal codes for the search area
                "code_type": "postal", # Store the type of code used
                "page1_results": api_response["page1_results"], # Results from the first batch of communes
                "total_pages_estimated": api_response["total_pages_estimated"], # Estimation for that first batch
                "total_results_estimated": api_response["total_results_estimated"], # Estimation for that first batch
                "original_query_params": api_response["original_query_params"], # Params used for that first batch (includes NAF, effectifs, and its specific commune codes)
                "user_address": adresse_input, # Store original user inputs for context
                "user_radius": radius_input,
                "user_lat_lon": (lat_centre, lon_centre)
            }
            st.session_state.show_breakdown_options = True
            st.rerun() # Rerun to show breakdown options UI

        elif isinstance(api_response, list): # Normal successful search (not too large, or already processed)
            # print(f"{datetime.datetime.now()} - DEBUG - Lancer recherche: API response is a list (normal search).")
            entreprises_trouvees_list = api_response # Renamed to avoid conflict
            df_resultats = data_utils.traitement_reponse_api( # This function filters by effectifs again, which is fine as a safeguard
                entreprises_trouvees_list, st.session_state.selected_effectifs_codes
            )

            st.session_state.df_search_results = df_resultats.copy() if not df_resultats.empty else pd.DataFrame()
            st.session_state.search_coordinates = (lat_centre, lon_centre)
            st.session_state.search_radius = radius_input

            # --- Track search in history ---
            if not df_resultats.empty:
                st.session_state.next_search_id += 1
                search_id = st.session_state.next_search_id
                sirets_in_this_query = set(df_resultats["SIRET"].unique())
                
                params_desc = create_search_params_description(
                    adresse_input, radius_input, 
                    st.session_state.selected_naf_letters, 
                    st.session_state.selected_specific_naf_codes, 
                    st.session_state.selected_effectifs_codes
                )
                new_search_entry = {
                    "id": search_id, "timestamp": datetime.datetime.now(),
                    "params_desc": params_desc, "sirets_found": sirets_in_this_query,
                    "num_total_found_by_query": len(df_resultats), "is_visible": True,
                }
                st.session_state.past_searches.insert(0, new_search_entry)


            if not entreprises_trouvees_list: # API returned empty list
                 st.info("Aucune entreprise trouvée pour les critères spécifiés après la recherche complète.")
            elif df_resultats.empty and entreprises_trouvees_list: # API had results, but filtering by effectifs yielded none
                 st.info("Des entreprises ont été trouvées pour les critères NAF/géographiques, mais aucune ne correspond aux tranches d'effectifs sélectionnées.")

            # --- Ajout automatique des nouvelles entreprises à l'ERM en session ---
            if not df_resultats.empty:
                if "SIRET" not in st.session_state.df_entreprises_erm.columns:
                    sirets_in_erm = pd.Series(dtype="object")
                else:
                    sirets_in_erm = st.session_state.df_entreprises_erm["SIRET"]

                df_new_entreprises = df_resultats[~df_resultats["SIRET"].isin(sirets_in_erm)].copy()

                if not df_new_entreprises.empty:
                    # Prepare df_to_add with the correct schema and dtypes
                    current_df_to_add = pd.DataFrame(index=df_new_entreprises.index)
                    for col_erm in config.ENTREPRISES_ERM_COLS:
                        if col_erm in df_new_entreprises.columns:
                            current_df_to_add[col_erm] = df_new_entreprises[col_erm]
                        else:
                            current_df_to_add[col_erm] = pd.NA
                    
                    for col_name, dtype_val in config.ENTREPRISES_ERM_DTYPES.items():
                        if col_name in current_df_to_add.columns:
                            if dtype_val == "datetime64[ns]":
                                current_df_to_add[col_name] = pd.to_datetime(current_df_to_add[col_name], errors='coerce')
                            else:
                                current_df_to_add[col_name] = current_df_to_add[col_name].astype(dtype_val)
                    df_to_add = current_df_to_add.reset_index(drop=True)

                    st.session_state.df_entreprises_erm = pd.concat(
                        [st.session_state.df_entreprises_erm, df_to_add], ignore_index=True
                    ).reindex(columns=config.ENTREPRISES_ERM_COLS)
                    st.success(
                        f"{len(df_new_entreprises)} nouvelle(s) entreprise(s) automatiquement ajoutée(s) à votre ERM."
                    )
                    st.session_state.editor_key_version += 1
                    # st.rerun() # Rerun might be too disruptive here, results will show anyway
                elif not df_resultats.empty: # Results found, but all already in ERM
                    st.info("✔️ Toutes les entreprises trouvées dans cette recherche sont déjà dans votre ERM.")
            # No rerun here, let the main flow display results from session_state

        elif api_response is None: # Critical error from API client (e.g. page 1 failed)
            # print(f"{datetime.datetime.now()} - DEBUG - Lancer recherche: API response is None (critical error).")
            # Error message should have been displayed by api_client's st.status
            st.error("Erreur critique lors de la recherche. Vérifiez les messages ci-dessus.")
            st.session_state.df_search_results = None # Ensure no stale results are shown
        
        else: # Other unexpected response type
            # print(f"{datetime.datetime.now()} - DEBUG - Lancer recherche: API response is unexpected type.")
            st.error("Une erreur inattendue est survenue lors de la recherche.")
            st.session_state.df_search_results = None
        
        # If not a breakdown scenario that reruns, the script continues to display results from session_state
        if not st.session_state.get("show_breakdown_options", False):
            st.rerun() # Rerun to make sure the results display section picks up changes


# --- UI FOR BREAKDOWN OPTIONS ---
if st.session_state.get("show_breakdown_options", False):
    with results_container: # Or a dedicated container for these options
        context = st.session_state.original_search_context_for_breakdown
        st.warning(
            f"⚠️ Votre recherche initiale a retourné une estimation de {context['total_results_estimated']} résultats sur {context['total_pages_estimated']} pages. "
            "Cela dépasse les limites pratiques pour une récupération directe."
        )
        st.markdown(
            "Pour une exploration plus ciblée et pour vous assurer de ne pas manquer d'entreprises pertinentes :"
            "\n- **Affinez vos critères** (réduire le rayon, spécifier davantage les codes NAF) et relancez une recherche."
            "\n- Ou, **lancez une recherche décomposée** : l'application tentera de récupérer les résultats par sous-ensembles (par exemple, par section NAF). Cela peut prendre du temps !"
        )

        col1_breakdown, col2_breakdown = st.columns(2)
        with col1_breakdown:
            if st.button("💡 Affiner mes critères de recherche", type="secondary", key="refine_criteria_btn", use_container_width=True):
                st.session_state.show_breakdown_options = False
                # User can now change inputs and click the main "🚀 Rechercher" button again.
                st.rerun()
        with col2_breakdown:
            if st.button("⚙️ Lancer la recherche décomposée", type="secondary", key="proceed_breakdown_btn", use_container_width=True):
                st.session_state.show_breakdown_options = False
                st.session_state.breakdown_search_pending = True
                st.rerun()

# --- LOGIC FOR PERFORMING THE BREAKDOWN SEARCH ---
if st.session_state.get("breakdown_search_pending", False):
    context = st.session_state.original_search_context_for_breakdown
    
    # These are from the *first batch* of the initial call if it triggered breakdown
    # `original_query_params_from_first_batch` contains NAF, effectifs, and the first batch of commune codes.
    original_query_params_from_first_batch = context["original_query_params"] 
    
    # The list of ALL localisation codes (postal codes in this case) for the breakdown search
    localisation_codes_for_breakdown = context["localisation_codes"]
    code_type_for_breakdown = context["code_type"]

    all_breakdown_results_list = []

    # Add page 1 results from the initial broad query
    if context["page1_results"]:
        sirens_of_companies_added_from_initial_page1 = set()
        for company_item_initial_p1 in context["page1_results"]:
            siren_company_initial_p1 = company_item_initial_p1.get("siren")
            company_had_new_etab_initial_p1 = False
            # Simplified: just add the company object. Deduplication by SIREN will happen at the end.
            all_breakdown_results_list.append(company_item_initial_p1)
    # print(f"{datetime.datetime.now()} - DEBUG - Breakdown: Added {len(context.get('page1_results', []))} results from initial page 1 of first batch.")
    
    # Determine NAF criteria to iterate for breakdown (same as before, but based on params of the first batch)
    naf_criteria_to_iterate = []
    naf_param_key_used = None
    naf_values_string_original = None

    if "section_activite_principale" in original_query_params_from_first_batch:
        naf_param_key_used = "section_activite_principale"
        naf_values_string_original = original_query_params_from_first_batch[naf_param_key_used]
    elif "activite_principale" in original_query_params_from_first_batch:
        naf_param_key_used = "activite_principale"
        naf_values_string_original = original_query_params_from_first_batch[naf_param_key_used]

    if naf_param_key_used and naf_values_string_original:
        individual_naf_values = naf_values_string_original.split(',')
        if len(individual_naf_values) > 1:
            for val in individual_naf_values:
                naf_criteria_to_iterate.append({naf_param_key_used: val.strip()})
        else: # Single NAF value initially, or became single after some processing
            naf_criteria_to_iterate.append({naf_param_key_used: naf_values_string})
    else: # No NAF filter in original query, or it was empty.
          # We'll run the original query with force_full_fetch=True.
          # This means no NAF key will be in naf_criterion_map for this iteration.
        naf_criteria_to_iterate.append({}) 

    with results_container: # Display progress within the results container
        st.info(f"Lancement de la recherche décomposée par critère NAF sur {len(localisation_codes_for_breakdown)} codes {code_type_for_breakdown} ({len(naf_criteria_to_iterate)} sous-ensemble(s) NAF)...")
        
        # Clear rate limit timestamps once before the batch of breakdown calls
        with api_client.rate_limit_lock:
            api_client.request_timestamps.clear()
            # print(f"{datetime.datetime.now()} - DEBUG - Request timestamps deque cleared for breakdown search batch.")

        for i, naf_criterion_map_for_subset in enumerate(naf_criteria_to_iterate):
            # Params for this NAF subset, to be applied to ALL communes
            current_subset_api_params_for_client = {
                # Copy effectifs from original params (of the first batch)
                k: v for k, v in original_query_params_from_first_batch.items() if k == "tranche_effectif_salarie"
            }
            
            if not naf_criterion_map_for_subset: # Original NAF criteria (could be empty if no NAF was set)
                if "activite_principale" in original_query_params_from_first_batch:
                    current_subset_api_params_for_client["activite_principale"] = original_query_params_from_first_batch["activite_principale"]
                if "section_activite_principale" in original_query_params_from_first_batch:
                     current_subset_api_params_for_client["section_activite_principale"] = original_query_params_from_first_batch["section_activite_principale"]
            else: # Specific NAF criterion for this iteration
                current_subset_api_params_for_client.update(naf_criterion_map_for_subset)


            desc_critere_naf = ", ".join([f"{k}={v}" for k,v in current_subset_api_params_for_client.items() if k.startswith("activite") or k.startswith("section")])
            if not desc_critere_naf: desc_critere_naf = "tous NAF sélectionnés initialement"
            st.markdown(f"--- \n**Sous-recherche NAF {i+1}/{len(naf_criteria_to_iterate)} : {desc_critere_naf}** (sur tous les codes {code_type_for_breakdown})")
            # print(f"{datetime.datetime.now()} - DEBUG - Breakdown by NAF: {desc_critere_naf}")
            # print(f"{datetime.datetime.now()} - DEBUG - Breakdown sub-search {i+1}: Params for API client: {current_subset_api_params_for_client}")
            
            # This call will iterate through localisation_codes_for_breakdown in batches internally
            subset_results_list = api_client.rechercher_entreprises_par_localisation_et_criteres(
                localisation_codes_for_breakdown,
                current_subset_api_params_for_client, # NAF + effectifs for this NAF subset
                force_full_fetch=True,
                code_type=code_type_for_breakdown
            )

            # The `rechercher_entreprises_par_communes_et_criteres` returns a list of "entreprise" objects
            # or the "NEEDS_BREAKDOWN" dict if the *first batch of its internal commune loop* was too large.
            # Since `force_full_fetch=True` here, it should always return a list (or None for critical error).
            if isinstance(subset_results_list, list):
                all_breakdown_results_list.extend(subset_results_list)
                # print(f"{datetime.datetime.now()} - DEBUG - Breakdown by NAF: Added {len(subset_results_list)} items from NAF subset {desc_critere_naf}.")
            elif isinstance(subset_results_list, dict) and subset_results_list.get("status_code") == "NEEDS_USER_CONFIRMATION_OR_BREAKDOWN":
                # This is an edge case: a NAF-specific query, across multiple communes, where the *first commune batch* was still too large,
                # even with force_full_fetch=True (which means it hit API_MAX_PAGES for that batch).
                # We should take its page1_results for this NAF subset.
                st.warning(f"La sous-recherche NAF {desc_critere_naf} pour le premier lot de communes était encore très volumineuse (même avec force_full_fetch). Seuls les premiers résultats de ce lot sont inclus pour ce critère NAF.")
                if subset_results_list.get("page1_results"):
                    all_breakdown_results_list.extend(subset_results_list.get("page1_results"))
            elif subset_results_list is None: # Critical error from API client for this NAF subset
                st.error(f"Erreur critique lors de la sous-recherche NAF pour {desc_critere_naf}.")
        
        st.markdown("--- \n**Fin de la recherche décomposée par NAF.**")
        st.session_state.breakdown_search_pending = False
        # print(f"{datetime.datetime.now()} - DEBUG - Breakdown by NAF: Completed. Total items before final deduplication: {len(all_breakdown_results_list)}")
        
        if all_breakdown_results_list:
            # Deduplicate `all_breakdown_results_list` by SIREN, merging matching_etablissements
            unique_entreprises_by_siren_bd = {}
            for entreprise_obj_bd in all_breakdown_results_list:
                siren_bd = entreprise_obj_bd.get("siren")
                if siren_bd:
                    if siren_bd not in unique_entreprises_by_siren_bd:
                        entreprise_obj_bd["matching_etablissements"] = entreprise_obj_bd.get("matching_etablissements") or []
                        unique_entreprises_by_siren_bd[siren_bd] = entreprise_obj_bd
                    else: # Merge matching_etablissements
                        existing_etabs_sirets_bd = {
                            etab_bd.get("siret") for etab_bd in unique_entreprises_by_siren_bd[siren_bd].get("matching_etablissements", []) if etab_bd.get("siret")
                        }
                        new_etabs_to_add_bd = [
                            new_etab_bd for new_etab_bd in entreprise_obj_bd.get("matching_etablissements", [])
                            if new_etab_bd.get("siret") and new_etab_bd.get("siret") not in existing_etabs_sirets_bd
                        ]
                        if new_etabs_to_add_bd:
                            unique_entreprises_by_siren_bd[siren_bd]["matching_etablissements"].extend(new_etabs_to_add_bd)
                else: # Should be rare
                    unique_entreprises_by_siren_bd[f"no_siren_{len(unique_entreprises_by_siren_bd)}"] = entreprise_obj_bd
            
            deduplicated_entreprise_list_bd = list(unique_entreprises_by_siren_bd.values())
            # print(f"{datetime.datetime.now()} - DEBUG - Breakdown by NAF: Deduplicated 'entreprise' items: {len(deduplicated_entreprise_list_bd)}")

            df_final_results = data_utils.traitement_reponse_api(
                deduplicated_entreprise_list_bd, 
                st.session_state.selected_effectifs_codes # This is now mostly for data transformation, not primary filtering
            )
            st.session_state.df_search_results = df_final_results.copy() if not df_final_results.empty else pd.DataFrame()
            st.session_state.search_coordinates = context.get("user_lat_lon") # Original center for map
            st.session_state.search_radius = context.get("user_radius") # Original radius for map context
            
            # --- Track breakdown search in history ---
            if not df_final_results.empty:
                st.session_state.next_search_id += 1
                search_id_bd = st.session_state.next_search_id
                sirets_in_bd_query = set(df_final_results["SIRET"].unique())
                # For breakdown, params_desc might be more complex or refer to the original broad search
                params_desc_bd = f"Recherche décomposée (basée sur: {context.get('user_address','')[:25]}...)"
                
                new_search_entry_bd = {
                    "id": search_id_bd, "timestamp": datetime.datetime.now(),
                    "params_desc": params_desc_bd, "sirets_found": sirets_in_bd_query,
                    "num_total_found_by_query": len(df_final_results), "is_visible": True,
                }
                st.session_state.past_searches.insert(0, new_search_entry_bd)


            # Add new results from breakdown to ERM
            if not df_final_results.empty:
                if "SIRET" not in st.session_state.df_entreprises_erm.columns:
                    sirets_in_erm_bd = pd.Series(dtype="object")
                else:
                    sirets_in_erm_bd = st.session_state.df_entreprises_erm["SIRET"]
                df_new_entreprises_bd = df_final_results[~df_final_results["SIRET"].isin(sirets_in_erm_bd)].copy()
                
                if not df_new_entreprises_bd.empty:
                    # Prepare df_to_add_bd with the correct schema and dtypes
                    current_df_to_add_bd = pd.DataFrame(index=df_new_entreprises_bd.index)
                    for col_erm_bd in config.ENTREPRISES_ERM_COLS:
                        if col_erm_bd in df_new_entreprises_bd.columns:
                            current_df_to_add_bd[col_erm_bd] = df_new_entreprises_bd[col_erm_bd]
                        else:
                            current_df_to_add_bd[col_erm_bd] = pd.NA
                    for col_name_bd, dtype_val_bd in config.ENTREPRISES_ERM_DTYPES.items():
                        if col_name_bd in current_df_to_add_bd.columns:
                            if dtype_val_bd == "datetime64[ns]":
                                current_df_to_add_bd[col_name_bd] = pd.to_datetime(current_df_to_add_bd[col_name_bd], errors='coerce')
                            else:
                                current_df_to_add_bd[col_name_bd] = current_df_to_add_bd[col_name_bd].astype(dtype_val_bd)
                    df_to_add_bd = current_df_to_add_bd.reset_index(drop=True)

                    st.session_state.df_entreprises_erm = pd.concat(
                        [st.session_state.df_entreprises_erm, df_to_add_bd], ignore_index=True
                    ).reindex(columns=config.ENTREPRISES_ERM_COLS)
                    st.success(f"{len(df_new_entreprises_bd)} nouvelle(s) entreprise(s) issue(s) de la recherche décomposée ajoutée(s) à l'ERM.")
                    st.session_state.editor_key_version += 1

            st.success(f"Recherche décomposée terminée. {len(df_final_results) if not df_final_results.empty else 0} établissements uniques trouvés au total.")
        else:
            # print(f"{datetime.datetime.now()} - DEBUG - Breakdown search: No results from breakdown.")
            st.info("La recherche décomposée n'a retourné aucun résultat.")
            st.session_state.df_search_results = pd.DataFrame()

        st.rerun()

# --- UI FOR MANAGING PAST SEARCHES ---
with st.sidebar.expander("⚙️ Gérer l'historique et l'affichage des recherches", expanded=True):
    if not st.session_state.past_searches:
        st.caption("Aucune recherche dans l'historique.")
    else:
        # Toggle all visibility
        # Check current state of all individual toggles to set the 'master' toggle
        all_currently_visible_in_ui = all(s.get("is_visible", True) for s in st.session_state.past_searches)

        def toggle_all_visibility_callback():
            new_master_state = st.session_state.toggle_all_visibility_cb
            for i in range(len(st.session_state.past_searches)):
                st.session_state.past_searches[i]["is_visible"] = new_master_state
            # No st.rerun() here, it's handled by Streamlit due to on_change

        st.checkbox(
            "Afficher/Masquer toutes les recherches",
            value=all_currently_visible_in_ui,
            key="toggle_all_visibility_cb",
            on_change=toggle_all_visibility_callback,
            help="Cochez pour afficher les résultats de toutes les recherches, décochez pour masquer."
        )
        st.markdown("---")

        for search_item in st.session_state.past_searches:
            search_id_hist = search_item["id"]
            # Find the item in session_state by ID to ensure we're working with the current version
            # This is important because st.rerun() might cause the list to be rebuilt if not careful
            current_search_item_in_state = next((s for s in st.session_state.past_searches if s["id"] == search_id_hist), None)
            if not current_search_item_in_state:
                continue # Should not happen if list is managed correctly

            item_is_visible = current_search_item_in_state.get("is_visible", True)

            col_info, col_toggle, col_remove = st.columns([4,1,1])
            with col_info:
                st.markdown(
                    f"<small>**Recherche {search_id_hist}** ({current_search_item_in_state['timestamp']:%d/%m %H:%M}):<br>"
                    f"{current_search_item_in_state['params_desc']}<br>"
                    f"({current_search_item_in_state['num_total_found_by_query']} résultats)</small>",
                    unsafe_allow_html=True
                )
            
            with col_toggle:
                # Callback for individual toggle
                def individual_toggle_callback(sid):
                    for i_s_cb, s_cb_item in enumerate(st.session_state.past_searches):
                        if s_cb_item["id"] == sid:
                            st.session_state.past_searches[i_s_cb]["is_visible"] = st.session_state[f"visible_search_cb_{sid}"]
                            break
                
                st.checkbox(
                    "Afficher",
                    value=item_is_visible,
                    key=f"visible_search_cb_{search_id_hist}",
                    label_visibility="collapsed",
                    on_change=individual_toggle_callback,
                    args=(search_id_hist,)
                )

            with col_remove:
                if st.button("🗑️", key=f"remove_search_btn_{search_id_hist}", help="Oublier cette recherche et ses résultats uniques."):
                    # --- Removal Logic ---
                    search_to_remove_obj = None
                    # Find the object to remove by its ID
                    for s_obj_rem in st.session_state.past_searches:
                        if s_obj_rem["id"] == search_id_hist:
                            search_to_remove_obj = s_obj_rem
                            break
                    
                    if search_to_remove_obj:
                        sirets_from_removed_query = search_to_remove_obj.get("sirets_found", set())
                        
                        # Collect SIRETs from all *other remaining* searches
                        sirets_from_other_remaining_queries = set()
                        for other_s_rem in st.session_state.past_searches:
                            if other_s_rem["id"] != search_id_hist: # Exclude the one being removed
                                sirets_from_other_remaining_queries.update(other_s_rem.get("sirets_found", set()))
                        
                        # Determine SIRETs that were *only* found by the search being removed
                        sirets_to_delete_from_erm_master = sirets_from_removed_query - sirets_from_other_remaining_queries
                        
                        # Remove these unique SIRETs from the master ERM DataFrame
                        if sirets_to_delete_from_erm_master and not st.session_state.df_entreprises_erm.empty:
                            st.session_state.df_entreprises_erm = st.session_state.df_entreprises_erm[
                                ~st.session_state.df_entreprises_erm["SIRET"].isin(sirets_to_delete_from_erm_master)
                            ]
                            st.toast(f"{len(sirets_to_delete_from_erm_master)} entreprise(s) unique(s) à cette recherche ont été retirée(s) de l'ERM.")
                        
                        # Remove the search entry itself from past_searches
                        st.session_state.past_searches = [s_f_rem for s_f_rem in st.session_state.past_searches if s_f_rem["id"] != search_id_hist]
                        
                        st.session_state.editor_key_version +=1 # if using data_editor for ERM
                        st.rerun()
            st.markdown("---")



# --- AFFICHAGE PERSISTANT DES RÉSULTATS DE RECHERCHE (SI EXISTANTS) ---
with results_container: # This container is now also used by breakdown logic for its messages
    # Check if there are results to display from session_state
    # This section will render after a normal search, or after a breakdown search completes.
    # It will also render if show_breakdown_options is true, but the map/table won't show then.
    
    # Determine what to display based on visible searches
    # df_results_to_show_on_map_and_summary is based on the *last search that produced results*
    # or could be an aggregation if we change that logic. For now, let's use st.session_state.df_search_results
    # for the summary count and map centering, but the actual points on map come from get_visible_erm_data().
        
    if not st.session_state.get("show_breakdown_options", False) and \
       not st.session_state.get("breakdown_search_pending", False) and \
       st.session_state.search_coordinates is not None: # Check for coordinates as a proxy for a completed search display

        df_visible_for_map_and_summary = get_visible_erm_data()

        if not df_visible_for_map_and_summary.empty and \
           st.session_state.search_coordinates is not None and \
           st.session_state.search_radius is not None:
            
            # Utiliser les variables de session pour afficher les résultats
            # The summary count should reflect what's currently visible from all active searches
            df_search_results_display_count = len(df_visible_for_map_and_summary)

            lat_centre_display, lon_centre_display = st.session_state.search_coordinates
            radius_display = st.session_state.search_radius

            st.success(
            f"📊 {df_search_results_display_count} établissement(s) actuellement visible(s) sur la carte et dans l'ERM."
            )

            # Affichage Carte
            st.subheader("Carte des établissements trouvés")
            # Use the globally visible data for the map points
            df_map_points = df_visible_for_map_and_summary.dropna(
                subset=["Latitude", "Longitude", "Radius", "Color"]
            ).copy()

            if not df_map_points.empty:
                zoom_level = 11
                if radius_display <= 1: zoom_level = 14
                elif radius_display <= 5: zoom_level = 12
                elif radius_display <= 10: zoom_level = 11
                elif radius_display <= 25: zoom_level = 10
                else: zoom_level = 9

                initial_view_state = pdk.ViewState(
                    latitude=lat_centre_display, longitude=lon_centre_display,
                    zoom=zoom_level, pitch=0, bearing=0,
                )
                layer = pdk.Layer(
                    "ScatterplotLayer", data=df_map_points,
                    get_position="[Longitude, Latitude]", get_color="Color", get_radius="Radius",
                    radius_min_pixels=3, radius_max_pixels=60,
                    pickable=True, auto_highlight=True,
                )
                tooltip = {
                    "html": "<b>{Dénomination - Enseigne}</b><br/>SIRET: {SIRET}<br/>Activité Étab.: {Activité NAF/APE Etablissement}<br/>Effectif Étab.: {Nb salariés établissement}",
                    "style": {"backgroundColor": "rgba(0,0,0,0.7)", "color": "white", "border": "1px solid white", "padding": "5px"},
                }
                deck = pdk.Deck(
                    layers=[layer], initial_view_state=initial_view_state,
                    map_style="mapbox://styles/mapbox/light-v9", tooltip=tooltip, height=600,
                )
                st.pydeck_chart(deck)

                # Affichage Légende
                st.subheader("Légende")
                cols_legende = st.columns([1, 2])
                with cols_legende[0]:
                    st.markdown("**Taille ≈ Effectif établissement**")
                    legend_pixel_sizes = {"01": 8, "12": 12, "32": 18, "53": 24}
                    base_circle_style = "display: inline-block; border-radius: 50%; background-color: #808080; margin-right: 5px; vertical-align: middle;"
                    legend_sizes = {"01": "Petit", "12": "Moyen", "32": "Grand", "53": "Très Grand"}
                    active_eff_codes = set(st.session_state.selected_effectifs_codes)
                    displayed_legend_sizes = set()
                    for group_label, group_details in config.effectifs_groupes_details.items(): # Use groupes_details
                        group_codes = group_details["codes"]
                        if any(code in active_eff_codes for code in group_codes):
                            rep_code = next((c for c in ["01", "12", "32", "53"] if c in group_codes), None)
                            if rep_code and rep_code not in displayed_legend_sizes:
                                displayed_legend_sizes.add(rep_code)
                                label = legend_sizes[rep_code]
                                pixel_size = legend_pixel_sizes.get(rep_code, 8)
                                circle_html = f'<span style="{base_circle_style} height: {pixel_size}px; width: {pixel_size}px;"></span>'
                                st.markdown(f"{circle_html} {label} ({group_details['label']})", unsafe_allow_html=True)
                with cols_legende[1]:
                    st.markdown("**Couleur = Secteur d'activité**")
                    if "Section NAF" in df_map_points.columns:
                        sections_in_final_results = sorted(list(set(df_map_points["Section NAF"].unique()) - {"N/A"}))
                        if not sections_in_final_results:
                            st.caption("Aucune section NAF trouvée dans les résultats.")
                        else:
                            legend_color_cols = st.columns(3)
                            col_idx_legend_color = 0
                            for letter in sections_in_final_results:
                                if letter in config.naf_sections_details:
                                    with legend_color_cols[col_idx_legend_color % len(legend_color_cols)]:
                                        color_rgb = config.naf_color_mapping.get(letter, [128, 128, 128])
                                        color_hex = "#%02x%02x%02x" % tuple(color_rgb)
                                        desc_legende = config.naf_sections_details[letter]["description"]
                                        st.markdown(f"<span style='color:{color_hex}; font-size: 1.2em; display: inline-block; margin-right: 4px;'>⬤</span>{desc_legende}", unsafe_allow_html=True)
                                    col_idx_legend_color += 1
                    else:
                        st.warning("Colonne 'Section NAF' non trouvée pour la légende des couleurs.")
            else: # df_map_display is empty
                st.info("Aucun établissement avec des coordonnées géographiques valides à afficher sur la carte.")
        
        elif df_visible_for_map_and_summary.empty and st.session_state.past_searches:
            st.info("Aucun établissement à afficher. Vérifiez les filtres de visibilité dans 'Gérer l'historique...' ou lancez une nouvelle recherche.")
        elif not st.session_state.past_searches : # No searches yet, or all cleared
            # This message is now handled by the ERM table display logic below if df_entreprises_erm is also empty
            pass


# --- AFFICHAGE DU TABLEAU ERM ---
# Ce tableau affiche les entreprises stockées dans st.session_state.df_entreprises_erm.
df_display_erm_filtered = get_visible_erm_data()

if df_display_erm_filtered.empty:
    st.info(
        "Aucune entreprise à afficher. Lancez une recherche pour en ajouter, "
        "ou vérifiez les filtres de visibilité dans 'Gérer l'historique...'."
    )
        # The clear button is hidden if the table is already empty
else:  # df_entreprises_erm is not empty
    st.subheader("Tableau des établissements trouvés")

    # Create a copy for display modifications
    df_display_erm_processed = df_display_erm_filtered.copy()

    # Assurer que 'Effectif Numérique' est correctement peuplé pour le formatage de l'affichage
    # et le tri potentiel (bien que le tri ne soit pas directement implémenté ici pour l'affichage).
    if 'Code effectif établissement' in df_display_erm_processed.columns:
        df_display_erm_processed['Effectif Numérique'] = df_display_erm_processed['Code effectif établissement'] \
           .map(config.effectifs_numerical_mapping) \
            .fillna(0) # Default to 0 if mapping fails or code is NA
        # Ensure it's integer type
        df_display_erm_processed['Effectif Numérique'] = pd.to_numeric(df_display_erm_processed['Effectif Numérique'], errors='coerce').fillna(0).astype(int)
    elif 'Effectif Numérique' not in df_display_erm_processed.columns:
        # If 'Code effectif établissement' is also missing, and 'Effectif Numérique' is missing, create it with default
        df_display_erm_processed['Effectif Numérique'] = 0
    else:
        # If 'Effectif Numérique' exists but 'Code effectif établissement' does not, ensure it's the correct type and fill NAs
        df_display_erm_processed['Effectif Numérique'] = pd.to_numeric(df_display_erm_processed['Effectif Numérique'], errors='coerce').fillna(0).astype(int)


    if 'Effectif Numérique' in df_display_erm_processed.columns and 'Nb salariés établissement' in df_display_erm_processed.columns:
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
        
        df_display_erm_processed['Nb salariés établissement'] = df_display_erm_processed.apply(format_effectif_for_display, axis=1)

    # Helper function to generate Google search URLs
    def generate_google_search_url(name, location_param, term, use_site_specific=False):
        if pd.isna(name) or str(name).strip() == "":
            return None
        
        name_cleaned = str(name).strip()
        query_parts = [name_cleaned]

        if pd.notna(location_param) and str(location_param).strip() != "":
            query_parts.append(str(location_param).strip())
        
        if use_site_specific: # For old Indeed/LinkedIn style with site:
            query_parts.append(f"site%3A{term}.com")
            search_query = "+".join(query_parts)
        else: # For new style with location and term
            query_parts.append(term)
            search_query = "+".join(query_parts)
            
        return f"https://www.google.com/search?q={search_query}"

    # Génération des colonnes de liens
    if "Dénomination - Enseigne" in df_display_erm_processed.columns and "Commune" in df_display_erm_processed.columns:
        df_display_erm_processed["LinkedIn"] = df_display_erm_processed.apply(
            lambda row: generate_google_search_url(row.get("Dénomination - Enseigne"), row.get("Commune"), "linkedin"),
            axis=1
        )
        df_display_erm_processed["Emploi"] = df_display_erm_processed.apply(
            lambda row: generate_google_search_url(row.get("Dénomination - Enseigne"), row.get("Commune"), "emploi"),
            axis=1
        )

    if "Dénomination - Enseigne" in df_display_erm_processed.columns and "Adresse établissement" in df_display_erm_processed.columns:
        df_display_erm_processed["Google Maps"] = df_display_erm_processed.apply(
            lambda row: f"https://www.google.com/maps/search/?api=1&query={row['Dénomination - Enseigne']},{row['Adresse établissement']}"
            if pd.notna(row["Dénomination - Enseigne"])
            and row["Dénomination - Enseigne"].strip() != ""
            and pd.notna(row["Adresse établissement"])
            and row["Adresse établissement"].strip() != ""
            else None,
            axis=1,
        )

    # Définir les colonnes à afficher et leur ordre
    # "Effectif Numérique" n'est pas affiché directement mais utilisé pour formater "Nb salariés établissement".
    display_order_base = [
        "SIRET", "Dénomination - Enseigne", 
        "Activité NAF/APE Etablissement", "Adresse établissement", "Commune",
        "Nb salariés établissement", # Colonne formatée
        "Est siège social", "Date de création Entreprise"
        # "Chiffre d'Affaires Entreprise", "Résultat Net Entreprise", "Année Finances Entreprise" # Removed for brevity
    ]
    cols_to_display_erm_tab = display_order_base[:]
    
    # Insert link columns at a specific position
    link_insert_index = cols_to_display_erm_tab.index("Dénomination - Enseigne") + 1
    if "Emploi" in df_display_erm_processed.columns and "Emploi" not in cols_to_display_erm_tab:
        cols_to_display_erm_tab.insert(link_insert_index, "Emploi")
    if "Google Maps" in df_display_erm_processed.columns and "Google Maps" not in cols_to_display_erm_tab:
        cols_to_display_erm_tab.insert(link_insert_index, "Google Maps")
    if "LinkedIn" in df_display_erm_processed.columns and "LinkedIn" not in cols_to_display_erm_tab:
        cols_to_display_erm_tab.insert(link_insert_index, "LinkedIn")

    cols_existantes_in_display_tab = [
        col for col in cols_to_display_erm_tab if col in df_display_erm_processed.columns
    ]

    # Configuration des colonnes pour st.dataframe, incluant les types de colonnes et les labels.
    column_config_map = {
        "LinkedIn": st.column_config.LinkColumn("LinkedIn", display_text="🔗 LinkedIn"),
        "Google Maps": st.column_config.LinkColumn("Google Maps", display_text="📍 Google Maps"),
        "Emploi": st.column_config.LinkColumn("Emploi", display_text="🔗 Emploi"),
        "Est siège social": st.column_config.CheckboxColumn(disabled=True),
        "Date de création Entreprise": st.column_config.DateColumn(format="DD/MM/YYYY", disabled=True),
        "Chiffre d'Affaires Entreprise": st.column_config.NumberColumn(label="CA Ent.", format="%d €", disabled=True),
        "Nb salariés établissement": st.column_config.TextColumn(label="Nb salariés établissement"), # Displays the new combined string
        "Résultat Net Entreprise": st.column_config.NumberColumn(label="Rés. Net Ent.", format="%d €", disabled=True),
    }

    st.dataframe(
        df_display_erm_processed[cols_existantes_in_display_tab],
        column_config=column_config_map,
        hide_index=True,
        use_container_width=True,
    )

# --- BOUTON DE TÉLÉCHARGEMENT ERM ---
download_button_key = "download_user_erm_excel_button"
try:
    # Prepare df_entreprises_for_excel from st.session_state.df_entreprises_erm
    # Now, it should download the VISIBLE ERM data.
    df_entreprises_for_excel = get_visible_erm_data() # Use the filtered data

    excel_column_order_core = [
        "SIRET", "Dénomination - Enseigne", "LinkedIn", "Google Maps", "Emploi",
        "Activité NAF/APE Etablissement", "Adresse établissement", "Commune",
        "Nb salariés établissement", # This will be the formatted version
        "Est siège social", "Date de création Entreprise",
        # "Chiffre d'Affaires Entreprise", "Résultat Net Entreprise", "Année Finances Entreprise" # Removed for brevity
    ]
    # Define other desired columns that might come from config.ENTREPRISES_ERM_COLS
    # and should appear after the core set.
    desired_suffix_cols = ["Notes Personnelles", "Statut Piste"]

    if not st.session_state.df_entreprises_erm.empty or st.session_state.past_searches:
        # 1. Ensure 'Effectif Numérique' for formatting (will be dropped before final Excel output)
        if 'Code effectif établissement' in df_entreprises_for_excel.columns:
            df_entreprises_for_excel['Effectif Numérique'] = df_entreprises_for_excel['Code effectif établissement'] \
                .map(config.effectifs_numerical_mapping) \
                .fillna(0)
            df_entreprises_for_excel['Effectif Numérique'] = pd.to_numeric(df_entreprises_for_excel['Effectif Numérique'], errors='coerce').fillna(0).astype(int)
        elif 'Effectif Numérique' not in df_entreprises_for_excel.columns:
            df_entreprises_for_excel['Effectif Numérique'] = 0 # Default if not present
        else: # Exists, ensure type and fill NA
             df_entreprises_for_excel['Effectif Numérique'] = pd.to_numeric(df_entreprises_for_excel['Effectif Numérique'], errors='coerce').fillna(0).astype(int)

        # 2. Format 'Nb salariés établissement'
        if 'Effectif Numérique' in df_entreprises_for_excel.columns and 'Nb salariés établissement' in df_entreprises_for_excel.columns:
            def format_effectif_for_excel(row):
                num_val = row.get('Effectif Numérique')
                text_val = row.get('Nb salariés établissement')
                letter_prefix = ""
                if pd.notna(num_val):
                    try:
                        num_val_int = int(num_val)
                        letter_prefix = config.effectif_numeric_to_letter_prefix.get(num_val_int, "")
                    except (ValueError, TypeError):
                        pass # letter_prefix remains ""
                text_upper = str(text_val).upper() if pd.notna(text_val) else "N/A"
                return f"{letter_prefix} - {text_upper}" if letter_prefix else text_upper
            df_entreprises_for_excel['Nb salariés établissement'] = df_entreprises_for_excel.apply(format_effectif_for_excel, axis=1)

        # 3. Add link columns using the helper function
        if "Dénomination - Enseigne" in df_entreprises_for_excel.columns and "Commune" in df_entreprises_for_excel.columns:
            df_entreprises_for_excel["LinkedIn"] = df_entreprises_for_excel.apply(
                lambda row: generate_google_search_url(row.get("Dénomination - Enseigne"), row.get("Commune"), "linkedin"),
                axis=1
            )
            df_entreprises_for_excel["Emploi"] = df_entreprises_for_excel.apply(
                lambda row: generate_google_search_url(row.get("Dénomination - Enseigne"), row.get("Commune"), "emploi"),
                axis=1
            )

        if "Dénomination - Enseigne" in df_entreprises_for_excel.columns and "Adresse établissement" in df_entreprises_for_excel.columns:
            df_entreprises_for_excel["Google Maps"] = df_entreprises_for_excel.apply(
                lambda row: f"https://www.google.com/maps/search/?api=1&query={row['Dénomination - Enseigne']},{row['Adresse établissement']}"
                if pd.notna(row["Dénomination - Enseigne"]) and row["Dénomination - Enseigne"].strip() != "" and \
                   pd.notna(row["Adresse établissement"]) and row["Adresse établissement"].strip() != ""
                else None, axis=1
            )
            # The old "Indeed" logic is now replaced by "Emploi" above.
            # df_entreprises_for_excel["Indeed"] = df_entreprises_for_excel["Dénomination - Enseigne"].apply(
            #     lambda x: f"https://www.google.com/search?q={x}+site%3Aindeed.com" if pd.notna(x) and x.strip() != "" else None
            # )

        
        # 4. Define final column list and select them
        excel_column_order_suffix = []
        for col_name in desired_suffix_cols:
            if col_name in df_entreprises_for_excel.columns or col_name in config.ENTREPRISES_ERM_COLS:
                 excel_column_order_suffix.append(col_name)

        final_excel_columns = excel_column_order_core + excel_column_order_suffix
        
        # Ensure all defined Excel columns exist in the DataFrame, adding them with NA if not.
        for col in final_excel_columns:
            if col not in df_entreprises_for_excel.columns:
                df_entreprises_for_excel[col] = pd.NA
        
        # Select only the desired columns in the specified order for the Excel sheet.
        # This implicitly drops "Code effectif établissement", "Effectif Numérique", and any other unwanted columns.
        df_entreprises_for_excel = df_entreprises_for_excel[final_excel_columns]
    else: # df_entreprises_erm is empty, create an empty DataFrame with the correct Excel column structure
        final_excel_columns_empty_case = excel_column_order_core + desired_suffix_cols
        df_entreprises_for_excel = pd.DataFrame(columns=final_excel_columns_empty_case)

    user_erm_excel_data = data_utils.generate_user_erm_excel(
        df_entreprises_for_excel, # Pass the prepared DataFrame for the "Entreprises" sheet
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
st.markdown(" Propulsé avec les API Data Gouv : [API Recherche d’Entreprises](https://www.data.gouv.fr/fr/dataservices/api-recherche-dentreprises/), [API Découpage administratif](https://guides.data.gouv.fr/reutiliser-des-donnees/utiliser-les-api-geographiques/utiliser-lapi-decoupage-administratif) & [API Adresse](https://www.data.gouv.fr/fr/dataservices/api-adresse-base-adresse-nationale-ban/)")
st.markdown("---")
# --- Bouton pour effacer le tableau des établissements ---
if not st.session_state.df_entreprises_erm.empty:
    with st.expander("Zone de danger", expanded=True):
        st.warning("Attention : Cette action effacera **toutes** les entreprises de l'ERM et l'historique des recherches.")
        if st.button("🗑️ Effacer toutes les données (ERM et Historique)", key="clear_all_data_button"):
            st.session_state.df_entreprises_erm = pd.DataFrame(columns=config.ENTREPRISES_ERM_COLS).astype(config.ENTREPRISES_ERM_DTYPES) # Réinitialise avec dtypes
            # Optionnel: effacer aussi contacts et actions si liés, ou laisser pour une gestion manuelle
            # st.session_state.df_contacts_erm = pd.DataFrame(columns=config.CONTACTS_ERM_COLS)
            # st.session_state.df_actions_erm = pd.DataFrame(columns=config.ACTIONS_ERM_COLS)
            
            # Clear search history
            st.session_state.past_searches = []
            st.session_state.next_search_id = 0

            st.rerun() # Rerun to update the display immediately

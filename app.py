import datetime  # Ensure datetime is imported for logging

import pandas as pd  # Ensure pandas is imported
import pydeck as pdk
import streamlit as st

import api_client
import auth_utils  # Import the new authentication utility

# Importer les modules locaux
import config
import data_utils
import geo_utils

# --- SCRIPT START LOG ---
print(f"{datetime.datetime.now()} - INFO - app.py script started.")
# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(layout="wide")

# --- GLOBAL COLUMN DEFINITIONS ---
# Moved here to be defined before use in session state initialization
EXPECTED_ENTREPRISE_COLS = [
    "SIRET",
    "Nom complet",
    "Enseignes",
    "Activité NAF/APE établissement",
    "Adresse établissement",
    "Nb salariés établissement",
    "Est siège social",
    "Date de création Entreprise",
    "Chiffre d'Affaires Entreprise",
    "Résultat Net Entreprise",
    "Année Finances Entreprise",
    "SIREN",
    "Notes Personnelles",
    "Statut Piste",
]
EXPECTED_CONTACT_COLS = [
    "Prénom Nom",
    "Entreprise",
    "Poste",
    "Direction",
    "Email",
    "Téléphone",
    "Profil LinkedIn URL",
    "Notes",
]
EXPECTED_ACTION_COLS = [
    "Entreprise",
    "Contact (Prénom Nom)",
    "Type Action",
    "Date Action",
    "Description/Notes",
    "Statut Action",
    "Statut Opportunuité Taf",
]

# --- DEFAULT USER FOR ERM ---
DEFAULT_USERNAME = ""

# --- INITIALISATION DE L'ÉTAT DE SESSION POUR L'AUTHENTIFICATION ET ERM ---
print(f"{datetime.datetime.now()} - INFO - Initializing session state variables.")
if "username" not in st.session_state:
    st.session_state.username = DEFAULT_USERNAME  # Set default username
    print(
        f"{datetime.datetime.now()} - INFO - Session state 'username' initialized to '{DEFAULT_USERNAME}'."
    )
if "erm_data" not in st.session_state:
    st.session_state.erm_data = auth_utils.load_user_erm_data(
        st.session_state.username
    )  # Load data for default user
    print(
        f"{datetime.datetime.now()} - INFO - Session state 'erm_data' initialized to empty lists."
    )
if "df_entreprises" not in st.session_state:
    # Initialiser à partir de erm_data si c'est la première fois
    df_e_initial = pd.DataFrame(st.session_state.erm_data.get("entreprises", []))
    st.session_state.df_entreprises = data_utils.ensure_df_schema(df_e_initial, EXPECTED_ENTREPRISE_COLS)
    print(
        f"{datetime.datetime.now()} - INFO - Session state 'df_entreprises' initialized from erm_data. Count: {len(st.session_state.df_entreprises)}"
    )
else:
    # S'assurer que le schéma est correct lors des rechargements suivants (au cas où)
    st.session_state.df_entreprises = data_utils.ensure_df_schema(st.session_state.df_entreprises, EXPECTED_ENTREPRISE_COLS)

if "df_contacts" not in st.session_state:
    df_c_initial = pd.DataFrame(st.session_state.erm_data.get("contacts", []))
    st.session_state.df_contacts = data_utils.ensure_df_schema(df_c_initial, EXPECTED_CONTACT_COLS)
    print(
        f"{datetime.datetime.now()} - INFO - Session state 'df_contacts' initialized from erm_data. Count: {len(st.session_state.df_contacts)}"
    )
else:
    st.session_state.df_contacts = data_utils.ensure_df_schema(st.session_state.df_contacts, EXPECTED_CONTACT_COLS)

if "df_actions" not in st.session_state:
    df_a_initial = pd.DataFrame(st.session_state.erm_data.get("actions", []))
    st.session_state.df_actions = data_utils.ensure_df_schema(df_a_initial, EXPECTED_ACTION_COLS)
    if "Date Action" in st.session_state.df_actions.columns:
        st.session_state.df_actions["Date Action"] = pd.to_datetime(
            st.session_state.df_actions["Date Action"], errors="coerce"
        )
    print(
        f"{datetime.datetime.now()} - INFO - Session state 'df_actions' initialized from erm_data. Count: {len(st.session_state.df_actions)}"
    )
else:
    st.session_state.df_actions = data_utils.ensure_df_schema(st.session_state.df_actions, EXPECTED_ACTION_COLS)
    if "Date Action" in st.session_state.df_actions.columns: # Assurer le type Date également lors des rechargements
        st.session_state.df_actions["Date Action"] = pd.to_datetime(
            st.session_state.df_actions["Date Action"], errors="coerce"
        )

if "confirm_flush" not in st.session_state:  # New session state for flush confirmation
    st.session_state.confirm_flush = False
    print(
        f"{datetime.datetime.now()} - INFO - Session state 'confirm_flush' initialized to False."
    )
if "editor_key_version" not in st.session_state: # Nouveau compteur pour la clé de l'éditeur
    st.session_state.editor_key_version = 0
    print(
        f"{datetime.datetime.now()} - INFO - Session state 'editor_key_version' initialized to 0."
    )


# Le bloc "LOAD INITIAL ERM DATA INTO DATAFRAMES" a été intégré ci-dessus
# et est donc supprimé d'ici.

# --- TITRE ET DESCRIPTION (Toujours visible) ---
st.title("🔎 Recherche d'entreprises pour candidatures spontanées")
st.markdown(
    "Trouvez des entreprises en fonction d'une adresse, d'un rayon, de secteurs d'activité (NAF) et de tranches d'effectifs salariés."
)

# --- CONTENU PRINCIPAL DE L'APPLICATION (Maintenant toujours visible) ---

# Sidebar welcome message (optional, can be removed or kept generic)
# st.sidebar.info(f"ERM actif pour : {st.session_state.username}") # Indicates which ERM data is being used

# --- Vérification chargement NAF ---
if data_utils.naf_detailed_lookup is None:
    st.error(
        "Erreur critique : Le dictionnaire NAF n'a pas pu être chargé. L'application ne peut pas continuer."
    )
    st.stop()

# --- SIDEBAR : SAISIE DES PARAMÈTRES (Partie de la sidebar visible si authentifié) ---
with st.sidebar:
    st.header("Paramètres de Recherche")
    st.subheader("📍 Localisation")
    adresse_input = st.text_input(
        "Adresse de référence",
        placeholder="Ex: 1 AVENUE DU DOCTEUR GLEY 75020 PARIS",
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
    st.markdown("---")
    st.subheader("🏢 Filtres Entreprise")

    # --- Gestion état session ---
    if "selected_naf_letters" not in st.session_state:
        st.session_state.selected_naf_letters = ["F","G","J"]
    if "selected_effectifs_codes" not in st.session_state:
        st.session_state.selected_effectifs_codes = [
            "01",
            "02",
            "03"
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

    # --- Sélection NAF Combinée ---
    st.markdown("**Secteurs d'activité NAF**")
    st.caption(
        "Sélectionnez les sections larges. Vous pourrez affiner par codes spécifiques ci-dessous (optionnel)."
    )

    # Utiliser une fonction pour gérer le changement d'état des sections
    def on_section_change():
        # Lire l'état actuel des checkboxes de section
        current_sections = []
        for letter in config.naf_sections_details: # Utiliser la nouvelle structure
            if st.session_state.get(f"naf_section_{letter}", False):
                current_sections.append(letter)

        # Comparer avec l'état précédent stocké
        if set(current_sections) != set(st.session_state.selected_naf_letters):
            st.session_state.selected_naf_letters = current_sections
            # Nettoyer les codes spécifiques des sections désélectionnées
            st.session_state.selected_specific_naf_codes = {
                code
                for code in st.session_state.selected_specific_naf_codes
                if data_utils.get_section_for_code(code)
                in st.session_state.selected_naf_letters
            }
            # Pas besoin de rerun ici, Streamlit le fait après le callback

    cols_naf = st.columns(2)
    col_idx_naf = 0
    # Utiliser la nouvelle structure pour obtenir lettre, description et icône
    for letter, details in sorted(config.naf_sections_details.items()):
        with cols_naf[col_idx_naf]:
            st.checkbox(
                f"{details['icon']} {details['description']}", # Afficher l'icône et la description
                value=(letter in st.session_state.selected_naf_letters),
                key=f"naf_section_{letter}",
                on_change=on_section_change,  # Appeler la fonction au changement
            )
        col_idx_naf = (col_idx_naf + 1) % len(cols_naf)

    st.markdown("---")
    # --- Affinage Optionnel par Codes NAF Spécifiques ---
    with st.expander("Affiner par codes NAF spécifiques (Optionnel)", expanded=False):
        selected_sections_sorted = sorted(st.session_state.selected_naf_letters)

        if not selected_sections_sorted:
            st.caption(
                "Sélectionnez au moins une section NAF ci-dessus pour pouvoir affiner par code."
            )
        else:
            # Utiliser une fonction pour gérer les changements des checkboxes spécifiques
            def on_specific_naf_change(change_type, section_letter=None, code=None):
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
                # Pas besoin de rerun ici, Streamlit le fait après le callback

            for section_letter in selected_sections_sorted:
                section_details = config.naf_sections_details.get(section_letter)
                section_description = section_details['description'] if section_details else section_letter
                st.markdown(
                    f"##### Codes spécifiques pour Section {section_description}"
                )

                codes_in_this_section = data_utils.get_codes_for_section(section_letter)
                if not codes_in_this_section:
                    st.caption("_Aucun code détaillé trouvé pour cette section._")
                    st.markdown("---")
                    continue

                all_codes_in_section_set = set(codes_in_this_section)
                # Vérifier si tous les codes sont DÉJÀ dans l'état de session
                are_all_selected = all_codes_in_section_set.issubset(
                    st.session_state.selected_specific_naf_codes
                )

                st.checkbox(
                    "Tout sélectionner / Désélectionner pour cette section",
                    value=are_all_selected,  # Afficher l'état actuel
                    key=f"select_all_{section_letter}",
                    on_change=on_specific_naf_change,  # Appeler la fonction
                    args=("select_all", section_letter),  # Passer des arguments
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
                            ),  # Afficher l'état actuel
                            key=f"specific_naf_cb_{code}",
                            on_change=on_specific_naf_change,  # Appeler la fonction
                            args=("individual", None, code),  # Passer des arguments
                        )
                    col_idx_specific += 1
                st.markdown("---")

        if st.session_state.selected_specific_naf_codes:
            st.caption(
                f"{len(st.session_state.selected_specific_naf_codes)} code(s) NAF spécifique(s) sélectionné(s) au total."
            )

    st.markdown("---")
    # --- Tranches d'effectifs (Simplifié) ---
    st.markdown("**Tranches d'effectifs salariés (Établissement)**")

    # Utiliser une fonction pour gérer les changements des groupes d'effectifs
    def on_effectif_change(group_key_arg, codes_in_group_arg): # Renamed args for clarity
        eff_key = f"eff_group_{group_key_arg}" # Use the internal key like "TPE", "PME_S"
        is_selected = st.session_state[eff_key]
        current_selection_codes_eff = set(st.session_state.selected_effectifs_codes)
        if is_selected:
            current_selection_codes_eff.update(codes_in_group_arg)
        else:
            current_selection_codes_eff.difference_update(codes_in_group_arg)
        st.session_state.selected_effectifs_codes = sorted(
            list(current_selection_codes_eff)
        )
        # Pas besoin de rerun ici

    cols_eff = st.columns(2)
    col_idx_eff = 0
    # Utiliser la nouvelle structure effectifs_groupes_details de config.py
    for group_key, details in config.effectifs_groupes_details.items():
        # Déterminer l'état actuel basé sur session_state
        is_group_currently_selected = any(
            code in st.session_state.selected_effectifs_codes for code in details["codes"]
        )
        with cols_eff[col_idx_eff % len(cols_eff)]:
            st.checkbox(
                f"{details['icon']} {details['label']}",  # Afficher l'icône et le label descriptif
                value=is_group_currently_selected,  # Afficher l'état actuel
                key=f"eff_group_{group_key}", # Utiliser la clé interne du groupe pour la clé du widget
                on_change=on_effectif_change,  # Appeler la fonction
                args=(group_key, details["codes"]),  # Passer la clé interne et les codes
            )
        col_idx_eff += 1

    # Afficher un résumé des codes effectifs sélectionnés (pour débogage)
    # st.caption(f"Codes effectifs sélectionnés : {st.session_state.selected_effectifs_codes}")

    st.markdown("---")
    # --- Bouton de Lancement ---
    lancer_recherche = st.button("🚀 Rechercher les Entreprises")

    # --- PIED DE PAGE (Partie de la sidebar visible si authentifié) ---
    st.markdown("---")
    st.info(f"🗓️ {datetime.date.today().strftime('%d/%m/%Y')}")
    st.info("API: recherche-entreprises.api.gouv.fr & BAN France")

# --- ZONE D'AFFICHAGE DES RÉSULTATS ---
results_container = st.container()

# --- LOGIQUE PRINCIPALE DE RECHERCHE ---
if lancer_recherche:
    results_container.empty()  # Nettoyer les anciens résultats

    # --- Vérifications initiales ---
    # Utiliser directement st.session_state qui a été mis à jour par les callbacks
    if not adresse_input or not adresse_input.strip():
        st.error(
            "⚠️ Veuillez saisir une adresse de référence pour lancer la recherche."
        )
        st.stop()
    if not st.session_state.selected_naf_letters:
        st.error("⚠️ Veuillez sélectionner au moins une section NAF.")
        st.stop()
    if not st.session_state.selected_effectifs_codes:
        st.warning("⚠️ Veuillez sélectionner au moins une tranche d'effectifs.")
        st.stop()

    # --- Construction de la liste finale des codes NAF pour l'API ---
    # Lire directement depuis st.session_state mis à jour
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
        #st.caption(f"Codes NAF utilisés : {codes_display}")
        #st.info(
        #    f"Filtrage sur effectifs établissement (codes) : {', '.join(st.session_state.selected_effectifs_codes)}")  # Lire l'état final

        # 1. Géocodage
        coordonnees = geo_utils.geocoder_ban_france(adresse_input)
        if coordonnees is None:
            print(
                f"{datetime.datetime.now()} - ERROR - Geocoding failed for address: {adresse_input}."
            )
            st.stop()
        lat_centre, lon_centre = coordonnees
        print(
            f"{datetime.datetime.now()} - INFO - Geocoding successful for address: {adresse_input} -> Lat: {lat_centre}, Lon: {lon_centre}."
        )

        # 2. Lancer la recherche API
        print(
            f"{datetime.datetime.now()} - INFO - Preparing to call API rechercher_geographiquement_entreprises."
        )
        print(
            f"{datetime.datetime.now()} - INFO - API Params: adresse_input='{adresse_input}', radius_input={radius_input}, final_codes_for_api='{final_api_params['activite_principale']}', selected_effectifs_codes='{st.session_state.selected_effectifs_codes}'."
        )
        entreprises_trouvees = api_client.rechercher_geographiquement_entreprises(
            lat_centre, lon_centre, radius_input, final_api_params
        )
        print(
            f"{datetime.datetime.now()} - INFO - API call completed. Number of raw results received: {len(entreprises_trouvees) if entreprises_trouvees is not None else 'Error/None'}."
        )

        # --- Traitement et Affichage des résultats ---
        if entreprises_trouvees is not None:
            # Utiliser l'état final de session_state pour le traitement
            df_resultats = data_utils.traitement_reponse_api(
                entreprises_trouvees, st.session_state.selected_effectifs_codes
            )
            print(
                f"{datetime.datetime.now()} - INFO - API results processed. Number of filtered establishments: {len(df_resultats)}."
            )
            st.success(
                f"📊 {len(df_resultats)} établissements trouvés correspondant à tous les critères."
            )

            if not df_resultats.empty:
                # Le tableau "Résultats Détaillés" est supprimé.
                # Affichage Carte
                st.subheader("Carte des établissements trouvés")
                df_map = df_resultats.dropna(
                    subset=["Latitude", "Longitude", "Radius", "Color"]
                ).copy()
                if not df_map.empty:
                    zoom_level = 11
                    if radius_input <= 1:
                        zoom_level = 14
                    elif radius_input <= 5:
                        zoom_level = 12
                    elif radius_input <= 10:
                        zoom_level = 11
                    elif radius_input <= 25:
                        zoom_level = 10
                    else:
                        zoom_level = 9

                    initial_view_state = pdk.ViewState(
                        latitude=lat_centre,
                        longitude=lon_centre,
                        zoom=zoom_level,
                        pitch=0,
                        bearing=0,
                    )
                    layer = pdk.Layer(
                        "ScatterplotLayer",
                        data=df_map,
                        get_position="[Longitude, Latitude]",
                        get_color="Color",
                        get_radius="Radius",
                        radius_min_pixels=3,
                        radius_max_pixels=60,
                        pickable=True,
                        auto_highlight=True,
                    )
                    tooltip = {
                        "html": "<b>{Nom complet}</b><br/>SIRET: {SIRET}<br/>Activité Étab.: {Activité NAF/APE Etablissement}<br/>Effectif Étab.: {Nb salariés établissement}",
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
                    st.subheader("Légende")
                    cols_legende = st.columns([1, 2])
                    with cols_legende[0]:
                        st.markdown("**Taille ≈ Effectif Étab.**")
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
                            if any(
                                code in active_eff_codes for code in group_codes
                            ):
                                rep_code = next(
                                    (
                                        c
                                        for c in ["01", "12", "32", "53"]
                                        if c in group_codes
                                    ),
                                    None,
                                )
                                if (
                                    rep_code
                                    and rep_code not in displayed_legend_sizes
                                ):
                                    displayed_legend_sizes.add(rep_code)
                                    label = legend_sizes[rep_code]
                                    pixel_size = legend_pixel_sizes.get(rep_code, 8)
                                    circle_html = f'<span style="{base_circle_style} height: {pixel_size}px; width: {pixel_size}px;"></span>'
                                    st.markdown(
                                        f"{circle_html} {label} ({group_label})",
                                        unsafe_allow_html=True,
                                    )
                    with cols_legende[1]:
                        st.markdown("**Couleur = Section NAF**")
                        if "Section NAF" in df_map.columns:
                            sections_in_final_results = sorted(
                                list(set(df_map["Section NAF"].unique()) - {"N/A"})
                            )
                            if not sections_in_final_results:
                                st.caption(
                                    "Aucune section NAF trouvée dans les résultats."
                                )
                            else:
                                for letter in sections_in_final_results: # Loop to display legend items
                                    if letter in config.naf_sections_details: # Check against the detailed structure
                                        color_rgb = config.naf_color_mapping.get(letter, [128, 128, 128])
                                        color_hex = "#%02x%02x%02x" % tuple(color_rgb)
                                        desc_legende = config.naf_sections_details[letter]['description']
                                        st.markdown(
                                            f"<span style='color:{color_hex}; font-size: 1.5em;'>⬤</span> {desc_legende}",
                                            unsafe_allow_html=True,
                                        )
                        else:
                            st.warning("Colonne 'Section NAF' non trouvée pour la légende des couleurs.")
                else:
                    st.info("Aucun établissement avec des coordonnées géographiques valides à afficher sur la carte.")

                # Le bouton de téléchargement des résultats de recherche a été enlevé.
                # L'utilisateur peut toujours télécharger son ERM complet plus bas.

            elif entreprises_trouvees is not None and len(df_resultats) == 0:
                st.info(
                    "Des entreprises ont été trouvées dans la zone pour les critères NAF/APE, mais aucun de leurs établissements actifs ne correspond aux tranches d'effectifs sélectionnées."
                )
            elif entreprises_trouvees == []:
                st.info(
                    "Aucune entreprise trouvée correspondant aux critères NAF/APE dans la zone spécifiée."
                )

        else:
            st.error(
                "La recherche d'entreprises a échoué en raison d'une erreur lors de la communication avec l'API. Vérifiez les messages d'erreur ci-dessus."
            )

        # --- Ajout automatique des nouvelles entreprises à l'ERM en session ---
        if not df_resultats.empty: # Uniquement si des résultats de recherche existent
            # S'assurer que df_entreprises existe et a la colonne SIRET, sinon initialiser comme vide.
            if "SIRET" not in st.session_state.df_entreprises.columns:
                # This case implies df_entreprises might be empty or from a very old format.
                # For safety, treat as if no ERM entreprises exist for comparison.
                sirets_in_erm = pd.Series(dtype="object")
            else:
                sirets_in_erm = st.session_state.df_entreprises["SIRET"]

            # Identifier les nouvelles entreprises
            df_new_entreprises = df_resultats[
                ~df_resultats["SIRET"].isin(sirets_in_erm)
            ].copy()  # Use .copy() to avoid SettingWithCopyWarning
            print(
                f"{datetime.datetime.now()} - INFO - Identified {len(df_new_entreprises)} new entreprises not in ERM."
            )

            if not df_new_entreprises.empty: # Si de nouvelles entreprises sont trouvées
                # Automatic addition of new companies
                if not df_new_entreprises.empty: # This check is redundant if we are already inside the parent 'if not df_new_entreprises.empty:'
                    print(
                        f"{datetime.datetime.now()} - INFO - Automatically adding {len(df_new_entreprises)} new entreprises to ERM for user '{st.session_state.username}'."
                    )
                    # Colonnes attendues dans le ERM (déjà définies dans l'onglet Entreprises)
                    expected_entreprise_cols_for_add = [ # Renamed to avoid conflict if global EXPECTED_ENTREPRISE_COLS is used directly
                        "SIRET",
                        "Nom complet",
                        "Enseignes",
                        "Activité NAF/APE établissement",
                        "Adresse établissement",
                        "Nb salariés établissement",
                        "Est siège social",
                        "Date de création Entreprise",
                        "Chiffre d'Affaires Entreprise",
                        "Résultat Net Entreprise",
                        "Année Finances Entreprise",
                        "SIREN",
                        "Notes Personnelles",
                        "Statut Piste",
                    ]

                    # Préparer df_new_entreprises pour la concaténation
                    df_to_add = df_new_entreprises.copy()  # Start with the data

                    # Ensure all expected columns exist, adding NA for missing ones
                    for col in expected_entreprise_cols_for_add:
                        if col not in df_to_add.columns:
                            df_to_add[col] = pd.NA

                    # Select and order columns according to expected_entreprise_cols
                    # Using reindex will also add any missing expected columns with NA
                    df_to_add = df_to_add.reindex(columns=expected_entreprise_cols_for_add)

                    # st.write("--- DEBUG: Before calling add_entreprise_records ---")
                    # st.write(
                    #     f"Shape of st.session_state.df_entreprises: {st.session_state.df_entreprises.shape if 'df_entreprises' in st.session_state and not st.session_state.df_entreprises.empty else 'N/A or Empty'}"
                    # )
                    # st.write("Head of st.session_state.df_entreprises:")
                    # st.dataframe(
                    #     st.session_state.df_entreprises.head()
                    #     if "df_entreprises" in st.session_state
                    #     and not st.session_state.df_entreprises.empty
                    #     else pd.DataFrame()
                    # )  # Use st.dataframe for better display

                    # st.write(
                    #     f"Shape of df_to_add: {df_to_add.shape if not df_to_add.empty else 'N/A or Empty'}"
                    # )
                    # st.write("Head of df_to_add:")
                    # st.dataframe(
                    #     df_to_add.head() if not df_to_add.empty else pd.DataFrame()
                    # )  # Use st.dataframe

                    # Use the new utility function
                    st.session_state.df_entreprises = data_utils.add_entreprise_records(
                        st.session_state.df_entreprises,  # current_df_entreprises
                        df_to_add,  # new_records_df
                        expected_entreprise_cols_for_add,  # expected_cols
                    )
                    print(
                        f"{datetime.datetime.now()} - INFO - Added {len(df_to_add)} new entreprises to session state df_entreprises. New total: {len(st.session_state.df_entreprises)}."
                    )
                    # Les messages de débogage après l'ajout sont également supprimés de l'interface utilisateur
                    # st.write("--- DEBUG: After calling add_entreprise_records ---")
                    # st.write(
                    #     f"Shape of updated st.session_state.df_entreprises: {st.session_state.df_entreprises.shape if not st.session_state.df_entreprises.empty else 'N/A or Empty'}"
                    # )
                    # st.write("Head of updated st.session_state.df_entreprises:")
                    # st.dataframe(
                    #     st.session_state.df_entreprises.head()
                    #     if not st.session_state.df_entreprises.empty
                    #     else pd.DataFrame()
                    # )  # Use st.dataframe

                    st.success(
                        f"{len(df_new_entreprises)} nouvelle(s) entreprise(s) automatiquement ajoutée(s) à votre ERM. N'oubliez pas de sauvegarder vos modifications !"
                    )
                    st.session_state.editor_key_version += 1 # Incrémenter pour changer la clé de l'éditeur
                    st.rerun()

            elif (
                not df_resultats.empty # df_resultats n'est pas vide, mais df_new_entreprises l'est
            ):  # df_resultats n'est pas vide, mais df_new_entreprises l'est
                print(
                    f"{datetime.datetime.now()} - INFO - No new entreprises to add to ERM from search results."
                )
                st.info(
                    "✔️ Toutes les entreprises trouvées dans cette recherche sont déjà dans votre ERM ou la recherche n'a pas retourné de nouvelles entreprises à ajouter."
                )

    # --- SECTION ERM ---


    print(
        f"{datetime.datetime.now()} - INFO - Preparing to display ERM tabs for user '{st.session_state.username}'."
    )
    # Simplification : Afficher uniquement l'onglet Entreprises
    #tab_entreprises = st.tabs([" Entreprises"])[0] # st.tabs retourne une liste, on prend le premier élément
    if st.session_state.df_entreprises.empty:
        st.info(
            "Aucune entreprise dans votre liste pour le moment. Lancez une recherche pour en ajouter."
        )
    else: # df_entreprises is not empty
        df_display_erm = st.session_state.df_entreprises.copy()
        # Generate Link Columns
        if "Nom complet" in df_display_erm.columns:
            df_display_erm["LinkedIn"] = df_display_erm[
                "Nom complet"
            ].apply(
                lambda x: f"https://www.google.com/search?q={x}+site%3Alinkedin.com"
                if pd.notna(x) and x.strip() != ""
                else None
            )
        if (
            "Nom complet" in df_display_erm.columns
            and "Adresse établissement" in df_display_erm.columns
        ):
            df_display_erm["Google Maps"] = (
                df_display_erm.apply(
                    lambda row: f"https://www.google.com/maps/search/?api=1&query={row['Nom complet']},{row['Adresse établissement']}"
                    if pd.notna(row["Nom complet"])
                    and row["Nom complet"].strip() != ""
                    and pd.notna(row["Adresse établissement"])
                    and row["Adresse établissement"].strip() != ""
                    else None,
                    axis=1,
                )
            )
        # Définir les colonnes à afficher et leur ordre
        cols_to_display_erm_tab = EXPECTED_ENTREPRISE_COLS[:] # Copie
        if "LinkedIn" in df_display_erm.columns:
            cols_to_display_erm_tab.append("LinkedIn")
        if "Google Maps" in df_display_erm.columns:
            cols_to_display_erm_tab.append("Google Maps")
        
        cols_existantes_in_display_tab = [col for col in cols_to_display_erm_tab if col in df_display_erm.columns]
        st.dataframe(
            df_display_erm[cols_existantes_in_display_tab],
            column_config={
                "LinkedIn": st.column_config.LinkColumn("LinkedIn", display_text="🔗 Profil"),
                "Google Maps": st.column_config.LinkColumn("Google Maps", display_text="📍 Maps"),
                "Est siège social": st.column_config.CheckboxColumn(disabled=True),
                "Date de création Entreprise": st.column_config.DateColumn(format="DD/MM/YYYY", disabled=True),
                "Chiffre d'Affaires Entreprise": st.column_config.NumberColumn(label="CA Ent.", format="€ %d", disabled=True),
                "Résultat Net Entreprise": st.column_config.NumberColumn(label="Rés. Net Ent.", format="€ %d", disabled=True),
            },
            hide_index=True,
            use_container_width=True
        )
    
    print(f"{datetime.datetime.now()} - INFO - TAB ENTREPRISES: Before final ensure_df_schema. Shape: {st.session_state.df_entreprises.shape}")
    # Ensure final schema using the utility function
    st.session_state.df_entreprises = data_utils.ensure_df_schema(
        st.session_state.df_entreprises, EXPECTED_ENTREPRISE_COLS
    )
    print(f"{datetime.datetime.now()} - INFO - TAB ENTREPRISES: End. df_entreprises final count for this run: {len(st.session_state.df_entreprises)}.")

    download_button_key = (
        "download_user_erm_excel_button"  # Key used in st.download_button
    )
    # We can't directly detect the click on st.download_button in the same way as st.button.
    # However, the data preparation for it implies intent.
    print(
        f"{datetime.datetime.now()} - INFO - Preparing data for user ERM download for user '{st.session_state.username}'."
    )
    try:
        # Prépare les données pour le téléchargement du ERM utilisateur
        # La fonction generate_user_erm_excel s'attend à des DataFrames.
        # La conversion de 'Date Action' est gérée dans generate_user_erm_excel.
        user_erm_excel_data = data_utils.generate_user_erm_excel(
            st.session_state.df_entreprises,
            st.session_state.df_contacts,
            st.session_state.df_actions,
        )
        st.download_button(
            label="📥 Télécharger les résultats dans un classeur Excel)",
            data=user_erm_excel_data,
            file_name=f"mon_erm_{st.session_state.username}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_user_erm_excel_button",  # Changed key to avoid conflict if any other key is similar
        )
    except Exception as e:
        st.error(f"Erreur lors de la préparation du téléchargement ERM : {e}")
        # import traceback # Consider for more detailed debugging if needed
        # st.error(traceback.format_exc())
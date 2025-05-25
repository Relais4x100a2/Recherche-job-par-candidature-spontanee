import streamlit as st
import auth_utils # Import the new authentication utility
import pandas as pd # Ensure pandas is imported

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(layout="wide")

# --- INITIALISATION DE L'ÉTAT DE SESSION POUR L'AUTHENTIFICATION ET CRM ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'crm_data' not in st.session_state:
    st.session_state.crm_data = {"entreprises": [], "contacts": [], "actions": []}
if 'df_entreprises' not in st.session_state:
    st.session_state.df_entreprises = pd.DataFrame()
if 'df_contacts' not in st.session_state:
    st.session_state.df_contacts = pd.DataFrame()
if 'df_actions' not in st.session_state:
    st.session_state.df_actions = pd.DataFrame()
if 'confirm_flush' not in st.session_state: # New session state for flush confirmation
    st.session_state.confirm_flush = False

import pydeck as pdk
import datetime

# Importer les modules locaux
import config
import data_utils
import api_client
import geo_utils

# --- GLOBAL COLUMN DEFINITIONS ---
EXPECTED_ENTREPRISE_COLS = [
    'SIRET', 'Nom complet', 'Enseignes', 'Activité NAF/APE établissement', 
    'Adresse établissement', 'Nb salariés établissement', 'Est siège social', 
    'Date de création Entreprise', "Chiffre d'Affaires Entreprise", 
    'Résultat Net Entreprise', 'Année Finances Entreprise', 'SIREN',
    'Notes Personnelles', 'Statut Piste'
]
EXPECTED_CONTACT_COLS = [
    'Prénom Nom', 'Entreprise', 'Poste', 'Direction', 
    'Email', 'Téléphone', 'Profil LinkedIn URL', 'Notes'
]
EXPECTED_ACTION_COLS = [
    'Entreprise', 'Contact (Prénom Nom)', 'Type Action', 'Date Action', 
    'Description/Notes', 'Statut Action', 'Statut Opportunuité Taf'
]

# --- TITRE ET DESCRIPTION (Toujours visible) ---
st.title("🔎 Recherche d'entreprises pour candidatures spontanées")
st.markdown("Trouvez des entreprises en fonction d'une adresse, d'un rayon, de secteurs d'activité (NAF) et de tranches d'effectifs salariés.")

# --- LOGIQUE DE CONNEXION/DECONNEXION ET AFFICHAGE CONDITIONNEL ---

# Formulaires de connexion/déconnexion dans la sidebar
if not st.session_state.authenticated:
    st.sidebar.subheader("Connexion")
    login_username = st.sidebar.text_input("Nom d'utilisateur", key="login_username_main")
    login_password = st.sidebar.text_input("Mot de passe", type="password", key="login_password_main")
    if st.sidebar.button("Se connecter", key="login_button_main"):
        if auth_utils.verify_user(login_username, login_password):
            st.session_state.authenticated = True
            st.session_state.username = login_username
            
            # Charger les données CRM spécifiques à l'utilisateur
            st.session_state.crm_data = auth_utils.load_user_crm_data(st.session_state.username)
            
            # Load initial DataFrames
            df_e = pd.DataFrame(st.session_state.crm_data.get('entreprises', []))
            df_c = pd.DataFrame(st.session_state.crm_data.get('contacts', []))
            df_a = pd.DataFrame(st.session_state.crm_data.get('actions', []))

            # Ensure schema immediately after loading
            st.session_state.df_entreprises = data_utils.ensure_df_schema(df_e, EXPECTED_ENTREPRISE_COLS)
            st.session_state.df_contacts = data_utils.ensure_df_schema(df_c, EXPECTED_CONTACT_COLS)
            st.session_state.df_actions = data_utils.ensure_df_schema(df_a, EXPECTED_ACTION_COLS)
            
            # Ensure 'Date Action' is datetime after schema enforcement
            if 'Date Action' in st.session_state.df_actions.columns:
                st.session_state.df_actions['Date Action'] = pd.to_datetime(st.session_state.df_actions['Date Action'], errors='coerce')

            st.rerun()
        else:
            st.sidebar.error("Nom d'utilisateur ou mot de passe incorrect.")
else:
    st.sidebar.success(f"Connecté en tant que : {st.session_state.username}")
    if st.sidebar.button("Se déconnecter", key="logout_button_main"):
        st.session_state.authenticated = False
        st.session_state.username = ""
        # Effacer les données CRM de la session lors de la déconnexion
        st.session_state.crm_data = {"entreprises": [], "contacts": [], "actions": []}
        st.session_state.df_entreprises = pd.DataFrame()
        st.session_state.df_contacts = pd.DataFrame()
        st.session_state.df_actions = pd.DataFrame()
        st.rerun()

# Affichage du contenu principal ou du message de connexion
if not st.session_state.authenticated:
    st.info("Veuillez vous connecter pour accéder à l'application.")
else:
    # --- CONTENU PRINCIPAL DE L'APPLICATION (Visible uniquement si authentifié) ---

    # --- Vérification chargement NAF ---
    if data_utils.naf_detailed_lookup is None:
        st.error("Erreur critique : Le dictionnaire NAF n'a pas pu être chargé. L'application ne peut pas continuer.")
        st.stop()

    # --- SIDEBAR : SAISIE DES PARAMÈTRES (Partie de la sidebar visible si authentifié) ---
    with st.sidebar: # Ceci s'ajoutera aux éléments de connexion/déconnexion déjà définis pour la sidebar
        st.header("Paramètres de Recherche")
        st.subheader("📍 Localisation")
        adresse_input = st.text_input("Adresse de référence", placeholder="Ex: 1 Rue de la Paix, 75002 Paris", help="Veuillez saisir une adresse complète pour lancer la recherche.")
        default_radius = 5.0
        radius_input = st.number_input("Rayon de recherche (km)", min_value=0.1, max_value=50.0, value=default_radius, step=0.5, format="%.1f")
        st.markdown("---")
        st.subheader("🏢 Filtres Entreprise")

        # --- Gestion état session ---
        if 'selected_naf_letters' not in st.session_state:
            st.session_state.selected_naf_letters = ["J"]
        if 'selected_effectifs_codes' not in st.session_state:
            st.session_state.selected_effectifs_codes = ['11', '12', '21', '22', '31', '32', '41', '42', '51', '52', '53']
        if 'selected_specific_naf_codes' not in st.session_state:
            st.session_state.selected_specific_naf_codes = set()
        else:
            if not isinstance(st.session_state.selected_specific_naf_codes, set):
                st.session_state.selected_specific_naf_codes = set(st.session_state.selected_specific_naf_codes)

        # --- Sélection NAF Combinée ---
        st.markdown("**Secteurs d'activité NAF**")
        st.caption("Sélectionnez les sections larges. Vous pourrez affiner par codes spécifiques ci-dessous (optionnel).")

        # Utiliser une fonction pour gérer le changement d'état des sections
        def on_section_change():
            # Lire l'état actuel des checkboxes de section
            current_sections = []
            for letter in config.naf_sections:
                if st.session_state.get(f"naf_section_{letter}", False):
                    current_sections.append(letter)

            # Comparer avec l'état précédent stocké
            if set(current_sections) != set(st.session_state.selected_naf_letters):
                st.session_state.selected_naf_letters = current_sections
                # Nettoyer les codes spécifiques des sections désélectionnées
                st.session_state.selected_specific_naf_codes = {
                    code for code in st.session_state.selected_specific_naf_codes
                    if data_utils.get_section_for_code(code) in st.session_state.selected_naf_letters
                }
                # Pas besoin de rerun ici, Streamlit le fait après le callback

        cols_naf = st.columns(2)
        col_idx_naf = 0
        for letter, description in sorted(config.naf_sections.items()):
            with cols_naf[col_idx_naf]:
                st.checkbox(
                    description,
                    value=(letter in st.session_state.selected_naf_letters),
                    key=f"naf_section_{letter}",
                    on_change=on_section_change # Appeler la fonction au changement
                )
            col_idx_naf = (col_idx_naf + 1) % len(cols_naf)

        st.markdown("---")
        # --- Affinage Optionnel par Codes NAF Spécifiques ---
        with st.expander("Affiner par codes NAF spécifiques (Optionnel)", expanded=False):

            selected_sections_sorted = sorted(st.session_state.selected_naf_letters)

            if not selected_sections_sorted:
                st.caption("Sélectionnez au moins une section NAF ci-dessus pour pouvoir affiner par code.")
            else:
                # Utiliser une fonction pour gérer les changements des checkboxes spécifiques
                def on_specific_naf_change(change_type, section_letter=None, code=None):
                    if change_type == "select_all":
                        select_all_key = f"select_all_{section_letter}"
                        should_select_all = st.session_state[select_all_key]
                        codes_in_section = set(data_utils.get_codes_for_section(section_letter))
                        if should_select_all:
                            st.session_state.selected_specific_naf_codes.update(codes_in_section)
                        else:
                            st.session_state.selected_specific_naf_codes.difference_update(codes_in_section)
                    elif change_type == "individual":
                        cb_key = f"specific_naf_cb_{code}"
                        is_selected = st.session_state[cb_key]
                        if is_selected:
                            st.session_state.selected_specific_naf_codes.add(code)
                        else:
                            st.session_state.selected_specific_naf_codes.discard(code)
                    # Pas besoin de rerun ici, Streamlit le fait après le callback

                for section_letter in selected_sections_sorted:
                    section_description = config.naf_sections.get(section_letter, section_letter)
                    st.markdown(f"##### Codes spécifiques pour Section {section_description}")

                    codes_in_this_section = data_utils.get_codes_for_section(section_letter)
                    if not codes_in_this_section:
                        st.caption("_Aucun code détaillé trouvé pour cette section._")
                        st.markdown("---")
                        continue

                    all_codes_in_section_set = set(codes_in_this_section)
                    # Vérifier si tous les codes sont DÉJÀ dans l'état de session
                    are_all_selected = all_codes_in_section_set.issubset(st.session_state.selected_specific_naf_codes)

                    st.checkbox(
                        "Tout sélectionner / Désélectionner pour cette section",
                        value=are_all_selected, # Afficher l'état actuel
                        key=f"select_all_{section_letter}",
                        on_change=on_specific_naf_change, # Appeler la fonction
                        args=("select_all", section_letter) # Passer des arguments
                    )
                    st.markdown("---")

                    cols_specific_naf = st.columns(2)
                    col_idx_specific = 0
                    for code in codes_in_this_section:
                        libelle = data_utils.naf_detailed_lookup.get(code, "Libellé inconnu")
                        with cols_specific_naf[col_idx_specific % len(cols_specific_naf)]:
                            st.checkbox(
                                f"{code} - {libelle}",
                                value=(code in st.session_state.selected_specific_naf_codes), # Afficher l'état actuel
                                key=f"specific_naf_cb_{code}",
                                on_change=on_specific_naf_change, # Appeler la fonction
                                args=("individual", None, code) # Passer des arguments
                            )
                        col_idx_specific += 1
                    st.markdown("---")

            if st.session_state.selected_specific_naf_codes:
                 st.caption(f"{len(st.session_state.selected_specific_naf_codes)} code(s) NAF spécifique(s) sélectionné(s) au total.")

        st.markdown("---")
        # --- Tranches d'effectifs (Simplifié) ---
        st.markdown("**Tranches d'effectifs salariés (Établissement)**")

        # Utiliser une fonction pour gérer les changements des groupes d'effectifs
        def on_effectif_change(group_label, codes_in_group):
            eff_key = f"eff_group_{group_label.replace(' ', '_')}"
            is_selected = st.session_state[eff_key]
            current_selection_codes_eff = set(st.session_state.selected_effectifs_codes)
            if is_selected:
                current_selection_codes_eff.update(codes_in_group)
            else:
                current_selection_codes_eff.difference_update(codes_in_group)
            st.session_state.selected_effectifs_codes = sorted(list(current_selection_codes_eff))
            # Pas besoin de rerun ici

        cols_eff = st.columns(2)
        col_idx_eff = 0
        for label, codes_in_group in config.effectifs_groupes.items():
            # Déterminer l'état actuel basé sur session_state
            is_group_currently_selected = any(code in st.session_state.selected_effectifs_codes for code in codes_in_group)
            with cols_eff[col_idx_eff % len(cols_eff)]:
                st.checkbox(
                    label,
                    value=is_group_currently_selected, # Afficher l'état actuel
                    key=f"eff_group_{label.replace(' ', '_')}",
                    on_change=on_effectif_change, # Appeler la fonction
                    args=(label, codes_in_group) # Passer des arguments
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
        results_container.empty() # Nettoyer les anciens résultats

        # --- Vérifications initiales ---
        # Utiliser directement st.session_state qui a été mis à jour par les callbacks
        if not adresse_input or not adresse_input.strip():
            st.error("⚠️ Veuillez saisir une adresse de référence pour lancer la recherche.")
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
            specifics_in_section = {code for code in selected_specifics if data_utils.get_section_for_code(code) == section_letter}
            if specifics_in_section:
                final_codes_for_api.update(specifics_in_section)
            else:
                all_codes_in_section = data_utils.get_codes_for_section(section_letter)
                final_codes_for_api.update(all_codes_in_section)

        if not final_codes_for_api:
            st.error("⚠️ Aucun code NAF résultant de votre sélection. Vérifiez vos choix de sections et de codes spécifiques.")
            st.stop()

        # Préparer les paramètres API
        final_api_params = {
            'activite_principale': ",".join(sorted(list(final_codes_for_api)))
        }

        # --- Début du processus dans le conteneur de résultats ---
        with results_container:
            st.info(f"Recherche pour {len(final_codes_for_api)} code(s) NAF spécifique(s) résultant de la sélection.")
            codes_display = final_api_params['activite_principale']
            if len(codes_display) > 200: codes_display = codes_display[:200] + "..."
            st.caption(f"Codes NAF utilisés : {codes_display}")
            st.info(f"Filtrage sur effectifs établissement (codes) : {', '.join(st.session_state.selected_effectifs_codes)}") # Lire l'état final

            # 1. Géocodage
            coordonnees = geo_utils.geocoder_ban_france(adresse_input)
            if coordonnees is None:
                st.stop()
            lat_centre, lon_centre = coordonnees

            # 2. Lancer la recherche API
            entreprises_trouvees = api_client.rechercher_geographiquement_entreprises(
                lat_centre, lon_centre, radius_input, final_api_params
            )

            # --- Traitement et Affichage des résultats ---
            if entreprises_trouvees is not None:
                # Utiliser l'état final de session_state pour le traitement
                df_resultats = data_utils.traitement_reponse_api(
                    entreprises_trouvees,
                    st.session_state.selected_effectifs_codes
                )
                st.success(f"📊 {len(df_resultats)} établissements trouvés correspondant à tous les critères.")

                if not df_resultats.empty:
                    # Affichage Tableau
                    st.subheader("Résultats Détaillés")
                    cols_existantes_pour_tableau = [col for col in config.COLS_DISPLAY_TABLE if col in df_resultats.columns]
                    df_display = df_resultats[cols_existantes_pour_tableau].copy()
                    st.dataframe(df_display) # Suppression de .fillna('')

                    # Affichage Carte
                    st.subheader("Carte des établissements trouvés")
                    df_map = df_resultats.dropna(subset=['Latitude', 'Longitude', 'Radius', 'Color']).copy()
                    if not df_map.empty:
                        zoom_level = 11
                        if radius_input <= 1: zoom_level = 14
                        elif radius_input <= 5: zoom_level = 12
                        elif radius_input <= 10: zoom_level = 11
                        elif radius_input <= 25: zoom_level = 10
                        else: zoom_level = 9

                        initial_view_state = pdk.ViewState(latitude=lat_centre, longitude=lon_centre, zoom=zoom_level, pitch=0, bearing=0)
                        layer = pdk.Layer(
                            'ScatterplotLayer', data=df_map, get_position='[Longitude, Latitude]',
                            get_color='Color', get_radius='Radius', radius_min_pixels=3, radius_max_pixels=60,
                            pickable=True, auto_highlight=True,
                        )
                        tooltip = {
                            "html": "<b>{Nom complet}</b><br/>SIRET: {SIRET}<br/>Activité Étab.: {Activité NAF/APE Etablissement}<br/>Effectif Étab.: {Nb salariés établissement}",
                            "style": {"backgroundColor": "rgba(0,0,0,0.7)", "color": "white", "border": "1px solid white", "padding": "5px"}
                        }
                        deck = pdk.Deck(
                            layers=[layer], initial_view_state=initial_view_state,
                            map_style='mapbox://styles/mapbox/light-v9', tooltip=tooltip, height=600
                        )
                        st.pydeck_chart(deck)

                        # Affichage Légende
                        st.subheader("Légende")
                        cols_legende = st.columns([1, 2])
                        with cols_legende[0]:
                            st.markdown("**Taille ≈ Effectif Étab.**")
                            legend_pixel_sizes = {'01': 8, '12': 12, '32': 18, '53': 24}
                            base_circle_style = "display: inline-block; border-radius: 50%; background-color: #808080; margin-right: 5px; vertical-align: middle;"
                            legend_sizes = {'01': 'Petit', '12': 'Moyen', '32': 'Grand', '53': 'Très Grand'}
                            active_eff_codes = set(st.session_state.selected_effectifs_codes)
                            displayed_legend_sizes = set()
                            for group_label, group_codes in config.effectifs_groupes.items():
                                 if any(code in active_eff_codes for code in group_codes):
                                     rep_code = next((c for c in ['01', '12', '32', '53'] if c in group_codes), None)
                                     if rep_code and rep_code not in displayed_legend_sizes:
                                         displayed_legend_sizes.add(rep_code)
                                         label = legend_sizes[rep_code]
                                         pixel_size = legend_pixel_sizes.get(rep_code, 8)
                                         circle_html = f'<span style="{base_circle_style} height: {pixel_size}px; width: {pixel_size}px;"></span>'
                                         st.markdown(f"{circle_html} {label} ({group_label})", unsafe_allow_html=True)
                        with cols_legende[1]:
                            st.markdown("**Couleur = Section NAF**")
                            if 'Section NAF' in df_map.columns:
                                sections_in_final_results = sorted(list(set(df_map['Section NAF'].unique()) - {'N/A'}))
                                if not sections_in_final_results:
                                    st.caption("Aucune section NAF trouvée dans les résultats.")
                                else:
                                    for letter in sections_in_final_results:
                                        if letter in config.naf_sections:
                                            color_rgb = config.naf_color_mapping.get(letter, [0,0,0])
                                            color_hex = '#%02x%02x%02x' % tuple(color_rgb)
                                            st.markdown(f"<span style='color:{color_hex}; font-size: 1.5em;'>⬤</span> {config.naf_sections[letter]}", unsafe_allow_html=True)
                            else:
                                st.warning("Colonne 'Section NAF' non trouvée pour la légende des couleurs.")
                    else:
                        st.info("Aucun établissement avec des coordonnées géographiques valides à afficher sur la carte.")

                    # Bouton Téléchargement
                    st.subheader("Télécharger les résultats")
                    col1, col2 = st.columns(2) # Mettre les boutons côte à côte

                    # Bouton CSV
                    with col1:
                        try:
                            cols_export_existantes = [col for col in config.COLS_EXPORT_ORDER if col in df_resultats.columns]
                            df_export = df_resultats[cols_export_existantes]
                            csv_data = df_export.to_csv(index=False, encoding='utf-8-sig', sep=';')

                            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            adresse_safe = "".join(c if c.isalnum() else "_" for c in adresse_input[:30])
                            eff_codes_str = '_'.join(sorted(st.session_state.selected_effectifs_codes))
                            naf_str = f"codesNAF_{len(final_codes_for_api)}"
                            nom_fichier_csv = f"entreprises_{adresse_safe}_R{radius_input}km_{naf_str}_eff_{eff_codes_str}_{timestamp}.csv"

                            st.download_button(
                                label="📥 Télécharger en CSV (séparateur ';')",
                                data=csv_data,
                                file_name=nom_fichier_csv,
                                mime='text/csv',
                                key='download-csv'
                            )
                        except Exception as e:
                            st.error(f"Erreur lors de la génération du fichier CSV : {e}")

                    # Bouton Excel CRM
                    with col2:
                        try:
                            excel_data = data_utils.generate_crm_excel(df_resultats) # Appel de la nouvelle fonction

                            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            adresse_safe = "".join(c if c.isalnum() else "_" for c in adresse_input[:30])
                            # Utiliser un nom de fichier distinctif
                            nom_fichier_excel = f"crm_candidatures_{adresse_safe}_{timestamp}.xlsx"

                            st.download_button(
                                label="📊 Télécharger le classeur CRM (.xlsx)",
                                data=excel_data,
                                file_name=nom_fichier_excel,
                                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                key='download-excel-crm'
                            )
                        except Exception as e:
                            st.error(f"Erreur lors de la génération du fichier Excel CRM : {e}")


                elif entreprises_trouvees is not None and len(df_resultats) == 0:
                     st.info("Des entreprises ont été trouvées dans la zone pour les critères NAF/APE, mais aucun de leurs établissements actifs ne correspond aux tranches d'effectifs sélectionnées.")
                elif entreprises_trouvees == []:
                     st.info("Aucune entreprise trouvée correspondant aux critères NAF/APE dans la zone spécifiée.")

            else:
                 st.error("La recherche d'entreprises a échoué en raison d'une erreur lors de la communication avec l'API. Vérifiez les messages d'erreur ci-dessus.")

            # --- Intégration des résultats de recherche avec le CRM ---
            if st.session_state.authenticated and not df_resultats.empty:
                st.divider()
                st.subheader("Intégration avec Mon CRM")

                # S'assurer que df_entreprises existe et a la colonne SIRET, sinon initialiser comme vide.
                if 'SIRET' not in st.session_state.df_entreprises.columns:
                    # This case implies df_entreprises might be empty or from a very old format.
                    # For safety, treat as if no CRM entreprises exist for comparison.
                    sirets_in_crm = pd.Series(dtype='object')
                else:
                    sirets_in_crm = st.session_state.df_entreprises['SIRET']
                
                # Identifier les nouvelles entreprises
                df_new_entreprises = df_resultats[~df_resultats['SIRET'].isin(sirets_in_crm)].copy() # Use .copy() to avoid SettingWithCopyWarning

                if not df_new_entreprises.empty:
                    st.write(f"{len(df_new_entreprises)} nouvelles entreprises trouvées (non présentes dans votre CRM) :")
                    
                    # Afficher un aperçu des nouvelles entreprises (par exemple, Nom et SIRET)
                    st.dataframe(df_new_entreprises[['Nom complet', 'SIRET', 'Adresse établissement', 'Activité NAF/APE Etablissement']].head())

                    if st.button(f"➕ Ajouter les {len(df_new_entreprises)} nouvelles entreprises à mon CRM", key="add_new_to_crm"):
                        # Colonnes attendues dans le CRM (déjà définies dans l'onglet Entreprises)
                        expected_entreprise_cols = [
                            'SIRET', 'Nom complet', 'Enseignes', 'Activité NAF/APE établissement', 
                            'Adresse établissement', 'Nb salariés établissement', 'Est siège social', 
                            'Date de création Entreprise', "Chiffre d'Affaires Entreprise", 
                            'Résultat Net Entreprise', 'Année Finances Entreprise', 'SIREN',
                            'Notes Personnelles', 'Statut Piste'
                        ]
                        
                        # Préparer df_new_entreprises pour la concaténation
                        df_to_add = df_new_entreprises.copy() # Start with the data

                        # Ensure all expected columns exist, adding NA for missing ones
                        for col in expected_entreprise_cols:
                            if col not in df_to_add.columns:
                                df_to_add[col] = pd.NA
                        
                        # Select and order columns according to expected_entreprise_cols
                        # Using reindex will also add any missing expected columns with NA
                        df_to_add = df_to_add.reindex(columns=expected_entreprise_cols) 
                        
                        st.write(f"DEBUG (Ajouter Button): df_to_add is empty: {df_to_add.empty}, rows: {len(df_to_add)}")
                        st.write(f"DEBUG (Ajouter Button): df_entreprises (before util call) is empty: {st.session_state.df_entreprises.empty if 'df_entreprises' in st.session_state else 'df_entreprises not in session_state'}, rows: {len(st.session_state.df_entreprises) if 'df_entreprises' in st.session_state and not st.session_state.df_entreprises.empty else 0}")

                        # Use the new utility function
                        st.session_state.df_entreprises = data_utils.add_entreprise_records(
                            st.session_state.df_entreprises, # current_df_entreprises
                            df_to_add,                      # new_records_df
                            expected_entreprise_cols        # expected_cols
                        )
                        
                        st.write(f"DEBUG (Ajouter Button): df_entreprises (after util call / final pre-rerun) is empty: {st.session_state.df_entreprises.empty}, rows: {len(st.session_state.df_entreprises)}")


                        st.success(f"{len(df_new_entreprises)} entreprise(s) ajoutée(s) à votre CRM. N'oubliez pas de sauvegarder vos modifications !")
                        st.rerun()
                
                elif not df_resultats.empty: # df_resultats n'est pas vide, mais df_new_entreprises l'est
                    st.info("✔️ Toutes les entreprises trouvées dans cette recherche sont déjà dans votre CRM ou la recherche n'a pas retourné de nouvelles entreprises.")


    # --- SECTION CRM ---
    st.divider()
    st.write(f"DEBUG: Before 'Mon Espace CRM' header. df_entreprises is empty: {st.session_state.df_entreprises.empty if 'df_entreprises' in st.session_state else 'df_entreprises not in session_state'}") # New debug line
    st.header("Mon Espace CRM")

    st.write("DEBUG: 'Mon Espace CRM' header rendered. Before st.columns for save button.") # New debug line 1
    
    col_save_crm, col_download_user_crm = st.columns(2) 

    with col_save_crm:
        st.write("DEBUG: Inside 'with col_save_crm'. Before main save button definition.") # Restored debug line
        if st.button("💾 Sauvegarder les modifications CRM", key="save_crm_button"):
            # Get data formatted for saving from the utility function
            crm_data_to_save = data_utils.get_crm_data_for_saving()

            # --- Debugging Info Start ---
            st.info(f"Attempting to save CRM data for user: '{st.session_state.username}'")
            st.info(f"Number of entreprises to save: {len(crm_data_to_save['entreprises'])}")
            st.info(f"Number of contacts to save: {len(crm_data_to_save['contacts'])}")
            st.info(f"Number of actions to save: {len(crm_data_to_save['actions'])}")
            
            # Need to import auth_utils at the top of app.py if not already done for this direct call,
            # but it should be imported as it's used elsewhere.
            # Ensure this call is correct based on how auth_utils is imported.
            # Assuming 'import auth_utils' is present.
            target_filepath = auth_utils.get_user_crm_filepath(st.session_state.username)
            st.info(f"Target file path: {target_filepath}")
            # --- Debugging Info End ---
            
            auth_utils.save_user_crm_data(st.session_state.username, crm_data_to_save)
            st.success("🎉 Modifications CRM sauvegardées avec succès !")
            # Optionnel: st.rerun() # Peut être ajouté si on veut forcer une relecture des données depuis le fichier après sauvegarde

    with col_download_user_crm:
        try:
            # Prépare les données pour le téléchargement du CRM utilisateur
            # La fonction generate_user_crm_excel s'attend à des DataFrames.
            # La conversion de 'Date Action' est gérée dans generate_user_crm_excel.
            user_crm_excel_data = data_utils.generate_user_crm_excel(
                st.session_state.df_entreprises,
                st.session_state.df_contacts,
                st.session_state.df_actions 
            )
            st.download_button(
                label="📥 Télécharger mon CRM complet (.xlsx)",
                data=user_crm_excel_data,
                file_name=f"mon_crm_{st.session_state.username}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                key='download_user_crm_excel_button' # Changed key to avoid conflict if any other key is similar
            )
        except Exception as e:
            st.error(f"Erreur lors de la préparation du téléchargement CRM : {e}")
            # import traceback # Consider for more detailed debugging if needed
            # st.error(traceback.format_exc())

    st.markdown("---") # Séparateur visuel

    # --- Zone Dangereuse: Vider le CRM ---
    st.subheader("⚠️ Zone Dangereuse")
    if st.button("Vider toutes mes données CRM", key="flush_crm_data_button"):
        st.session_state.confirm_flush = True
        st.rerun() # Rerun to show confirmation

    if st.session_state.confirm_flush:
        st.warning("Êtes-vous sûr de vouloir supprimer définitivement toutes vos données CRM ? Cette action est irréversible.")
        col1_flush, col2_flush = st.columns(2)
        with col1_flush:
            if st.button("Oui, supprimer tout", key="confirm_flush_yes", type="primary"):
                expected_entreprise_cols = [
                    'SIRET', 'Nom complet', 'Enseignes', 'Activité NAF/APE établissement', 
                    'Adresse établissement', 'Nb salariés établissement', 'Est siège social', 
                    'Date de création Entreprise', "Chiffre d'Affaires Entreprise", 
                    'Résultat Net Entreprise', 'Année Finances Entreprise', 'SIREN',
                    'Notes Personnelles', 'Statut Piste'
                ]
                expected_contact_cols = [
                    'Prénom Nom', 'Entreprise', 'Poste', 'Direction', 
                    'Email', 'Téléphone', 'Profil LinkedIn URL', 'Notes'
                ]
                expected_action_cols = [
                    'Entreprise', 'Contact (Prénom Nom)', 'Type Action', 'Date Action', 
                    'Description/Notes', 'Statut Action', 'Statut Opportunuité Taf'
                ]

                st.session_state.df_entreprises = pd.DataFrame(columns=expected_entreprise_cols)
                st.session_state.df_contacts = pd.DataFrame(columns=expected_contact_cols)
                st.session_state.df_actions = pd.DataFrame(columns=expected_action_cols)
                if 'Date Action' in st.session_state.df_actions.columns: # Ensure datetime type for empty df
                     st.session_state.df_actions['Date Action'] = pd.to_datetime(st.session_state.df_actions['Date Action'], errors='coerce')


                crm_data_to_save = {
                    "entreprises": [],
                    "contacts": [],
                    "actions": []
                }
                auth_utils.save_user_crm_data(st.session_state.username, crm_data_to_save)
                
                st.success("Toutes vos données CRM ont été supprimées.")
                st.session_state.confirm_flush = False
                st.rerun()
        with col2_flush:
            if st.button("Non, annuler", key="confirm_flush_no"):
                st.session_state.confirm_flush = False
                st.rerun()
    
    st.divider() # Visuel separator before tabs
    tab_entreprises, tab_contacts, tab_actions = st.tabs([
        "Mon CRM - Entreprises", 
        "Mon CRM - Contacts", 
        "Mon CRM - Actions"
    ])

    with tab_entreprises:
        st.subheader("Mes Entreprises Sauvegardées")

        # Define expected columns for consistency (this will be global now)
        # expected_entreprise_cols = [
        #     'SIRET', 'Nom complet', 'Enseignes', 'Activité NAF/APE établissement', 
        #     'Adresse établissement', 'Nb salariés établissement', 'Est siège social', 
        #     'Date de création Entreprise', "Chiffre d'Affaires Entreprise", 
        #     'Résultat Net Entreprise', 'Année Finances Entreprise', 'SIREN',
        #     'Notes Personnelles', 'Statut Piste' # Added for direct editing
        # ]
        # Ensure df_entreprises has all expected columns, add if missing
        # for col in EXPECTED_ENTREPRISE_COLS: # Use global
        #     if col not in st.session_state.df_entreprises.columns:
        #         st.session_state.df_entreprises[col] = pd.NA


        if st.session_state.df_entreprises.empty:
            st.info("Aucune entreprise sauvegardée pour le moment. Ajoutez des entreprises via la recherche ou manuellement ci-dessous.")
            # Provide a way to add the first row if df is empty
            # Create an empty DataFrame with expected columns to allow adding the first row
            empty_df_for_editor = pd.DataFrame(columns=EXPECTED_ENTREPRISE_COLS) # Use global
            empty_df_for_editor["Supprimer ?"] = False 
            # Ensure 'Supprimer ?' is first
            cols_ordered_empty = ["Supprimer ?"] + EXPECTED_ENTREPRISE_COLS # Use global
            empty_df_for_editor = empty_df_for_editor[cols_ordered_empty]

            edited_df_entreprises = st.data_editor(
                empty_df_for_editor,
                key="editor_entreprises_empty_init",
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                     # Basic config for empty state, actual links won't be generated yet
                }
            )
            if "Supprimer ?" in edited_df_entreprises.columns: # Check if new rows were added
                st.session_state.df_entreprises = edited_df_entreprises[edited_df_entreprises["Supprimer ?"] == False].drop(columns=["Supprimer ?"], errors='ignore')
            else:
                st.session_state.df_entreprises = edited_df_entreprises.drop(columns=["Supprimer ?"], errors='ignore')


        else: # df_entreprises is not empty
            df_display_entreprises = st.session_state.df_entreprises.copy()
            
            # Add "Supprimer ?" column
            df_display_entreprises["Supprimer ?"] = False
            
            # Generate Link Columns
            if 'Nom complet' in df_display_entreprises.columns:
                df_display_entreprises['Recherche LinkedIn'] = df_display_entreprises['Nom complet'].apply(
                    lambda x: f"https://www.google.com/search?q={x}+site%3Alinkedin.com" if pd.notna(x) and x.strip() != "" else None
                )
            if 'Nom complet' in df_display_entreprises.columns and 'Adresse établissement' in df_display_entreprises.columns:
                df_display_entreprises['Recherche Google Maps'] = df_display_entreprises.apply(
                    lambda row: f"https://www.google.com/maps/search/?api=1&query={row['Nom complet']},{row['Adresse établissement']}" if pd.notna(row['Nom complet']) and row['Nom complet'].strip() != "" and pd.notna(row['Adresse établissement']) and row['Adresse établissement'].strip() != "" else None,
                    axis=1
                )

            # Reorder columns
            link_cols = ['Recherche LinkedIn', 'Recherche Google Maps']
            existing_cols_ordered = [col for col in expected_entreprise_cols if col in df_display_entreprises.columns]
            
            final_cols_ordered = ["Supprimer ?"] + existing_cols_ordered + [lc for lc in link_cols if lc in df_display_entreprises.columns]
            # Add any other columns that might exist but are not in expected or link cols (e.g. from older data)
            other_cols = [col for col in df_display_entreprises.columns if col not in final_cols_ordered]
            df_display_entreprises = df_display_entreprises[final_cols_ordered + other_cols]

            column_config_entreprises = {
                "SIRET": st.column_config.TextColumn(disabled=True),
                "SIREN": st.column_config.TextColumn(disabled=True),
                "Est siège social": st.column_config.CheckboxColumn(disabled=False), # Make it editable
                "Date de création Entreprise": st.column_config.DateColumn(disabled=True),
                "Recherche LinkedIn": st.column_config.LinkColumn("LinkedIn", display_text="🔗 Link", disabled=True),
                "Recherche Google Maps": st.column_config.LinkColumn("Google Maps", display_text="📍 Maps", disabled=True),
                "Statut Piste": st.column_config.SelectboxColumn(
                    options=["À contacter", "Contacté", "En discussion", "Proposition envoyée", "Stand-by", "Non intéressé", "Contrat signé"],
                    required=False # Allow empty selection
                ),
                "Nb salariés établissement": st.column_config.TextColumn(label="Nb Sal. Étab."),
                "Activité NAF/APE établissement": st.column_config.TextColumn(label="Activité Étab."),
                "Chiffre d'Affaires Entreprise": st.column_config.NumberColumn(label="CA Ent.", format="€ %d"),
                "Résultat Net Entreprise": st.column_config.NumberColumn(label="Rés. Net Ent.", format="€ %d"),
                "Année Finances Entreprise": st.column_config.TextColumn(label="Année Fin."),
            }

            edited_df_entreprises = st.data_editor(
                df_display_entreprises,
                key="editor_entreprises",
                num_rows="dynamic",
                use_container_width=True,
                column_config=column_config_entreprises,
                # disabled=['SIRET', 'SIREN', 'Date de création Entreprise', 'Recherche LinkedIn', 'Recherche Google Maps'] # Alternative way
            )

            # Process edits and deletions
            if "Supprimer ?" in edited_df_entreprises.columns:
                rows_to_delete_mask = edited_df_entreprises["Supprimer ?"] == True
                num_rows_to_delete = rows_to_delete_mask.sum()
                
                st.session_state.df_entreprises = edited_df_entreprises[~rows_to_delete_mask].drop(columns=["Supprimer ?"], errors='ignore')
                
                if num_rows_to_delete > 0:
                    st.toast(f"{num_rows_to_delete} entreprise(s) marquée(s) pour suppression et retirée(s) de la vue. N'oubliez pas de sauvegarder les changements globaux du CRM.")
            else:
                 st.session_state.df_entreprises = edited_df_entreprises # Should not happen if "Supprimer ?" was added

        # Ensure final schema using the utility function
        st.session_state.df_entreprises = data_utils.ensure_df_schema(st.session_state.df_entreprises, EXPECTED_ENTREPRISE_COLS)

    with tab_contacts:
        st.subheader("Mes Contacts")

        # expected_contact_cols = [
        #     'Prénom Nom', 'Entreprise', 'Poste', 'Direction', 
        #     'Email', 'Téléphone', 'Profil LinkedIn URL', 'Notes'
        # ]
        # for col in EXPECTED_CONTACT_COLS: # Use global
        #     if col not in st.session_state.df_contacts.columns:
        #         st.session_state.df_contacts[col] = pd.NA

        # Prepare options for SelectboxColumn
        entreprise_options = []
        if "df_entreprises" in st.session_state and not st.session_state.df_entreprises.empty and 'Nom complet' in st.session_state.df_entreprises.columns:
            entreprise_options = st.session_state.df_entreprises['Nom complet'].unique().tolist()
            entreprise_options = [opt for opt in entreprise_options if pd.notna(opt) and opt.strip() != ""]


        if st.session_state.df_contacts.empty:
            st.info("Aucun contact sauvegardé. Ajoutez des contacts manuellement ci-dessous.")
            empty_df_for_editor_contacts = pd.DataFrame(columns=EXPECTED_CONTACT_COLS) # Use global
            empty_df_for_editor_contacts["Supprimer ?"] = False
            cols_ordered_empty_contacts = ["Supprimer ?"] + EXPECTED_CONTACT_COLS # Use global
            empty_df_for_editor_contacts = empty_df_for_editor_contacts[cols_ordered_empty_contacts]

            edited_df_contacts = st.data_editor(
                empty_df_for_editor_contacts,
                key="editor_contacts_empty_init",
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Entreprise": st.column_config.SelectboxColumn(
                        options=entreprise_options,
                        required=False # Or True, depending on desired behavior
                    ),
                    "Direction": st.column_config.SelectboxColumn(
                        options=config.VALEURS_LISTE_CONTACTS_DIRECTION,
                        required=False
                    )
                }
            )
            if "Supprimer ?" in edited_df_contacts.columns:
                st.session_state.df_contacts = edited_df_contacts[edited_df_contacts["Supprimer ?"] == False].drop(columns=["Supprimer ?"], errors='ignore')
            else:
                st.session_state.df_contacts = edited_df_contacts.drop(columns=["Supprimer ?"], errors='ignore')

        else: # df_contacts is not empty
            df_display_contacts = st.session_state.df_contacts.copy()
            df_display_contacts["Supprimer ?"] = False
            
            final_cols_ordered_contacts = ["Supprimer ?"] + expected_contact_cols
            other_cols_contacts = [col for col in df_display_contacts.columns if col not in final_cols_ordered_contacts]
            df_display_contacts = df_display_contacts[final_cols_ordered_contacts + other_cols_contacts]

            column_config_contacts = {
                "Entreprise": st.column_config.SelectboxColumn(
                    options=entreprise_options,
                    required=False 
                ),
                "Direction": st.column_config.SelectboxColumn(
                    options=config.VALEURS_LISTE_CONTACTS_DIRECTION,
                    required=False
                ),
                "Profil LinkedIn URL": st.column_config.LinkColumn(
                    "LinkedIn", 
                    display_text="🔗 Profil" # Optional: custom display text
                ),
            }

            edited_df_contacts = st.data_editor(
                df_display_contacts,
                key="editor_contacts",
                num_rows="dynamic",
                use_container_width=True,
                column_config=column_config_contacts
            )

            if "Supprimer ?" in edited_df_contacts.columns:
                rows_to_delete_mask_contacts = edited_df_contacts["Supprimer ?"] == True
                num_rows_to_delete_contacts = rows_to_delete_mask_contacts.sum()
                
                st.session_state.df_contacts = edited_df_contacts[~rows_to_delete_mask_contacts].drop(columns=["Supprimer ?"], errors='ignore')
                
                if num_rows_to_delete_contacts > 0:
                    st.toast(f"{num_rows_to_delete_contacts} contact(s) marqué(s) pour suppression et retiré(s) de la vue. N'oubliez pas de sauvegarder les changements globaux du CRM.")
            else:
                st.session_state.df_contacts = edited_df_contacts

        # Ensure final schema using the utility function
        st.session_state.df_contacts = data_utils.ensure_df_schema(st.session_state.df_contacts, EXPECTED_CONTACT_COLS)

    with tab_actions:
        st.subheader("Mes Actions et Suivis")

        # expected_action_cols = [
        #     'Entreprise', 'Contact (Prénom Nom)', 'Type Action', 'Date Action', 
        #     'Description/Notes', 'Statut Action', 'Statut Opportunuité Taf'
        # ]
        # for col in EXPECTED_ACTION_COLS: # Use global
        #     if col not in st.session_state.df_actions.columns:
        #         st.session_state.df_actions[col] = pd.NA
        
        # Ensure 'Date Action' is datetime (moved to login)
        # if 'Date Action' in st.session_state.df_actions.columns:
        #     st.session_state.df_actions['Date Action'] = pd.to_datetime(st.session_state.df_actions['Date Action'], errors='coerce')


        # Prepare options for SelectboxColumns
        entreprise_options_actions = []
        if "df_entreprises" in st.session_state and not st.session_state.df_entreprises.empty and 'Nom complet' in st.session_state.df_entreprises.columns:
            entreprise_options_actions = st.session_state.df_entreprises['Nom complet'].unique().tolist()
            entreprise_options_actions = [opt for opt in entreprise_options_actions if pd.notna(opt) and opt.strip() != ""]

        contact_options_actions = []
        if "df_contacts" in st.session_state and not st.session_state.df_contacts.empty and 'Prénom Nom' in st.session_state.df_contacts.columns:
            contact_options_actions = st.session_state.df_contacts['Prénom Nom'].unique().tolist()
            contact_options_actions = [opt for opt in contact_options_actions if pd.notna(opt) and opt.strip() != ""]


        if st.session_state.df_actions.empty:
            st.info("Aucune action sauvegardée. Ajoutez des actions manuellement ci-dessous.")
            empty_df_for_editor_actions = pd.DataFrame(columns=EXPECTED_ACTION_COLS) # Use global
            empty_df_for_editor_actions["Supprimer ?"] = False
            cols_ordered_empty_actions = ["Supprimer ?"] + EXPECTED_ACTION_COLS # Use global
            empty_df_for_editor_actions = empty_df_for_editor_actions[cols_ordered_empty_actions]
            # Ensure 'Date Action' is datetime for empty editor too (handled at load)
            # empty_df_for_editor_actions['Date Action'] = pd.to_datetime(empty_df_for_editor_actions['Date Action'], errors='coerce')


            edited_df_actions = st.data_editor(
                empty_df_for_editor_actions,
                key="editor_actions_empty_init",
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Entreprise": st.column_config.SelectboxColumn(options=entreprise_options_actions, required=False),
                    "Contact (Prénom Nom)": st.column_config.SelectboxColumn(options=contact_options_actions, required=False),
                    "Type Action": st.column_config.SelectboxColumn(options=config.VALEURS_LISTE_ACTIONS_TYPEACTION, required=False),
                    "Date Action": st.column_config.DateColumn(required=False),
                    "Statut Action": st.column_config.SelectboxColumn(options=config.VALEURS_LISTE_ACTIONS_STATUTACTION, required=False),
                    "Statut Opportunuité Taf": st.column_config.SelectboxColumn(options=config.VALEURS_LISTE_ACTIONS_STATUTOPPORTUNITE, required=False)
                }
            )
            if "Supprimer ?" in edited_df_actions.columns:
                st.session_state.df_actions = edited_df_actions[edited_df_actions["Supprimer ?"] == False].drop(columns=["Supprimer ?"], errors='ignore')
            else:
                st.session_state.df_actions = edited_df_actions.drop(columns=["Supprimer ?"], errors='ignore')
        
        else: # df_actions is not empty
            df_display_actions = st.session_state.df_actions.copy()
            df_display_actions["Supprimer ?"] = False
            
            final_cols_ordered_actions = ["Supprimer ?"] + expected_action_cols
            other_cols_actions = [col for col in df_display_actions.columns if col not in final_cols_ordered_actions]
            df_display_actions = df_display_actions[final_cols_ordered_actions + other_cols_actions]

            column_config_actions = {
                "Entreprise": st.column_config.SelectboxColumn(options=entreprise_options_actions, required=False),
                "Contact (Prénom Nom)": st.column_config.SelectboxColumn(options=contact_options_actions, required=False),
                "Type Action": st.column_config.SelectboxColumn(options=config.VALEURS_LISTE_ACTIONS_TYPEACTION, required=False),
                "Date Action": st.column_config.DateColumn(required=False), # format="dd/MM/yyyy" can be added if needed
                "Statut Action": st.column_config.SelectboxColumn(options=config.VALEURS_LISTE_ACTIONS_STATUTACTION, required=False),
                "Statut Opportunuité Taf": st.column_config.SelectboxColumn(options=config.VALEURS_LISTE_ACTIONS_STATUTOPPORTUNITE, required=False)
            }

            edited_df_actions = st.data_editor(
                df_display_actions,
                key="editor_actions",
                num_rows="dynamic",
                use_container_width=True,
                column_config=column_config_actions
            )

            if "Supprimer ?" in edited_df_actions.columns:
                rows_to_delete_mask_actions = edited_df_actions["Supprimer ?"] == True
                num_rows_to_delete_actions = rows_to_delete_mask_actions.sum()
                
                st.session_state.df_actions = edited_df_actions[~rows_to_delete_mask_actions].drop(columns=["Supprimer ?"], errors='ignore')
                
                if num_rows_to_delete_actions > 0:
                    st.toast(f"{num_rows_to_delete_actions} action(s) marquée(s) pour suppression et retirée(s) de la vue. N'oubliez pas de sauvegarder les changements globaux du CRM.")
            else:
                st.session_state.df_actions = edited_df_actions

        # Ensure final schema using the utility function
        st.session_state.df_actions = data_utils.ensure_df_schema(st.session_state.df_actions, EXPECTED_ACTION_COLS)
        # Coerce 'Date Action' to datetime after schema is ensured, as data_editor might change its type
        if 'Date Action' in st.session_state.df_actions.columns:
             st.session_state.df_actions['Date Action'] = pd.to_datetime(st.session_state.df_actions['Date Action'], errors='coerce')

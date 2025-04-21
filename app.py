import streamlit as st
# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(layout="wide")

import pandas as pd
import pydeck as pdk
import datetime

# Importer les modules locaux
import config
import data_utils
import api_client
import geo_utils

# --- TITRE ET DESCRIPTION ---
st.title("🔎 Recherche d'entreprises pour candidatures spontanées")
st.markdown("Trouvez des entreprises en fonction d'une adresse, d'un rayon, de secteurs d'activité (NAF) et de tranches d'effectifs salariés.")

# --- Vérification chargement NAF ---
if data_utils.naf_detailed_lookup is None:
    st.error("Erreur critique : Le dictionnaire NAF n'a pas pu être chargé. L'application ne peut pas continuer.")
    st.stop()

# --- SIDEBAR : SAISIE DES PARAMÈTRES ---
with st.sidebar:
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
                        "html": "<b>{Nom complet}</b><br/>SIRET: {SIRET}<br/>Activité: {Activité NAF/APE}<br/>Effectif Étab.: {Nb salariés établissement}",
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


# --- PIED DE PAGE ---
st.sidebar.markdown("---")
st.sidebar.info(f"🗓️ {datetime.date.today().strftime('%d/%m/%Y')}")
st.sidebar.info("API: recherche-entreprises.api.gouv.fr & BAN France")

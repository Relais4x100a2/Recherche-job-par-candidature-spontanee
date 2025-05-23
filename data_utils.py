# /home/guillaumecayeux/code_dev/recherche_job_candidature_spontanée/data_utils.py
import streamlit as st
import pandas as pd
from functools import lru_cache
import datetime 
from io import BytesIO # Nécessaire pour l'export Excel en mémoire
from openpyxl import Workbook # Bien que pandas utilise openpyxl, l'importer peut aider pour des manips avancées si besoin
from openpyxl.worksheet.datavalidation import DataValidation # Pour les listes déroulantes et restrictions


# Importer la configuration
import config

# --- Chargement et mise en cache du dictionnaire NAF ---
@st.cache_data # Utiliser le cache Streamlit pour le chargement initial
def load_naf_dictionary(file_path=config.NAF_FILE_PATH):
    """Charge le fichier NAF et retourne un dictionnaire Code -> Libellé."""
    try:
        try:
            df_naf = pd.read_csv(file_path, sep=',', dtype={'Code': str}, encoding='utf-8')
            if 'Code' not in df_naf.columns or 'Libellé' not in df_naf.columns:
                 raise ValueError("Colonnes 'Code' ou 'Libellé' manquantes avec sep=','")
        except (ValueError, pd.errors.ParserError, UnicodeDecodeError):
            # Essayer avec séparateur ';' et encodage utf-8
            try:
                # st.warning(f"Échec lecture de {file_path} avec sep=',' et encodage utf-8. Essai avec ';'.")
                df_naf = pd.read_csv(file_path, sep=';', dtype={'Code': str}, encoding='utf-8')
                if 'Code' not in df_naf.columns or 'Libellé' not in df_naf.columns:
                    raise ValueError("Colonnes 'Code' ou 'Libellé' manquantes avec sep=';'")
            except (ValueError, pd.errors.ParserError, UnicodeDecodeError):
                 # Essayer avec séparateur ',' et encodage latin-1
                try:
                    #  st.warning(f"Échec lecture de {file_path} avec sep=';' et encodage utf-8. Essai avec latin-1.")
                     df_naf = pd.read_csv(file_path, sep=',', dtype={'Code': str}, encoding='latin-1')
                     if 'Code' not in df_naf.columns or 'Libellé' not in df_naf.columns:
                         raise ValueError("Colonnes 'Code' ou 'Libellé' manquantes avec sep=',', latin-1")
                except (ValueError, pd.errors.ParserError, UnicodeDecodeError):
                     # Essayer avec séparateur ';' et encodage latin-1
                    #  st.warning(f"Échec lecture de {file_path} avec sep=',' et encodage latin-1. Essai avec ';'.")
                     df_naf = pd.read_csv(file_path, sep=';', dtype={'Code': str}, encoding='latin-1')
                     if 'Code' not in df_naf.columns or 'Libellé' not in df_naf.columns:
                         st.error(f"Colonnes 'Code' et 'Libellé' introuvables dans {file_path} avec les séparateurs et encodages testés.")
                         return None

        if df_naf.empty:
            st.error(f"Le fichier NAF '{file_path}' est vide ou n'a pas pu être lu correctement.")
            return None

        # Nettoyage des colonnes et des codes
        df_naf.columns = df_naf.columns.str.strip()
        df_naf['Code'] = df_naf['Code'].astype(str).str.strip()

        # Vérification des doublons
        if df_naf['Code'].duplicated().any():
            # st.warning(f"Attention : Codes NAF dupliqués trouvés dans {file_path}. Seul le dernier sera conservé.")
            df_naf = df_naf.drop_duplicates(subset='Code', keep='last')

        # Création du dictionnaire
        naf_dict = df_naf.set_index('Code')['Libellé'].to_dict()
        # st.success(f"Dictionnaire NAF chargé avec {len(naf_dict)} entrées.") # Confirmation
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

# Charger le dictionnaire une fois au démarrage du module
naf_detailed_lookup = load_naf_dictionary()

# --- Fonctions Helper NAF (mises en cache) ---
@lru_cache(maxsize=None)
def get_section_for_code(code):
    """Retourne la lettre de section pour un code NAF donné."""
    if not code or not isinstance(code, str):
        return None
    # Gère les codes comme '62.01Z' ou '01.12Z'
    code_cleaned = code.strip().replace('.', '')[:2]
    return config.NAF_SECTION_MAP.get(code_cleaned)

@lru_cache(maxsize=None)
def get_codes_for_section(section_letter):
    """Retourne une liste triée de tous les codes NAF appartenant à une section."""
    if not naf_detailed_lookup or not section_letter:
        return []
    # Itère sur les clés du dictionnaire chargé dans ce module
    codes = [code for code in naf_detailed_lookup if get_section_for_code(code) == section_letter]
    return sorted(codes)

# --- Fonction de correspondance NAF ---
def correspondance_NAF(code_naf_input):
    """Retourne le libellé NAF détaillé pour un code donné."""
    if naf_detailed_lookup is None:
        # Ce cas ne devrait pas arriver si le chargement initial a réussi
        return f"{code_naf_input} (Dico NAF non chargé)"
    if not code_naf_input or not isinstance(code_naf_input, str):
        return "Code NAF invalide"
    code_naf_clean = code_naf_input.strip()
    return naf_detailed_lookup.get(code_naf_clean, f"{code_naf_clean} (Libellé non trouvé)")

# --- Traitement de la réponse API ---
def traitement_reponse_api(entreprises, selected_effectifs_codes):
    """Prépare les données pour l'affichage et le téléchargement."""
    if not entreprises:
        return pd.DataFrame()

    all_etablissements_data = []
    processed_sirens = set() # Pour éviter de traiter les finances plusieurs fois

    for entreprise in entreprises:
        siren = entreprise.get('siren')
        nom_complet = entreprise.get('nom_complet')
        nom_sociale = entreprise.get('nom_raison_sociale')
        date_creation = entreprise.get('date_creation')
        nombre_etablissements_ouverts = entreprise.get('nombre_etablissements_ouverts')
        code_naf_entreprise = entreprise.get('activite_principale')
        tranche_effectif_salarie_entreprise = entreprise.get('tranche_effectif_salarie')
        tranche_description_entreprise = config.effectifs_tranches.get(tranche_effectif_salarie_entreprise, 'N/A')

        # Traitement Finances (une seule fois par SIREN)
        latest_year_str = None
        ca_latest = None
        resultat_net_latest = None
        if siren and siren not in processed_sirens:
            processed_sirens.add(siren)
            finances = entreprise.get("finances", {})
            if finances and isinstance(finances, dict):
                try:
                    available_years = [year for year in finances.keys() if year.isdigit()]
                    if available_years:
                        latest_year_str = max(available_years)
                        latest_year_data = finances.get(latest_year_str, {})
                        ca_latest = latest_year_data.get("ca")
                        resultat_net_latest = latest_year_data.get("resultat_net")
                except Exception as e:
                    print(f"Avertissement: Erreur extraction finances pour SIREN {siren}: {e}")
                    latest_year_str = 'Erreur'

        # Traitement des établissements correspondants
        matching_etablissements = entreprise.get('matching_etablissements', [])
        for etab in matching_etablissements:
            etat_etab = etab.get('etat_administratif')
            tranche_eff_etab = etab.get('tranche_effectif_salarie')

            # Assurer que selected_effectifs_codes est un set
            if not isinstance(selected_effectifs_codes, set):
                selected_effectifs_codes_set = set(selected_effectifs_codes)
            else:
                selected_effectifs_codes_set = selected_effectifs_codes

            # Filtrer sur état actif et tranche effectif sélectionnée
            if etat_etab == 'A' and tranche_eff_etab in selected_effectifs_codes_set:
                all_etablissements_data.append({
                    'SIRET': etab.get('siret'),
                    'SIREN': siren,
                    'tranche_effectif_salarie_etablissement': tranche_eff_etab,
                    'annee_tranche_effectif_salarie': etab.get('annee_tranche_effectif_salarie'),
                    'code_naf_etablissement': etab.get('activite_principale'),
                    'adresse': etab.get('adresse'),
                    'latitude': etab.get('latitude'),
                    'longitude': etab.get('longitude'),
                    'liste_enseignes': etab.get('liste_enseignes', []),
                    'est_siege': etab.get('est_siege', False),
                    'nom_complet_entreprise': nom_complet,
                    'nom_sociale_entreprise': nom_sociale,
                    'date_creation_entreprise': date_creation,
                    'nb_etab_ouverts_entreprise': nombre_etablissements_ouverts,
                    'code_naf_entreprise': code_naf_entreprise,
                    'tranche_desc_entreprise': tranche_description_entreprise,
                    'annee_finances': latest_year_str,
                    'ca_entreprise': ca_latest,
                    'resultat_net_entreprise': resultat_net_latest,
                })

    if not all_etablissements_data:
        return pd.DataFrame()

    df_filtered = pd.DataFrame(all_etablissements_data)

    # Enrichissement des données
    # df_filtered['Code NAF'] = df_filtered['code_naf_etablissement'].fillna(df_filtered['code_naf_entreprise']).astype(str)
    # df_filtered['Activité NAF/APE'] = df_filtered['Code NAF'].apply(lambda x: correspondance_NAF(x) if pd.notna(x) and x != 'nan' else 'N/A')
    df_filtered['Activité NAF/APE Entreprise'] = df_filtered['code_naf_entreprise'].apply(lambda x: correspondance_NAF(x) if pd.notna(x) and x != 'nan' else 'N/A')
    df_filtered['Activité NAF/APE Etablissement'] = df_filtered['code_naf_etablissement'].apply(lambda x: correspondance_NAF(x) if pd.notna(x) and x != 'nan' else 'N/A')
    df_filtered['Nb salariés établissement'] = df_filtered['tranche_effectif_salarie_etablissement'].map(config.effectifs_tranches).fillna('N/A')
    # Utiliser code_naf_etablissement pour Section NAF, couleur et radius car plus spécifique à l'établissement affiché
    df_filtered['Section NAF'] = df_filtered['code_naf_etablissement'].apply(get_section_for_code).fillna('N/A')
    df_filtered['Color'] = df_filtered['Section NAF'].apply(lambda section: config.naf_color_mapping.get(section, config.naf_color_mapping['N/A']))
    df_filtered['Radius'] = df_filtered['tranche_effectif_salarie_etablissement'].map(config.size_mapping).fillna(config.size_mapping.get('N/A', 10))

    # Conversion numérique et gestion des erreurs
    df_filtered['Latitude'] = pd.to_numeric(df_filtered['latitude'], errors='coerce')
    df_filtered['Longitude'] = pd.to_numeric(df_filtered['longitude'], errors='coerce')
    df_filtered['Chiffre d\'Affaires Entreprise'] = pd.to_numeric(df_filtered['ca_entreprise'], errors='coerce')
    df_filtered['Résultat Net Entreprise'] = pd.to_numeric(df_filtered['resultat_net_entreprise'], errors='coerce')

    # Formatage des listes (enseignes)
    df_filtered['Enseignes'] = df_filtered['liste_enseignes'].apply(lambda x: ', '.join(x) if isinstance(x, list) and x else 'N/A')

    # Renommage et sélection finale des colonnes
    final_df = df_filtered.rename(columns={
        'nom_complet_entreprise': 'Nom complet',
        'est_siege': 'Est siège social',
        'adresse': 'Adresse établissement',
        'tranche_effectif_salarie_etablissement': 'Code effectif établissement',
        'annee_tranche_effectif_salarie': 'Année nb salariés établissement',
        'nom_sociale_entreprise': 'Raison sociale',
        'date_creation_entreprise': 'Date de création Entreprise',
        'nb_etab_ouverts_entreprise': 'Nb total établissements ouverts',
        'tranche_desc_entreprise': 'Nb salariés entreprise',
        'annee_finances': 'Année Finances Entreprise',
        # Les colonnes 'Chiffre d\'Affaires Entreprise' et 'Résultat Net Entreprise'
        # sont déjà correctement nommées et n'ont pas besoin d'être dans rename()
    })

    # Garder seulement les colonnes existantes dans l'ordre défini par config
    cols_existantes = [col for col in config.COLS_EXPORT_ORDER if col in final_df.columns]
    return final_df[cols_existantes]

def generate_crm_excel(df_entreprises):
    """
    Génère un fichier Excel (.xlsx) avec 3 feuilles (Entreprises, Contacts, Actions)
    pour le suivi CRM, incluant la validation des données.

    Args:
        df_entreprises (pd.DataFrame): Le DataFrame des résultats de recherche (après traitement).

    Returns:
        bytes: Le contenu binaire du fichier Excel.
    """
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # --- Feuille 1: Entreprises ---
        cols_crm_entreprises = [
        'SIRET', 'Nom complet', 'Enseignes',
        'Activité NAF/APE Etablissement',  # Modifié
        'code_naf_etablissement', # Pour garder le code brut si besoin, renommé plus bas si nécessaire ou utilisé direct
        'Activité NAF/APE Entreprise', # Ajouté
        'code_naf_entreprise', # Pour garder le code brut si besoin
            'Adresse établissement', 'Nb salariés établissement', 'Est siège social',
        'Date de création Entreprise', 'Chiffre d\'Affaires Entreprise',
        'Résultat Net Entreprise', 'Année Finances Entreprise', 'SIREN'
        ]
        # Sélectionner et réorganiser les colonnes pertinentes
        df_crm_entreprises = df_entreprises[[col for col in cols_crm_entreprises if col in df_entreprises.columns]].copy()
        df_crm_entreprises.to_excel(writer, sheet_name='Entreprises', index=False, freeze_panes=(1, 0)) # Freeze top row

        # --- Feuille 2: Contacts (Vide, prête à remplir) ---
        cols_contacts = [
            'ID Contact', 'Prénom', 'Nom', 'Poste', 'Email', 'Téléphone',
            'LinkedIn URL', 'SIRET Entreprise', 'Notes'
        ]
        df_contacts = pd.DataFrame(columns=cols_contacts)
        df_contacts.to_excel(writer, sheet_name='Contacts', index=False, freeze_panes=(1, 0))

        # --- Feuille 3: Actions (Vide, prête à remplir) ---
        cols_actions = [
            'ID Action', 'Date Action', 'SIRET Entreprise', 'ID Contact',
            'Type Action', 'Statut', 'Description/Notes'
        ]
        df_actions = pd.DataFrame(columns=cols_actions)
        df_actions.to_excel(writer, sheet_name='Actions', index=False, freeze_panes=(1, 0))

        # --- Ajout de la Validation des Données ---
        workbook = writer.book
        ws_entreprises = workbook['Entreprises']
        ws_contacts = workbook['Contacts']
        ws_actions = workbook['Actions']

        max_row_excel = 1048576 # Limite Excel pour les plages de validation

        # 1. Validation SIRET dans Contacts (colonne H si l'ordre est respecté)
        if not df_crm_entreprises.empty:
            siret_list_formula = f"=Entreprises!$A$2:$A${len(df_crm_entreprises) + 1}"
            dv_siret_contact = DataValidation(type="list", formula1=siret_list_formula, allow_blank=True)
            dv_siret_contact.error = "Le SIRET doit provenir de la feuille 'Entreprises'."
            dv_siret_contact.errorTitle = 'SIRET Invalide'
            dv_siret_contact.prompt = "Choisissez un SIRET dans la liste"
            dv_siret_contact.promptTitle = 'SIRET Entreprise'
            # Appliquer à la colonne H (SIRET Entreprise) de la feuille Contacts
            ws_contacts.add_data_validation(dv_siret_contact)
            dv_siret_contact.add(f'H2:H{max_row_excel}') # Appliquer à toute la colonne à partir de la ligne 2

            # 2. Validation SIRET dans Actions (colonne C)
            dv_siret_action = DataValidation(type="list", formula1=siret_list_formula, allow_blank=True)
            dv_siret_action.error = "Le SIRET doit provenir de la feuille 'Entreprises'."
            dv_siret_action.errorTitle = 'SIRET Invalide'
            dv_siret_action.prompt = "Choisissez un SIRET dans la liste"
            dv_siret_action.promptTitle = 'SIRET Entreprise'
            ws_actions.add_data_validation(dv_siret_action)
            dv_siret_action.add(f'C2:C{max_row_excel}')

        # 3. Validation ID Contact dans Actions (colonne D) - Attention: se base sur ce que l'utilisateur remplira
        # On crée la règle, mais elle ne sera utile que si l'utilisateur remplit les ID Contacts
        contact_id_list_formula = f"=Contacts!$A$2:$A${max_row_excel}" # Prend toute la colonne A de Contacts
        dv_contact_id_action = DataValidation(type="list", formula1=contact_id_list_formula, allow_blank=True)
        dv_contact_id_action.error = "L'ID Contact doit provenir de la feuille 'Contacts'."
        dv_contact_id_action.errorTitle = 'ID Contact Invalide'
        dv_contact_id_action.prompt = "Choisissez un ID Contact dans la liste (si applicable)"
        dv_contact_id_action.promptTitle = 'ID Contact'
        ws_actions.add_data_validation(dv_contact_id_action)
        dv_contact_id_action.add(f'D2:D{max_row_excel}')

        # 4. Listes déroulantes pour Type Action et Statut dans Actions (colonnes E et F)
        type_action_list = '"Candidature envoyée,Relance téléphonique,Relance email,Entretien RH,Entretien technique,Entretien manager,Proposition,Refus,Acceptation,Autre"'
        dv_type_action = DataValidation(type="list", formula1=type_action_list, allow_blank=True)
        dv_type_action.prompt = "Choisissez un type d'action"
        dv_type_action.promptTitle = 'Type Action'
        ws_actions.add_data_validation(dv_type_action)
        dv_type_action.add(f'E2:E{max_row_excel}')

        statut_action_list = '"À faire,En cours,Terminé,En attente,Annulé"'
        dv_statut_action = DataValidation(type="list", formula1=statut_action_list, allow_blank=True)
        dv_statut_action.prompt = "Choisissez un statut"
        dv_statut_action.promptTitle = 'Statut'
        ws_actions.add_data_validation(dv_statut_action)
        dv_statut_action.add(f'F2:F{max_row_excel}')

        # Ajuster la largeur des colonnes (optionnel mais améliore la lisibilité)
        for sheet in [ws_entreprises, ws_contacts, ws_actions]:
            for col in sheet.columns:
                max_length = 0
                column = col[0].column_letter # Get the column name
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2) * 1.2
                sheet.column_dimensions[column].width = min(adjusted_width, 50) # Limiter la largeur max

    # Le writer est fermé automatiquement ici, le buffer est prêt
    return output.getvalue()

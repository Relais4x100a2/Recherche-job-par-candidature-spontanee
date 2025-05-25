# /home/guillaumecayeux/code_dev/recherche_job_candidature_spontanée/data_utils.py
import streamlit as st
import pandas as pd
from functools import lru_cache
import datetime
from io import BytesIO
# Removed: import openpyxl - pandas uses it via ExcelWriter, direct use not strictly needed if formulas written via pandas/xlsxwriter methods
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill, Alignment # Added for styling
import numpy as np # For pd.NA if used

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
            try:
                df_naf = pd.read_csv(file_path, sep=';', dtype={'Code': str}, encoding='utf-8')
                if 'Code' not in df_naf.columns or 'Libellé' not in df_naf.columns:
                    raise ValueError("Colonnes 'Code' ou 'Libellé' manquantes avec sep=';'")
            except (ValueError, pd.errors.ParserError, UnicodeDecodeError):
                try:
                     df_naf = pd.read_csv(file_path, sep=',', dtype={'Code': str}, encoding='latin-1')
                     if 'Code' not in df_naf.columns or 'Libellé' not in df_naf.columns:
                         raise ValueError("Colonnes 'Code' ou 'Libellé' manquantes avec sep=',', latin-1")
                except (ValueError, pd.errors.ParserError, UnicodeDecodeError):
                     df_naf = pd.read_csv(file_path, sep=';', dtype={'Code': str}, encoding='latin-1')
                     if 'Code' not in df_naf.columns or 'Libellé' not in df_naf.columns:
                         st.error(f"Colonnes 'Code' et 'Libellé' introuvables dans {file_path} avec les séparateurs et encodages testés.")
                         return None
        if df_naf.empty:
            st.error(f"Le fichier NAF '{file_path}' est vide ou n'a pas pu être lu correctement.")
            return None
        df_naf.columns = df_naf.columns.str.strip()
        df_naf['Code'] = df_naf['Code'].astype(str).str.strip()
        if df_naf['Code'].duplicated().any():
            df_naf = df_naf.drop_duplicates(subset='Code', keep='last')
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

naf_detailed_lookup = load_naf_dictionary()

@lru_cache(maxsize=None)
def get_section_for_code(code):
    if not code or not isinstance(code, str): return None
    code_cleaned = code.strip().replace('.', '')[:2]
    return config.NAF_SECTION_MAP.get(code_cleaned)

@lru_cache(maxsize=None)
def get_codes_for_section(section_letter):
    if not naf_detailed_lookup or not section_letter: return []
    codes = [code for code in naf_detailed_lookup if get_section_for_code(code) == section_letter]
    return sorted(codes)

def correspondance_NAF(code_naf_input):
    if naf_detailed_lookup is None: return f"{code_naf_input} (Dico NAF non chargé)"
    if not code_naf_input or not isinstance(code_naf_input, str): return "Code NAF invalide"
    code_naf_clean = code_naf_input.strip()
    return naf_detailed_lookup.get(code_naf_clean, f"{code_naf_clean} (Libellé non trouvé)")

def traitement_reponse_api(entreprises, selected_effectifs_codes):
    if not entreprises: return pd.DataFrame()
    all_etablissements_data = []
    processed_sirens = set()
    for entreprise in entreprises:
        siren = entreprise.get('siren')
        nom_complet = entreprise.get('nom_complet')
        nom_sociale = entreprise.get('nom_raison_sociale')
        date_creation = entreprise.get('date_creation')
        nombre_etablissements_ouverts = entreprise.get('nombre_etablissements_ouverts')
        code_naf_entreprise = entreprise.get('activite_principale')
        tranche_effectif_salarie_entreprise = entreprise.get('tranche_effectif_salarie')
        tranche_description_entreprise = config.effectifs_tranches.get(tranche_effectif_salarie_entreprise, 'N/A')
        latest_year_str, ca_latest, resultat_net_latest = None, None, None
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
        matching_etablissements = entreprise.get('matching_etablissements', [])
        for etab in matching_etablissements:
            etat_etab = etab.get('etat_administratif')
            tranche_eff_etab = etab.get('tranche_effectif_salarie')
            selected_effectifs_codes_set = set(selected_effectifs_codes) if not isinstance(selected_effectifs_codes, set) else selected_effectifs_codes
            if etat_etab == 'A' and tranche_eff_etab in selected_effectifs_codes_set:
                all_etablissements_data.append({
                    'SIRET': etab.get('siret'), 'SIREN': siren,
                    'tranche_effectif_salarie_etablissement': tranche_eff_etab,
                    'annee_tranche_effectif_salarie': etab.get('annee_tranche_effectif_salarie'),
                    'code_naf_etablissement': etab.get('activite_principale'),
                    'adresse': etab.get('adresse'), 'latitude': etab.get('latitude'), 'longitude': etab.get('longitude'),
                    'liste_enseignes': etab.get('liste_enseignes', []), 'est_siege': etab.get('est_siege', False),
                    'nom_complet_entreprise': nom_complet, 'nom_sociale_entreprise': nom_sociale,
                    'date_creation_entreprise': date_creation, 'nb_etab_ouverts_entreprise': nombre_etablissements_ouverts,
                    'code_naf_entreprise': code_naf_entreprise, 'tranche_desc_entreprise': tranche_description_entreprise,
                    'annee_finances': latest_year_str, 'ca_entreprise': ca_latest, 'resultat_net_entreprise': resultat_net_latest,
                })
    if not all_etablissements_data: return pd.DataFrame()
    df_filtered = pd.DataFrame(all_etablissements_data)
    df_filtered['Activité NAF/APE Entreprise'] = df_filtered['code_naf_entreprise'].apply(lambda x: correspondance_NAF(x) if pd.notna(x) and x != 'nan' else 'N/A')
    df_filtered['Activité NAF/APE Etablissement'] = df_filtered['code_naf_etablissement'].apply(lambda x: correspondance_NAF(x) if pd.notna(x) and x != 'nan' else 'N/A')
    df_filtered['Nb salariés établissement'] = df_filtered['tranche_effectif_salarie_etablissement'].map(config.effectifs_tranches).fillna('N/A')
    df_filtered['Section NAF'] = df_filtered['code_naf_etablissement'].apply(get_section_for_code).fillna('N/A')
    df_filtered['Color'] = df_filtered['Section NAF'].apply(lambda section: config.naf_color_mapping.get(section, config.naf_color_mapping['N/A']))
    df_filtered['Radius'] = df_filtered['tranche_effectif_salarie_etablissement'].map(config.size_mapping).fillna(config.size_mapping.get('N/A', 10))
    df_filtered['Latitude'] = pd.to_numeric(df_filtered['latitude'], errors='coerce')
    df_filtered['Longitude'] = pd.to_numeric(df_filtered['longitude'], errors='coerce')
    df_filtered['Chiffre d\'Affaires Entreprise'] = pd.to_numeric(df_filtered['ca_entreprise'], errors='coerce')
    df_filtered['Résultat Net Entreprise'] = pd.to_numeric(df_filtered['resultat_net_entreprise'], errors='coerce')
    df_filtered['Enseignes'] = df_filtered['liste_enseignes'].apply(lambda x: ', '.join(x) if isinstance(x, list) and x else 'N/A')
    final_df = df_filtered.rename(columns={
        'nom_complet_entreprise': 'Nom complet', 'est_siege': 'Est siège social',
        'adresse': 'Adresse établissement', 'tranche_effectif_salarie_etablissement': 'Code effectif établissement',
        'annee_tranche_effectif_salarie': 'Année nb salariés établissement',
        'nom_sociale_entreprise': 'Raison sociale', 'date_creation_entreprise': 'Date de création Entreprise',
        'nb_etab_ouverts_entreprise': 'Nb total établissements ouverts',
        'tranche_desc_entreprise': 'Nb salariés entreprise', 'annee_finances': 'Année Finances Entreprise',
    })
    cols_existantes = [col for col in config.COLS_EXPORT_ORDER if col in final_df.columns]
    return final_df[cols_existantes]

def generate_crm_excel(df_entreprises_input: pd.DataFrame):
    """
    Génère un fichier Excel (.xlsx) à partir de zéro avec plusieurs feuilles (DATA_IMPORT, ENTREPRISES, etc.),
    des formules, des données statiques, et des règles de validation de données.

    Args:
        df_entreprises_input (pd.DataFrame): Le DataFrame des résultats de recherche.

    Returns:
        bytes: Le contenu binaire du fichier Excel, ou None en cas d'erreur.
    """
    output = BytesIO()
    try:
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            workbook = writer.book # Get the openpyxl workbook object

            # 1. DATA_IMPORT Sheet
            data_import_cols = [
                'SIRET', 'Nom complet', 'Enseignes', 'Activité NAF/APE Etablissement', 
                'code_naf_etablissement', 'Activité NAF/APE Entreprise', 'code_naf_entreprise', 
                'Adresse établissement', 'Nb salariés établissement', 'Est siège social', 
                'Date de création Entreprise', "Chiffre d'Affaires Entreprise", 
                'Résultat Net Entreprise', 'Année Finances Entreprise', 'SIREN'
            ]
            df_data_import = pd.DataFrame()
            for col in data_import_cols:
                if col in df_entreprises_input.columns:
                    df_data_import[col] = df_entreprises_input[col]
                else:
                    df_data_import[col] = np.nan # Use np.nan for missing columns
            
            df_data_import = df_data_import[data_import_cols] # Ensure correct order
            df_data_import.to_excel(writer, sheet_name='DATA_IMPORT', index=False, freeze_panes=(1, 0))
            num_data_rows = len(df_data_import)

            # 2. ENTREPRISES Sheet
            entreprises_headers = [
                'SIRET', 'Nom complet', 'Enseignes', 'Activité NAF/APE établissement', 
                'Adresse établissement', 'Recherche LinkedIn', 'Recherche Google Maps', 
                'Nb salariés établissement', 'Est siège social', 'Date de création Entreprise', 
                "Chiffre d'Affaires Entreprise", 'Résultat Net Entreprise', 
                'Année Finances Entreprise', 'SIREN'
            ]
            # Create empty DataFrame for headers, formulas will be written by openpyxl
            df_entreprises_sheet_headers_only = pd.DataFrame(columns=entreprises_headers)
            df_entreprises_sheet_headers_only.to_excel(writer, sheet_name='ENTREPRISES', index=False, freeze_panes=(1, 0))
            
            ws_entreprises = workbook['ENTREPRISES'] # Get the sheet after pandas creates it
            
            # Write formulas row by row
            # Column mapping for ENTREPRISES sheet (1-indexed for openpyxl)
            # B: Nom complet, E: Adresse établissement
            for r_idx in range(num_data_rows):
                excel_row = r_idx + 2 # Excel rows are 1-indexed, data starts on row 2
                ws_entreprises.cell(row=excel_row, column=1, value=f"=DATA_IMPORT!A{excel_row}")  # SIRET
                ws_entreprises.cell(row=excel_row, column=2, value=f"=DATA_IMPORT!B{excel_row}")  # Nom complet
                ws_entreprises.cell(row=excel_row, column=3, value=f"=DATA_IMPORT!C{excel_row}")  # Enseignes
                ws_entreprises.cell(row=excel_row, column=4, value=f"=DATA_IMPORT!D{excel_row}")  # Activité NAF/APE établissement
                ws_entreprises.cell(row=excel_row, column=5, value=f"=DATA_IMPORT!H{excel_row}")  # Adresse établissement
                # Recherche LinkedIn: HYPERLINK("google search for B{excel_row} + linkedin", "Recherche LinkedIn " & B{excel_row})
                # B{excel_row} in ENTREPRISES sheet is Nom complet
                ws_entreprises.cell(row=excel_row, column=6, value=f'=HYPERLINK("https://www.google.com/search?q="&B{excel_row}&"+site%3Alinkedin.com","Recherche LinkedIn "&B{excel_row}&"")')
                # Recherche Google Maps: HYPERLINK("google maps search for B{excel_row} , E{excel_row}", "Recherche Google Maps " & B{excel_row})
                # B{excel_row} is Nom complet, E{excel_row} is Adresse établissement in ENTREPRISES sheet
                ws_entreprises.cell(row=excel_row, column=7, value=f'=HYPERLINK("https://www.google.com/maps/search/?api=1&query="&B{excel_row}&","&E{excel_row}&"","Recherche Google Maps "&B{excel_row}&"")')
                ws_entreprises.cell(row=excel_row, column=8, value=f"=DATA_IMPORT!I{excel_row}")  # Nb salariés établissement
                ws_entreprises.cell(row=excel_row, column=9, value=f"=DATA_IMPORT!J{excel_row}")  # Est siège social
                ws_entreprises.cell(row=excel_row, column=10, value=f"=DATA_IMPORT!K{excel_row}") # Date de création Entreprise
                ws_entreprises.cell(row=excel_row, column=11, value=f"=DATA_IMPORT!L{excel_row}")# Chiffre d'Affaires Entreprise
                ws_entreprises.cell(row=excel_row, column=12, value=f"=DATA_IMPORT!M{excel_row}")# Résultat Net Entreprise
                ws_entreprises.cell(row=excel_row, column=13, value=f"=DATA_IMPORT!N{excel_row}")# Année Finances Entreprise
                ws_entreprises.cell(row=excel_row, column=14, value=f"=DATA_IMPORT!O{excel_row}") # SIREN
            
            # 3. VALEURS_LISTE Sheet
            vl_headers = ['CONTACTS_Direction', 'ACTIONS_TypeAction', 'ACTIONS_StatutAction', 'ACTIONS_StatutOpportunuiteTaf']
            
            # Use global lists from config.py
            vl_data_from_config = {
                'CONTACTS_Direction': config.VALEURS_LISTE_CONTACTS_DIRECTION,
                'ACTIONS_TypeAction': config.VALEURS_LISTE_ACTIONS_TYPEACTION,
                'ACTIONS_StatutAction': config.VALEURS_LISTE_ACTIONS_STATUTACTION,
                'ACTIONS_StatutOpportunuiteTaf': config.VALEURS_LISTE_ACTIONS_STATUTOPPORTUNITE
            }
            
            # Create DataFrame by padding shorter lists with None to make them equal length for DataFrame creation
            max_len = max(len(lst) for lst in vl_data_from_config.values())
            padded_vl_data = {col: lst + [None]*(max_len - len(lst)) for col, lst in vl_data_from_config.items()}
            df_valeurs_liste = pd.DataFrame(padded_vl_data)
            df_valeurs_liste = df_valeurs_liste[vl_headers] # Ensure column order
            df_valeurs_liste.to_excel(writer, sheet_name='VALEURS_LISTE', index=False, freeze_panes=(1, 0))

            # 4. CONTACTS Sheet
            contacts_headers = ['Prénom Nom', 'Entreprise', 'Poste', 'Direction', 'Email', 'Téléphone', 'Profil LinkedIn URL', 'Notes']
            df_contacts = pd.DataFrame(columns=contacts_headers)
            df_contacts.to_excel(writer, sheet_name='CONTACTS', index=False, freeze_panes=(1, 0))

            # 5. ACTIONS Sheet
            actions_headers = ['Entreprise', 'Contact (Prénom Nom)', 'Type Action', 'Date Action', 'Description/Notes', 'Statut Action', 'Statut Opportunuité Taf']
            df_actions = pd.DataFrame(columns=actions_headers)
            df_actions.to_excel(writer, sheet_name='ACTIONS', index=False, freeze_panes=(1, 0))

            # 6. Data Validation
            max_row_validation = 5000
            
            # CONTACTS Sheet Validations
            ws_contacts = workbook['CONTACTS']
            dv_contacts_entreprise = DataValidation(type="list", formula1=f"=ENTREPRISES!$B$2:$B${max_row_validation}", allow_blank=True)
            dv_contacts_entreprise.error = "Veuillez choisir une entreprise de la liste (Feuille ENTREPRISES, colonne 'Nom complet')."
            dv_contacts_entreprise.errorTitle = "Entreprise Invalide"
            ws_contacts.add_data_validation(dv_contacts_entreprise)
            dv_contacts_entreprise.add(f"B2:B{max_row_validation}")

            dv_contacts_direction = DataValidation(type="list", formula1=f"=VALEURS_LISTE!$A$2:$A${max_row_validation}", allow_blank=True)
            dv_contacts_direction.error = "Veuillez choisir une direction de la liste (Feuille VALEURS_LISTE, colonne 'CONTACTS_Direction')."
            dv_contacts_direction.errorTitle = "Direction Invalide"
            ws_contacts.add_data_validation(dv_contacts_direction)
            dv_contacts_direction.add(f"D2:D{max_row_validation}")

            # ACTIONS Sheet Validations
            ws_actions = workbook['ACTIONS']
            dv_actions_entreprise = DataValidation(type="list", formula1=f"=ENTREPRISES!$B$2:$B${max_row_validation}", allow_blank=True)
            dv_actions_entreprise.error = "Veuillez choisir une entreprise de la liste (Feuille ENTREPRISES, colonne 'Nom complet')."
            dv_actions_entreprise.errorTitle = "Entreprise Invalide"
            ws_actions.add_data_validation(dv_actions_entreprise)
            dv_actions_entreprise.add(f"A2:A{max_row_validation}")

            dv_actions_contact = DataValidation(type="list", formula1=f"=CONTACTS!$A$2:$A${max_row_validation}", allow_blank=True)
            dv_actions_contact.error = "Veuillez choisir un contact de la liste (Feuille CONTACTS, colonne 'Prénom Nom')."
            dv_actions_contact.errorTitle = "Contact Invalide"
            ws_actions.add_data_validation(dv_actions_contact)
            dv_actions_contact.add(f"B2:B{max_row_validation}")

            dv_actions_type = DataValidation(type="list", formula1=f"=VALEURS_LISTE!$B$2:$B${max_row_validation}", allow_blank=True)
            dv_actions_type.error = "Veuillez choisir un type d'action (Feuille VALEURS_LISTE, colonne 'ACTIONS_TypeAction')."
            dv_actions_type.errorTitle = "Type d'Action Invalide"
            ws_actions.add_data_validation(dv_actions_type)
            dv_actions_type.add(f"C2:C{max_row_validation}")

            dv_actions_statut = DataValidation(type="list", formula1=f"=VALEURS_LISTE!$C$2:$C${max_row_validation}", allow_blank=True)
            dv_actions_statut.error = "Veuillez choisir un statut d'action (Feuille VALEURS_LISTE, colonne 'ACTIONS_StatutAction')."
            dv_actions_statut.errorTitle = "Statut d'Action Invalide"
            ws_actions.add_data_validation(dv_actions_statut)
            dv_actions_statut.add(f"F2:F{max_row_validation}")

            dv_actions_opportunite = DataValidation(type="list", formula1=f"=VALEURS_LISTE!$D$2:$D${max_row_validation}", allow_blank=True)
            dv_actions_opportunite.error = "Veuillez choisir un statut d'opportunité (Feuille VALEURS_LISTE, colonne 'ACTIONS_StatutOpportunuiteTaf')."
            dv_actions_opportunite.errorTitle = "Statut Opportunité Invalide"
            ws_actions.add_data_validation(dv_actions_opportunite)
            dv_actions_opportunite.add(f"G2:G{max_row_validation}")

            # 7. Formatting: Auto-adjust column widths
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                for col_idx, column in enumerate(sheet.columns): # openpyxl columns are 0-indexed here
                    max_length = 0
                    column_letter = get_column_letter(col_idx + 1)

                    # Calculate max_length based on header
                    header_cell = sheet.cell(row=1, column=col_idx + 1)
                    if header_cell.value:
                        max_length = len(str(header_cell.value))
                    
                    # For DATA_IMPORT and VALEURS_LISTE, check cell content
                    if sheet_name in ['DATA_IMPORT', 'VALEURS_LISTE']:
                        for i, cell in enumerate(column):
                            if i == 0: continue # Skip header already processed
                            try:
                                if cell.value:
                                    cell_len = len(str(cell.value))
                                    if cell_len > max_length:
                                        max_length = cell_len
                            except:
                                pass
                    # For ENTREPRISES, special handling for formula columns if needed (crude estimate)
                    elif sheet_name == 'ENTREPRISES':
                         # Columns F and G are HYPERLINK formulas
                        if col_idx + 1 == 6 or col_idx + 1 == 7: # F or G
                             max_length = max(max_length, 30) # Estimate for hyperlink text
                        else: # For other formula columns, iterate a few rows if populated
                            for i in range(min(5, num_data_rows)): # Check first 5 data rows
                                cell_value_formula = sheet.cell(row=i+2, column=col_idx+1).value
                                if cell_value_formula: # This is the formula string
                                    # Crude: if it's a DATA_IMPORT reference, could try to get corresponding data width
                                    # For now, header width is the main driver for formula columns other than hyperlinks
                                    pass


                    adjusted_width = (max_length + 2) * 1.2 
                    adjusted_width = min(adjusted_width, 60) # Cap max width
                    sheet.column_dimensions[column_letter].width = adjusted_width
            
            # 8. Styling Headers
            header_font = Font(bold=True, color="FFFFFFFF") # White
            header_fill = PatternFill(start_color="FF4472C4", end_color="FF4472C4", fill_type="solid") # Medium Blue
            header_alignment = Alignment(horizontal="center", vertical="center")

            sheets_to_style_headers = ['ENTREPRISES', 'CONTACTS', 'ACTIONS', 'VALEURS_LISTE']
            for sheet_name in sheets_to_style_headers:
                if sheet_name in workbook.sheetnames:
                    sheet = workbook[sheet_name]
                    for cell in sheet[1]: # Iterate through cells in the first row
                        cell.font = header_font
                        cell.fill = header_fill
                        cell.alignment = header_alignment
            
            # 9. Hide DATA_IMPORT sheet
            if 'DATA_IMPORT' in workbook.sheetnames:
                ws_data_import = workbook['DATA_IMPORT']
                ws_data_import.sheet_state = 'hidden'

            # 10. Set Sheet Order
            # Desired order of visible sheets, DATA_IMPORT will be last among (potentially) visible then hidden
            # The actual creation order was: DATA_IMPORT, ENTREPRISES, VALEURS_LISTE, CONTACTS, ACTIONS
            # New desired order: ENTREPRISES, CONTACTS, ACTIONS, VALEURS_LISTE, (DATA_IMPORT hidden)
            
            # Get all sheet titles currently in the workbook
            current_sheet_titles = [sheet.title for sheet in workbook._sheets]

            # Define the desired visible order
            desired_visible_order = ['ENTREPRISES', 'CONTACTS', 'ACTIONS', 'VALEURS_LISTE']
            
            final_ordered_sheets = []
            # Add sheets in the desired visible order
            for title in desired_visible_order:
                if title in current_sheet_titles:
                    final_ordered_sheets.append(workbook[title])
            
            # Add any other sheets that are not in the desired visible list (e.g., DATA_IMPORT or others)
            # This ensures all sheets are kept, with DATA_IMPORT being effectively at the end or wherever it lands
            # after the specified visible ones.
            for title in current_sheet_titles:
                if title not in desired_visible_order:
                    final_ordered_sheets.append(workbook[title])
            
            workbook._sheets = final_ordered_sheets


        # End of `with pd.ExcelWriter` block, writer is saved here.
    except Exception as e:
        st.error(f"Une erreur est survenue lors de la génération du fichier Excel : {e}")
        import traceback
        st.error(traceback.format_exc()) # For more detailed debugging
        return None

    output.seek(0)
    return output.getvalue()


def generate_user_crm_excel(df_entreprises: pd.DataFrame, df_contacts: pd.DataFrame, df_actions: pd.DataFrame) -> bytes:
    """
    Génère un fichier Excel (.xlsx) à partir des DataFrames CRM de l'utilisateur.
    """
    output = BytesIO()
    try:
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            workbook = writer.book

            # 1. DATA_IMPORT Sheet (from df_entreprises, but only relevant columns)
            # These are typically columns that might come from an initial API search or import,
            # excluding user-added notes or statuses if they are not part of the "raw" data concept.
            # For this version, we'll include most columns from df_entreprises but ensure
            # it matches the structure expected if it were raw data.
            data_import_cols = [
                'SIRET', 'Nom complet', 'Enseignes', 'Activité NAF/APE Etablissement', 
                # 'code_naf_etablissement', # Assuming this is not directly in df_entreprises, but derived if needed
                # 'Activité NAF/APE Entreprise', # Assuming this is not directly in df_entreprises
                # 'code_naf_entreprise', # Assuming this is not directly in df_entreprises
                'Adresse établissement', 'Nb salariés établissement', 'Est siège social', 
                'Date de création Entreprise', "Chiffre d'Affaires Entreprise", 
                'Résultat Net Entreprise', 'Année Finances Entreprise', 'SIREN'
            ]
            df_data_import = pd.DataFrame()
            for col in data_import_cols:
                if col in df_entreprises.columns:
                    df_data_import[col] = df_entreprises[col]
                else:
                    df_data_import[col] = pd.NA # Use pd.NA for missing columns

            df_data_import = df_data_import[data_import_cols] # Ensure correct order
            df_data_import.to_excel(writer, sheet_name='DATA_IMPORT', index=False, freeze_panes=(1, 0))
            num_data_rows_entreprises = len(df_entreprises) # Used for formula ranges later

            # 2. ENTREPRISES Sheet (direct from user's df_entreprises)
            # Include user-specific columns like 'Notes Personnelles', 'Statut Piste'
            df_entreprises_sheet = df_entreprises.copy()
            
            # Generate hyperlink columns if base columns exist
            if 'Nom complet' in df_entreprises_sheet.columns:
                 df_entreprises_sheet['Recherche LinkedIn'] = df_entreprises_sheet['Nom complet'].apply(
                    lambda x: f"https://www.google.com/search?q={x}+site%3Alinkedin.com" if pd.notna(x) and x.strip() != "" else None)
            else:
                df_entreprises_sheet['Recherche LinkedIn'] = None

            if 'Nom complet' in df_entreprises_sheet.columns and 'Adresse établissement' in df_entreprises_sheet.columns:
                 df_entreprises_sheet['Recherche Google Maps'] = df_entreprises_sheet.apply(
                    lambda row: f"https://www.google.com/maps/search/?api=1&query={row['Nom complet']},{row['Adresse établissement']}" if pd.notna(row['Nom complet']) and row['Nom complet'].strip() != "" and pd.notna(row['Adresse établissement']) and row['Adresse établissement'].strip() != "" else None, axis=1)
            else:
                df_entreprises_sheet['Recherche Google Maps'] = None

            # Define desired column order for the sheet
            entreprises_sheet_cols_ordered = [
                'SIRET', 'Nom complet', 'Enseignes', 'Activité NAF/APE établissement', 
                'Adresse établissement', 'Recherche LinkedIn', 'Recherche Google Maps', 
                'Nb salariés établissement', 'Est siège social', 'Date de création Entreprise', 
                "Chiffre d'Affaires Entreprise", 'Résultat Net Entreprise', 
                'Année Finances Entreprise', 'SIREN', 'Notes Personnelles', 'Statut Piste'
            ]
            # Add any columns that might be in df_entreprises_sheet but not in the defined order (e.g., old columns)
            for col in df_entreprises_sheet.columns:
                if col not in entreprises_sheet_cols_ordered:
                    entreprises_sheet_cols_ordered.append(col)
            
            df_entreprises_sheet = df_entreprises_sheet.reindex(columns=entreprises_sheet_cols_ordered)
            df_entreprises_sheet.to_excel(writer, sheet_name='ENTREPRISES', index=False, freeze_panes=(1, 0))


            # 3. VALEURS_LISTE Sheet (from config)
            vl_headers = ['CONTACTS_Direction', 'ACTIONS_TypeAction', 'ACTIONS_StatutAction', 'ACTIONS_StatutOpportunuiteTaf']
            vl_data_from_config = {
                'CONTACTS_Direction': config.VALEURS_LISTE_CONTACTS_DIRECTION,
                'ACTIONS_TypeAction': config.VALEURS_LISTE_ACTIONS_TYPEACTION,
                'ACTIONS_StatutAction': config.VALEURS_LISTE_ACTIONS_STATUTACTION,
                'ACTIONS_StatutOpportunuiteTaf': config.VALEURS_LISTE_ACTIONS_STATUTOPPORTUNITE
            }
            max_len_vl = max(len(lst) for lst in vl_data_from_config.values())
            padded_vl_data = {col: lst + [pd.NA]*(max_len_vl - len(lst)) for col, lst in vl_data_from_config.items()}
            df_valeurs_liste = pd.DataFrame(padded_vl_data)
            df_valeurs_liste = df_valeurs_liste[vl_headers]
            df_valeurs_liste.to_excel(writer, sheet_name='VALEURS_LISTE', index=False, freeze_panes=(1, 0))

            # 4. CONTACTS Sheet (direct from user's df_contacts)
            df_contacts_sheet = df_contacts.copy()
            # Ensure all expected columns are present
            expected_contact_cols = ['Prénom Nom', 'Entreprise', 'Poste', 'Direction', 'Email', 'Téléphone', 'Profil LinkedIn URL', 'Notes']
            for col in expected_contact_cols:
                if col not in df_contacts_sheet.columns:
                    df_contacts_sheet[col] = pd.NA
            df_contacts_sheet = df_contacts_sheet[expected_contact_cols]
            df_contacts_sheet.to_excel(writer, sheet_name='CONTACTS', index=False, freeze_panes=(1, 0))

            # 5. ACTIONS Sheet (direct from user's df_actions)
            df_actions_sheet = df_actions.copy()
            # Ensure 'Date Action' is string or Excel might format it poorly if NaT exists
            if 'Date Action' in df_actions_sheet.columns:
                df_actions_sheet['Date Action'] = df_actions_sheet['Date Action'].astype(object).where(df_actions_sheet['Date Action'].notnull(), None)
            
            expected_action_cols = ['Entreprise', 'Contact (Prénom Nom)', 'Type Action', 'Date Action', 'Description/Notes', 'Statut Action', 'Statut Opportunuité Taf']
            for col in expected_action_cols:
                if col not in df_actions_sheet.columns:
                    df_actions_sheet[col] = pd.NA
            df_actions_sheet = df_actions_sheet[expected_action_cols]
            df_actions_sheet.to_excel(writer, sheet_name='ACTIONS', index=False, freeze_panes=(1, 0))
            
            # 6. Data Validation (similar to generate_crm_excel)
            max_row_validation = 5000 # Consistent with other function
            
            # CONTACTS Sheet Validations
            ws_contacts = workbook['CONTACTS']
            # Entreprise validation (from ENTREPRISES sheet, 'Nom complet' column - B)
            dv_contacts_entreprise = DataValidation(type="list", formula1=f"=ENTREPRISES!$B$2:$B${max_row_validation}", allow_blank=True)
            ws_contacts.add_data_validation(dv_contacts_entreprise)
            dv_contacts_entreprise.add(f"B2:B{max_row_validation}")
            # Direction validation (from VALEURS_LISTE sheet, column A)
            dv_contacts_direction = DataValidation(type="list", formula1=f"=VALEURS_LISTE!$A$2:$A${max_row_validation}", allow_blank=True)
            ws_contacts.add_data_validation(dv_contacts_direction)
            dv_contacts_direction.add(f"D2:D{max_row_validation}")

            # ACTIONS Sheet Validations
            ws_actions = workbook['ACTIONS']
            # Entreprise validation
            dv_actions_entreprise = DataValidation(type="list", formula1=f"=ENTREPRISES!$B$2:$B${max_row_validation}", allow_blank=True)
            ws_actions.add_data_validation(dv_actions_entreprise)
            dv_actions_entreprise.add(f"A2:A{max_row_validation}")
            # Contact validation (from CONTACTS sheet, 'Prénom Nom' column - A)
            dv_actions_contact = DataValidation(type="list", formula1=f"=CONTACTS!$A$2:$A${max_row_validation}", allow_blank=True)
            ws_actions.add_data_validation(dv_actions_contact)
            dv_actions_contact.add(f"B2:B{max_row_validation}")
            # Type Action (from VALEURS_LISTE sheet, column B)
            dv_actions_type = DataValidation(type="list", formula1=f"=VALEURS_LISTE!$B$2:$B${max_row_validation}", allow_blank=True)
            ws_actions.add_data_validation(dv_actions_type)
            dv_actions_type.add(f"C2:C{max_row_validation}")
            # Statut Action (from VALEURS_LISTE sheet, column C)
            dv_actions_statut = DataValidation(type="list", formula1=f"=VALEURS_LISTE!$C$2:$C${max_row_validation}", allow_blank=True)
            ws_actions.add_data_validation(dv_actions_statut)
            dv_actions_statut.add(f"F2:F{max_row_validation}")
            # Statut Opportunuité Taf (from VALEURS_LISTE sheet, column D)
            dv_actions_opportunite = DataValidation(type="list", formula1=f"=VALEURS_LISTE!$D$2:$D${max_row_validation}", allow_blank=True)
            ws_actions.add_data_validation(dv_actions_opportunite)
            dv_actions_opportunite.add(f"G2:G{max_row_validation}")

            # 7. Formatting: Auto-adjust column widths
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                for col_idx, column_cells in enumerate(sheet.columns):
                    max_length = 0
                    column_letter = get_column_letter(col_idx + 1)
                    
                    # Header length
                    if sheet.cell(row=1, column=col_idx + 1).value:
                         max_length = len(str(sheet.cell(row=1, column=col_idx + 1).value))
                    
                    # Cell content length (check first N rows for performance)
                    for i, cell in enumerate(column_cells):
                        if i > 100: break # Limit rows checked for performance
                        try:
                            if cell.value:
                                cell_len = len(str(cell.value))
                                if cell_len > max_length:
                                    max_length = cell_len
                        except:
                            pass
                    adjusted_width = (max_length + 2) * 1.2
                    adjusted_width = min(adjusted_width, 60) # Cap max width
                    sheet.column_dimensions[column_letter].width = adjusted_width
            
            # 8. Styling Headers
            header_font = Font(bold=True, color="FFFFFFFF")
            header_fill = PatternFill(start_color="FF4472C4", end_color="FF4472C4", fill_type="solid")
            header_alignment = Alignment(horizontal="center", vertical="center")
            sheets_to_style_headers = ['ENTREPRISES', 'CONTACTS', 'ACTIONS', 'VALEURS_LISTE', 'DATA_IMPORT']
            for sheet_name in sheets_to_style_headers:
                if sheet_name in workbook.sheetnames:
                    sheet = workbook[sheet_name]
                    for cell in sheet[1]:
                        cell.font = header_font
                        cell.fill = header_fill
                        cell.alignment = header_alignment
            
            # 9. Hide DATA_IMPORT sheet
            if 'DATA_IMPORT' in workbook.sheetnames:
                workbook['DATA_IMPORT'].sheet_state = 'hidden'

            # 10. Set Sheet Order
            desired_visible_order = ['ENTREPRISES', 'CONTACTS', 'ACTIONS', 'VALEURS_LISTE']
            current_sheet_titles = [sheet.title for sheet in workbook._sheets]
            final_ordered_sheets = []
            for title in desired_visible_order:
                if title in current_sheet_titles:
                    final_ordered_sheets.append(workbook[title])
            for title in current_sheet_titles:
                if title not in desired_visible_order: # Add remaining sheets (like DATA_IMPORT)
                    final_ordered_sheets.append(workbook[title])
            workbook._sheets = final_ordered_sheets

    except Exception as e:
        # Consider logging the error or using st.error if this can be called from Streamlit context directly
        print(f"Error generating user CRM Excel: {e}") # Basic print for now
        import traceback
        print(traceback.format_exc())
        return None

    output.seek(0)
    return output.getvalue()

def add_entreprise_records(current_df_entreprises: pd.DataFrame, new_records_df: pd.DataFrame, expected_cols: list) -> pd.DataFrame:
    """
    Adds new entreprise records to the current DataFrame of entreprises,
    handles deduplication, and ensures schema.
    """
    if new_records_df.empty:
        # If there are no new records, ensure the current DataFrame conforms to expected_cols
        # This handles the case where current_df_entreprises might be empty but needs schema
        if current_df_entreprises.empty:
            processed_df = pd.DataFrame(columns=expected_cols)
        else:
            processed_df = current_df_entreprises.copy()
        # Ensure all expected columns exist
        for col in expected_cols:
            if col not in processed_df.columns:
                processed_df[col] = pd.NA # Or appropriate default
        return processed_df.reindex(columns=expected_cols)

    # Ensure new_records_df has the expected schema before concatenation,
    # though this should ideally be handled before calling this function.
    # For robustness, we can re-apply it here on a copy of new_records_df.
    df_to_add_prepared = new_records_df.copy()
    for col in expected_cols:
        if col not in df_to_add_prepared.columns:
            df_to_add_prepared[col] = pd.NA
    df_to_add_prepared = df_to_add_prepared.reindex(columns=expected_cols)

    # Concatenate
    combined_df = pd.concat([current_df_entreprises, df_to_add_prepared], ignore_index=True)
    
    # Drop duplicates
    if 'SIRET' in combined_df.columns:
        combined_df.drop_duplicates(subset=['SIRET'], keep='last', inplace=True)
    
    # Final schema enforcement (ensure all expected columns and order)
    # This also handles adding any expected_cols that might have been dropped if combined_df became empty
    # or if SIRET was missing and drop_duplicates wasn't effective.
    final_df = pd.DataFrame(columns=expected_cols) # Start with a clean slate for columns
    if not combined_df.empty:
        for col in expected_cols:
            if col in combined_df.columns:
                final_df[col] = combined_df[col]
            else:
                final_df[col] = pd.NA
    else: # If combined_df is empty (e.g. current_df was empty, new_records was empty)
        for col in expected_cols:
            final_df[col] = pd.NA # Ensure schema on empty df

    return final_df.reindex(columns=expected_cols)

# Add this function to data_utils.py
# Ensure pandas as pd and numpy as np (for pd.NA) are imported if not already.
# numpy might not be needed if pd.NA is used directly and pandas version is appropriate.

def ensure_df_schema(df: pd.DataFrame, expected_cols: list) -> pd.DataFrame:
    """
    Ensures the DataFrame has all expected columns with pd.NA for missing ones,
    and reorders columns to match expected_cols.
    """
    df_processed = df.copy()
    for col in expected_cols:
        if col not in df_processed.columns:
            df_processed[col] = pd.NA # Use pd.NA for missing values
    
    # Ensure correct column order and drop any columns not in expected_cols
    return df_processed.reindex(columns=expected_cols)

def get_crm_data_for_saving() -> dict:
    """
    Retrieves CRM DataFrames from session state, performs necessary cleaning,
    and returns a dictionary formatted for JSON saving.
    """
    # Ensure DataFrames exist in session_state and have a default schema if empty
    # This part relies on the main app ensuring df_entreprises, df_contacts, df_actions exist
    # and preferably have their schemas (expected_cols) applied.
    # For safety, we can try to retrieve them or default to empty DataFrames.
    
    df_e = st.session_state.get('df_entreprises', pd.DataFrame())
    df_c = st.session_state.get('df_contacts', pd.DataFrame())
    df_a = st.session_state.get('df_actions', pd.DataFrame())

    # Perform data cleaning, especially for JSON serialization compatibility
    # Example: Convert NaT in 'Date Action' to None for df_actions
    df_a_cleaned = df_a.copy()
    if 'Date Action' in df_a_cleaned.columns:
        # Ensure it's datetime first, then convert NaT to None
        df_a_cleaned['Date Action'] = pd.to_datetime(df_a_cleaned['Date Action'], errors='coerce')
        df_a_cleaned['Date Action'] = df_a_cleaned['Date Action'].astype(object).where(df_a_cleaned['Date Action'].notnull(), None)
    
    crm_data = {
        "entreprises": df_e.to_dict(orient='records'),
        "contacts": df_c.to_dict(orient='records'),
        "actions": df_a_cleaned.to_dict(orient='records')
    }
    return crm_data

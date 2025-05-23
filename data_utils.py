# /home/guillaumecayeux/code_dev/recherche_job_candidature_spontanée/data_utils.py
import streamlit as st
import pandas as pd
from functools import lru_cache
import datetime
from io import BytesIO
import openpyxl # Importer openpyxl pour charger le template
from openpyxl.worksheet.datavalidation import DataValidation


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
        df_entreprises (pd.DataFrame): Le DataFrame des résultats de recherche.

    Returns:
        bytes: Le contenu binaire du fichier Excel, ou None en cas d'erreur.
    """
    template_path = "suivi_canditatures_spontanees.xlsx"
    try:
        workbook = openpyxl.load_workbook(template_path)
    except FileNotFoundError:
        st.error(f"Erreur: Le fichier template '{template_path}' est introuvable.")
        return None
    except Exception as e:
        st.error(f"Erreur lors du chargement du template Excel: {e}")
        return None

    try:
        # Accéder à la feuille "Data_Import"
        sheet_name = "Data_Import"
        if sheet_name in workbook.sheetnames:
            ws = workbook[sheet_name]
        else:
            st.error(f"Erreur: La feuille '{sheet_name}' est introuvable dans le template.")
            # Optionnel: créer la feuille si elle n'existe pas
            # ws = workbook.create_sheet(sheet_name)
            # st.warning(f"La feuille '{sheet_name}' n'existait pas et a été créée.")
            return None # Ou gérer autrement

        # Effacer les données existantes à partir de la deuxième ligne
        # ws.max_row donne le nombre total de lignes ayant du contenu.
        # ws.min_row est généralement 1.
        # Il faut faire attention si la feuille est complètement vide ou n'a que des en-têtes.
        if ws.max_row > 1: # S'il y a des données au-delà de la première ligne
            # La suppression de lignes peut être lente et complexe avec openpyxl.
            # Il est souvent plus simple de supprimer les lignes en itérant à l'envers
            # ou de recréer la feuille ou d'écrire des cellules vides.
            # Pour l'instant, on va juste écraser les cellules nécessaires.
            # On va effacer en écrasant avec None jusqu'à la dernière ligne utilisée,
            # puis on ajoutera les nouvelles données.
            for row_idx in range(2, ws.max_row + 1):
                for col_idx in range(1, ws.max_column + 1):
                    ws.cell(row=row_idx, column=col_idx).value = None
        
        # Définir les en-têtes attendus/à écrire
        headers = [
            'SIRET', 'Nom complet', 'Enseignes', 'Activité NAF/APE Etablissement',
            'code_naf_etablissement', 'Activité NAF/APE Entreprise', 'code_naf_entreprise',
            'Adresse établissement', 'Nb salariés établissement', 'Est siège social',
            'Date de création Entreprise', 'Chiffre d\'Affaires Entreprise',
            'Résultat Net Entreprise', 'Année Finances Entreprise', 'SIREN'
        ]

        # Vérifier si les en-têtes sont présents, sinon les écrire
        # Ou simplement les réécrire pour s'assurer qu'ils sont corrects
        for col_num, header_text in enumerate(headers, 1):
            ws.cell(row=1, column=col_num, value=header_text)

        # Préparer le DataFrame pour l'écriture
        # S'assurer que seules les colonnes nécessaires sont présentes et dans le bon ordre
        df_to_write = df_entreprises.copy()

        # Mapper les noms de colonnes du DataFrame aux noms d'en-tête Excel si nécessaire
        # Ici, on suppose que les noms de colonnes de df_entreprises correspondent
        # aux `headers` après le renommage effectué dans `traitement_reponse_api`.
        # Si ce n'est pas le cas, un mappage explicite serait nécessaire ici.
        # Par exemple: df_to_write = df_entreprises.rename(columns={'AncienNom': 'NouveauNom'})

        # Filtrer df_to_write pour ne garder que les colonnes définies dans headers
        # et dans le bon ordre.
        # Les colonnes non présentes dans df_entreprises seront ignorées silencieusement par reindex,
        # ou on peut ajouter une gestion d'erreur si certaines sont critiques.
        df_to_write = df_to_write.reindex(columns=headers)

        # Écrire les données du DataFrame dans la feuille
        # openpyxl.utils.dataframe.dataframe_to_rows est pratique mais sans formatage.
        # On va itérer pour plus de contrôle si besoin plus tard.
        current_row = 2 # Commencer à écrire à la deuxième ligne
        for _, row_data in df_to_write.iterrows():
            for col_num, header_name in enumerate(headers, 1):
                cell_value = row_data.get(header_name)
                # Gérer les types de données si nécessaire (ex: dates, nombres)
                # Pour l'instant, on écrit directement.
                ws.cell(row=current_row, column=col_num, value=cell_value)
            current_row += 1

        # --- Ajout de la Validation des Données ---
        max_row_validation = 5000 # Max row for applying data validation dropdowns

        # Define formulas for data validation lists
        company_list_formula = f"=Entreprises!$B$2:$B${max_row_validation}"
        contact_list_formula = f"=Contacts!$A$2:$A${max_row_validation}"
        vl_contacts_direction_formula = f"=Valeurs_Liste!$A$2:$A${max_row_validation}"
        vl_actions_type_formula = f"=Valeurs_Liste!$B$2:$B${max_row_validation}"
        vl_actions_statut_formula = f"=Valeurs_Liste!$C$2:$C${max_row_validation}"
        vl_actions_opportunite_formula = f"=Valeurs_Liste!$D$2:$D${max_row_validation}"

        # Apply validations to 'Contacts' sheet
        if "Contacts" in workbook.sheetnames:
            ws_contacts = workbook["Contacts"]

            # Rule 1: Contacts Sheet, Column B (Company Name)
            dv_company_contacts = DataValidation(type="list", formula1=company_list_formula, allow_blank=True)
            dv_company_contacts.error = "Veuillez choisir une entreprise de la liste (Feuille Entreprises)."
            dv_company_contacts.errorTitle = "Entreprise Invalide"
            dv_company_contacts.prompt = "Sélectionnez une entreprise"
            dv_company_contacts.promptTitle = "Entreprise"
            ws_contacts.add_data_validation(dv_company_contacts)
            dv_company_contacts.add(f"B2:B{max_row_validation}")

            # Rule 2: Contacts Sheet, Column D (Direction)
            dv_direction_contacts = DataValidation(type="list", formula1=vl_contacts_direction_formula, allow_blank=True)
            dv_direction_contacts.error = "Veuillez choisir une direction depuis Valeurs_Liste."
            dv_direction_contacts.errorTitle = "Direction Invalide"
            dv_direction_contacts.prompt = "Sélectionnez une direction"
            dv_direction_contacts.promptTitle = "Direction"
            ws_contacts.add_data_validation(dv_direction_contacts)
            dv_direction_contacts.add(f"D2:D{max_row_validation}")
        else:
            st.warning("Feuille 'Contacts' non trouvée. Certaines validations de données n'ont pas été appliquées.")

        # Apply validations to 'Actions' sheet
        if "Actions" in workbook.sheetnames:
            ws_actions = workbook["Actions"]

            # Rule 1: Actions Sheet, Column A (Company Name)
            dv_company_actions = DataValidation(type="list", formula1=company_list_formula, allow_blank=True)
            dv_company_actions.error = "Veuillez choisir une entreprise de la liste (Feuille Entreprises)."
            dv_company_actions.errorTitle = "Entreprise Invalide"
            dv_company_actions.prompt = "Sélectionnez une entreprise"
            dv_company_actions.promptTitle = "Entreprise"
            ws_actions.add_data_validation(dv_company_actions)
            dv_company_actions.add(f"A2:A{max_row_validation}")

            # Rule 2: Actions Sheet, Column B (Contact Name)
            dv_contact_actions = DataValidation(type="list", formula1=contact_list_formula, allow_blank=True)
            dv_contact_actions.error = "Veuillez choisir un contact de la liste (Feuille Contacts)."
            dv_contact_actions.errorTitle = "Contact Invalide"
            dv_contact_actions.prompt = "Sélectionnez un contact"
            dv_contact_actions.promptTitle = "Contact"
            ws_actions.add_data_validation(dv_contact_actions)
            dv_contact_actions.add(f"B2:B{max_row_validation}")

            # Rule 3: Actions Sheet, Column C (Type Action)
            dv_type_actions = DataValidation(type="list", formula1=vl_actions_type_formula, allow_blank=True)
            dv_type_actions.error = "Veuillez choisir un type d'action depuis Valeurs_Liste."
            dv_type_actions.errorTitle = "Type d'Action Invalide"
            dv_type_actions.prompt = "Sélectionnez un type d'action"
            dv_type_actions.promptTitle = "Type d'Action"
            ws_actions.add_data_validation(dv_type_actions)
            dv_type_actions.add(f"C2:C{max_row_validation}")

            # Rule 4: Actions Sheet, Column F (Statut Action)
            dv_statut_actions = DataValidation(type="list", formula1=vl_actions_statut_formula, allow_blank=True)
            dv_statut_actions.error = "Veuillez choisir un statut d'action depuis Valeurs_Liste."
            dv_statut_actions.errorTitle = "Statut d'Action Invalide"
            dv_statut_actions.prompt = "Sélectionnez un statut"
            dv_statut_actions.promptTitle = "Statut d'Action"
            ws_actions.add_data_validation(dv_statut_actions)
            dv_statut_actions.add(f"F2:F{max_row_validation}")

            # Rule 5: Actions Sheet, Column G (Statut Opportunité Taf)
            dv_opportunite_actions = DataValidation(type="list", formula1=vl_actions_opportunite_formula, allow_blank=True)
            dv_opportunite_actions.error = "Veuillez choisir un statut d'opportunité depuis Valeurs_Liste."
            dv_opportunite_actions.errorTitle = "Statut Opportunité Invalide"
            dv_opportunite_actions.prompt = "Sélectionnez un statut d'opportunité"
            dv_opportunite_actions.promptTitle = "Statut Opportunité"
            ws_actions.add_data_validation(dv_opportunite_actions)
            dv_opportunite_actions.add(f"G2:G{max_row_validation}")
        else:
            st.warning("Feuille 'Actions' non trouvée. Certaines validations de données n'ont pas été appliquées.")
            
        # Sauvegarder le classeur modifié dans un flux BytesIO
        output = BytesIO()
        workbook.save(output)
        output.seek(0) # Rembobiner le flux pour la lecture
        return output.getvalue()

    except Exception as e:
        st.error(f"Erreur lors de la manipulation de la feuille Excel: {e}")
        # Afficher plus de détails pour le débogage si nécessaire
        # import traceback
        # st.error(traceback.format_exc())
        return None

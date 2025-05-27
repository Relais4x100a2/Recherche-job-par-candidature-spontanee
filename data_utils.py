import datetime as dt
from functools import lru_cache
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

import config


# --- Chargement et mise en cache du dictionnaire NAF ---
@st.cache_data  # Utiliser le cache Streamlit pour le chargement initial
def load_naf_dictionary(file_path=config.NAF_FILE_PATH):
    """Charge le fichier NAF et retourne un dictionnaire Code -> Libellé."""
    print(
        f"{dt.datetime.now()} - INFO - Loading NAF dictionary from file_path: {file_path}"
    )
    attempts = [
        {"sep": ",", "encoding": "utf-8"},
        {"sep": ";", "encoding": "utf-8"},
        {"sep": ",", "encoding": "latin-1"},
        {"sep": ";", "encoding": "latin-1"},
    ]
    df_naf = None
    for attempt in attempts:
        print(
            f"{dt.datetime.now()} - INFO - Attempting to read NAF CSV with sep='{attempt['sep']}' and encoding='{attempt['encoding']}'"
        )
        try:
            df_naf_current = pd.read_csv(
                file_path,
                sep=attempt["sep"],
                dtype={"Code": str},
                encoding=attempt["encoding"],
            )
            if "Code" in df_naf_current.columns and "Libellé" in df_naf_current.columns:
                print(
                    f"{dt.datetime.now()} - INFO - NAF CSV read successfully with sep='{attempt['sep']}', encoding='{attempt['encoding']}'."
                )
                df_naf = df_naf_current
                break
            else:
                print(
                    f"{dt.datetime.now()} - WARNING - NAF CSV read with sep='{attempt['sep']}', encoding='{attempt['encoding']}', but 'Code' or 'Libellé' column missing."
                )
        except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as e:
            print(
                f"{dt.datetime.now()} - WARNING - Failed to read NAF CSV with sep='{attempt['sep']}', encoding='{attempt['encoding']}': {e}"
            )
        except FileNotFoundError:
            print(
                f"{dt.datetime.now()} - ERROR - NAF file not found at path: {file_path}"
            )
            return None
        except pd.errors.EmptyDataError:
            print(
                f"{dt.datetime.now()} - ERROR - NAF file is empty at path: {file_path}"
            )
            return None

    if df_naf is None:
        print(
            f"{dt.datetime.now()} - ERROR - Could not find 'Code' and 'Libellé' columns in {file_path} with any attempted separator/encoding."
        )
        return None

    if df_naf.empty:
        print(
            f"{dt.datetime.now()} - WARNING - NAF file '{file_path}' is empty or could not be read correctly."
        )
        return None

    try:
        df_naf.columns = df_naf.columns.str.strip()
        df_naf["Code"] = df_naf["Code"].astype(str).str.strip()
        if df_naf["Code"].duplicated().any():
            df_naf = df_naf.drop_duplicates(subset="Code", keep="last")
        naf_dict = df_naf.set_index("Code")["Libellé"].to_dict()
        print(
            f"{dt.datetime.now()} - INFO - NAF dictionary loaded successfully with {len(naf_dict)} codes."
        )
        return naf_dict
    except Exception as e:
        print(
            f"{dt.datetime.now()} - ERROR - Critical error during NAF file processing from '{file_path}': {e}"
        )
        return None


# Initialize as None. Will be populated by get_naf_lookup().
naf_detailed_lookup = None

def get_naf_lookup():
    """
    Ensures the NAF dictionary is loaded and cached, then populates 
    the global naf_detailed_lookup.
    This function should be called once from the main app after st.set_page_config().
    """
    global naf_detailed_lookup
    # load_naf_dictionary is cached by @st.cache_data.
    # This call will either load fresh data or return cached data.
    # We assign it to our global variable for other functions in this module to use.
    if naf_detailed_lookup is None: # Populate only if not already done
        naf_detailed_lookup = load_naf_dictionary()
    return naf_detailed_lookup


@lru_cache(maxsize=None)
def get_section_for_code(code):
    if not code or not isinstance(code, str):
        return None
    code_cleaned = code.strip().replace(".", "")[:2]
    section = config.NAF_SECTION_MAP.get(code_cleaned)
    return section


@lru_cache(maxsize=None)
def get_codes_for_section(section_letter):
    if naf_detailed_lookup is None:
        print(f"{dt.datetime.now()} - WARNING - get_codes_for_section: NAF dictionary not initialized or failed to load.")
        return []
    if not section_letter:
        return []
    codes = [
        code
        for code in naf_detailed_lookup
        if get_section_for_code(code) == section_letter
    ]
    return sorted(codes)


def correspondance_NAF(code_naf_input):
    print(
        f"{dt.datetime.now()} - DEBUG - correspondance_NAF called with code_naf_input: '{code_naf_input}'."
    )
    if naf_detailed_lookup is None:
        print(
            f"{dt.datetime.now()} - WARNING - correspondance_NAF: NAF dictionary not initialized or failed to load. Input: '{code_naf_input}'."
        )
        return f"{code_naf_input} (Dico NAF non chargé)"
    if not code_naf_input or not isinstance(code_naf_input, str):
        print(
            f"{dt.datetime.now()} - WARNING - correspondance_NAF: Invalid code_naf_input '{code_naf_input}'."
        )
        return "Code NAF invalide"
    code_naf_clean = code_naf_input.strip()
    libelle = naf_detailed_lookup.get(code_naf_clean)
    if libelle is None:
        print(
            f"{dt.datetime.now()} - WARNING - correspondance_NAF: Code '{code_naf_clean}' not found in NAF dictionary."
        )
        return f"{code_naf_clean} (Libellé non trouvé)"
    return libelle


def traitement_reponse_api(entreprises, selected_effectifs_codes):
    print(
        f"{dt.datetime.now()} - INFO - traitement_reponse_api called. Number of entreprises in input: {len(entreprises) if entreprises else 0}. Selected effectifs codes: {selected_effectifs_codes}"
    )
    if not entreprises:
        return pd.DataFrame()
    all_etablissements_data = []
    processed_sirens = set()
    num_etablissements_processed = 0
    num_etablissements_matched = 0
    for entreprise in entreprises:
        siren = entreprise.get("siren")
        # nom_complet_api = entreprise.get("nom_complet") # Company's legal name
        # nom_sociale_api = entreprise.get("nom_raison_sociale") # Often similar or more formal
        date_creation = entreprise.get("date_creation")
        nombre_etablissements_ouverts = entreprise.get("nombre_etablissements_ouverts")
        code_naf_entreprise = entreprise.get("activite_principale")
        tranche_effectif_salarie_entreprise = entreprise.get("tranche_effectif_salarie")
        tranche_description_entreprise = config.effectifs_tranches.get(
            tranche_effectif_salarie_entreprise, "N/A"
        )
        latest_year_str, ca_latest, resultat_net_latest = None, None, None
        if siren and siren not in processed_sirens:
            processed_sirens.add(siren)
            finances = entreprise.get("finances", {})
            if finances and isinstance(finances, dict):
                try:
                    available_years = [
                        year for year in finances.keys() if year.isdigit()
                    ]
                    if available_years:
                        latest_year_str = max(available_years)
                        latest_year_data = finances.get(latest_year_str, {})
                        ca_latest = latest_year_data.get("ca")
                        resultat_net_latest = latest_year_data.get("resultat_net")
                except Exception as e:
                    print(
                        f"{dt.datetime.now()} - WARNING - Error extracting financial data for SIREN {siren}: {e}"
                    )
                    latest_year_str = "Erreur"
        matching_etablissements = entreprise.get("matching_etablissements", [])
        for etab in matching_etablissements:
            num_etablissements_processed += 1
            etat_etab = etab.get("etat_administratif")
            tranche_eff_etab = etab.get("tranche_effectif_salarie")
            selected_effectifs_codes_set = (
                set(selected_effectifs_codes)
                if not isinstance(selected_effectifs_codes, set)
                else selected_effectifs_codes
            )
            if etat_etab == "A" and tranche_eff_etab in selected_effectifs_codes_set:
                num_etablissements_matched += 1

                # --- Début de la logique de combinaison Dénomination - Enseigne + Enseigne ---
                base_name_for_etab = str(entreprise.get("nom_complet", "")).strip()
                if not base_name_for_etab:  # Fallback si nom_complet est vide
                    base_name_for_etab = str(
                        entreprise.get("nom_raison_sociale", "")
                    ).strip()

                liste_enseignes_etab = etab.get("liste_enseignes", [])
                enseignes_str_etab = ""
                if liste_enseignes_etab:
                    # Filtre les enseignes valides et les joint
                    valid_enseignes = [
                        str(e).strip()
                        for e in liste_enseignes_etab
                        if e and str(e).strip()
                    ]
                    if valid_enseignes:
                        enseignes_str_etab = ", ".join(valid_enseignes)

                processed_name = base_name_for_etab

                if enseignes_str_etab and enseignes_str_etab.upper() != "N/A":
                    processed_name_upper = processed_name.upper()
                    enseignes_str_etab_upper = enseignes_str_etab.upper()

                    if (
                        not processed_name
                    ):  # Si le nom de base est vide, l'enseigne devient le nom
                        processed_name = enseignes_str_etab
                    # Ajoute l'enseigne si elle est différente ET n'est pas déjà une sous-chaîne
                    elif (
                        enseignes_str_etab_upper != processed_name_upper
                        and enseignes_str_etab_upper not in processed_name_upper
                    ):
                        processed_name = f"{processed_name} - {enseignes_str_etab}"

                if not processed_name:  # S'assurer qu'il y a une valeur
                    processed_name = "N/A"
                # --- Fin de la logique de combinaison ---

                all_etablissements_data.append(
                    {
                        "SIRET": etab.get("siret"),
                        "SIREN": siren,
                        "tranche_effectif_salarie_etablissement": tranche_eff_etab,
                        "annee_tranche_effectif_salarie": etab.get(
                            "annee_tranche_effectif_salarie"
                        ),
                        "code_naf_etablissement": etab.get("activite_principale"),
                        "adresse": etab.get("adresse"),
                        "latitude": etab.get("latitude"),
                        "longitude": etab.get("longitude"),
                        "est_siege": etab.get("est_siege", False),
                        "nom_complet_entreprise": processed_name,  # Utilise le nom traité
                        "nom_sociale_entreprise": entreprise.get(
                            "nom_raison_sociale"
                        ),  # Garde la raison sociale brute
                        "date_creation_entreprise": date_creation,
                        "nb_etab_ouverts_entreprise": nombre_etablissements_ouverts,
                        "code_naf_entreprise": code_naf_entreprise,
                        "tranche_desc_entreprise": tranche_description_entreprise,
                        "annee_finances": latest_year_str,
                        "ca_entreprise": ca_latest,
                        "resultat_net_entreprise": resultat_net_latest,
                    }
                )
    print(
        f"{dt.datetime.now()} - INFO - traitement_reponse_api: Processed SIRENs: {len(processed_sirens)}. Total establishments processed: {num_etablissements_processed}. Matched establishments: {num_etablissements_matched}."
    )
    if not all_etablissements_data:
        print(
            f"{dt.datetime.now()} - INFO - traitement_reponse_api: No establishments matched criteria. Returning empty DataFrame."
        )
        return pd.DataFrame()
    df_filtered = pd.DataFrame(all_etablissements_data)
    df_filtered["Activité NAF/APE Entreprise"] = df_filtered[
        "code_naf_entreprise"
    ].apply(lambda x: correspondance_NAF(x) if pd.notna(x) and x != "nan" else "N/A")
    df_filtered["Activité NAF/APE Etablissement"] = df_filtered[
        "code_naf_etablissement"
    ].apply(lambda x: correspondance_NAF(x) if pd.notna(x) and x != "nan" else "N/A")
    df_filtered["Nb salariés établissement"] = (
        df_filtered["tranche_effectif_salarie_etablissement"]
        .map(config.effectifs_tranches)
        .fillna("N/A")
    )
    df_filtered["Section NAF"] = (
        df_filtered["code_naf_etablissement"].apply(get_section_for_code).fillna("N/A")
    )
    df_filtered["Color"] = df_filtered["Section NAF"].apply(
        lambda section: config.naf_color_mapping.get(
            section, config.naf_color_mapping["N/A"]
        )
    )
    df_filtered["Radius"] = (
        df_filtered["tranche_effectif_salarie_etablissement"]
        .map(config.size_mapping)
        .fillna(config.size_mapping.get("N/A", 10))
    )
    df_filtered["Latitude"] = pd.to_numeric(df_filtered["latitude"], errors="coerce")
    df_filtered["Longitude"] = pd.to_numeric(df_filtered["longitude"], errors="coerce")
    df_filtered["Chiffre d'Affaires Entreprise"] = pd.to_numeric(
        df_filtered["ca_entreprise"], errors="coerce"
    )
    df_filtered["Résultat Net Entreprise"] = pd.to_numeric(
        df_filtered["resultat_net_entreprise"], errors="coerce"
    )
    final_df = df_filtered.rename(
        columns={
            "nom_complet_entreprise": "Dénomination - Enseigne",
            "est_siege": "Est siège social",
            "adresse": "Adresse établissement",
            "tranche_effectif_salarie_etablissement": "Code effectif établissement",
            "annee_tranche_effectif_salarie": "Année nb salariés établissement",
            "nom_sociale_entreprise": "Raison sociale",
            "date_creation_entreprise": "Date de création Entreprise",
            "nb_etab_ouverts_entreprise": "Nb total établissements ouverts",
            "tranche_desc_entreprise": "Nb salariés entreprise",
            "annee_finances": "Année Finances Entreprise",
        }
    )
    cols_existantes = [
        col for col in config.COLS_EXPORT_ORDER if col in final_df.columns
    ]
    final_df_result = final_df[cols_existantes]
    print(
        f"{dt.datetime.now()} - INFO - traitement_reponse_api: Final DataFrame has {len(final_df_result)} rows."
    )
    return final_df_result


def generate_erm_excel(df_entreprises_input: pd.DataFrame):
    """
    Génère un fichier Excel (.xlsx) à partir de zéro avec plusieurs feuilles (DATA_IMPORT, ENTREPRISES, etc.),
    des formules, des données statiques, et des règles de validation de données.

    Args:
        df_entreprises_input (pd.DataFrame): Le DataFrame des résultats de recherche.

    Returns:
        bytes: Le contenu binaire du fichier Excel, ou None en cas d'erreur.
    """
    print(
        f"{dt.datetime.now()} - INFO - generate_erm_excel called. Input df_entreprises_input shape: {df_entreprises_input.shape}"
    )
    output = BytesIO()
    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            workbook = writer.book
            print(
                f"{dt.datetime.now()} - INFO - ExcelWriter created, workbook obtained."
            )

            # 1. DATA_IMPORT Sheet
            print(f"{dt.datetime.now()} - INFO - Creating DATA_IMPORT sheet.")
            data_import_cols = [
                "SIRET",
                "Dénomination - Enseigne",
                "Activité NAF/APE Etablissement",
                "code_naf_etablissement",
                "Activité NAF/APE Entreprise",
                "code_naf_entreprise",
                "Adresse établissement",
                "Nb salariés établissement",
                "Est siège social",
                "Date de création Entreprise",
                "Chiffre d'Affaires Entreprise",
                "Résultat Net Entreprise",
                "Année Finances Entreprise",
                "SIREN",
            ]
            df_data_import = pd.DataFrame()
            for col in data_import_cols:
                if col in df_entreprises_input.columns:
                    df_data_import[col] = df_entreprises_input[col]
                else:
                    df_data_import[col] = np.nan

            df_data_import = df_data_import[data_import_cols]
            df_data_import.to_excel(
                writer, sheet_name="DATA_IMPORT", index=False, freeze_panes=(1, 0)
            )
            num_data_rows = len(df_data_import)
            print(
                f"{dt.datetime.now()} - INFO - DATA_IMPORT sheet created with {num_data_rows} rows."
            )

            # 2. ENTREPRISES Sheet
            print(
                f"{dt.datetime.now()} - INFO - Creating ENTREPRISES sheet with formulas."
            )
            entreprises_headers = [
                "SIRET",
                "Dénomination - Enseigne",
                "Recherche LinkedIn",
                "Recherche Google Maps",
                "Recherche Indeed",
                "Activité NAF/APE Etablissement",
                "Adresse établissement",
                "Nb salariés établissement",
                "Est siège social",
                "Date de création Entreprise",
                "Chiffre d'Affaires Entreprise",
                "Résultat Net Entreprise",
                "Année Finances Entreprise",
            ]
            df_entreprises_sheet_headers_only = pd.DataFrame(
                columns=entreprises_headers
            )
            df_entreprises_sheet_headers_only.to_excel(
                writer, sheet_name="ENTREPRISES", index=False, freeze_panes=(1, 0)
            )

            ws_entreprises = workbook["ENTREPRISES"]

            # Write formulas row by row
            for r_idx in range(num_data_rows):
                excel_row = r_idx + 2  # Excel rows are 1-indexed, data starts on row 2
                
                # Col 1: SIRET
                ws_entreprises.cell(row=excel_row, column=1, value=f"=DATA_IMPORT!A{excel_row}")
                # Col 2: Dénomination - Enseigne
                ws_entreprises.cell(row=excel_row, column=2, value=f"=DATA_IMPORT!B{excel_row}")
                
                # Col 3: Recherche LinkedIn (B{excel_row} on ENTREPRISES sheet is "Dénomination - Enseigne")
                ws_entreprises.cell(
                    row=excel_row,
                    column=3,
                    value=f'=HYPERLINK("https://www.google.com/search?q="&B{excel_row}&"+site%3Alinkedin.com%2Fcompany%2F","Recherche LinkedIn")'
                )
                # Col 4: Recherche Google Maps (B{excel_row} is Dénomination, G{excel_row} on ENTREPRISES sheet is "Adresse établissement")
                ws_entreprises.cell(
                    row=excel_row,
                    column=4,
                    value=f'=HYPERLINK("https://www.google.com/maps/search/?api=1&query="&B{excel_row}&","&G{excel_row}&"","Recherche Google Maps")'
                )
                # Col 5: Recherche Indeed (B{excel_row} on ENTREPRISES sheet is "Dénomination - Enseigne")
                ws_entreprises.cell(
                    row=excel_row,
                    column=5,
                    value=f'=HYPERLINK("https://www.google.com/search?q="&B{excel_row}&"+site%3Aindeed.com","Recherche Indeed")'
                )
                # Col 6: Activité NAF/APE Etablissement
                ws_entreprises.cell(row=excel_row, column=6, value=f"=DATA_IMPORT!C{excel_row}")
                # Col 7: Adresse établissement (Source: DATA_IMPORT col G)
                ws_entreprises.cell(row=excel_row, column=7, value=f"=DATA_IMPORT!G{excel_row}")
                # Col 8: Nb salariés établissement (Source: DATA_IMPORT col H)
                ws_entreprises.cell(
                    row=excel_row, column=8, value=f"=DATA_IMPORT!H{excel_row}"
                )
                # Col 9: Est siège social (Source: DATA_IMPORT col I)
                ws_entreprises.cell(
                    row=excel_row, column=9, value=f"=DATA_IMPORT!I{excel_row}"
                )
                # Col 10: Date de création Entreprise (Source: DATA_IMPORT col J)
                ws_entreprises.cell(
                    row=excel_row, column=10, value=f"=DATA_IMPORT!J{excel_row}"
                )
                # Col 11: Chiffre d'Affaires Entreprise (Source: DATA_IMPORT col K)
                ws_entreprises.cell(
                    row=excel_row, column=11, value=f"=DATA_IMPORT!K{excel_row}"
                )
                # Col 12: Résultat Net Entreprise (Source: DATA_IMPORT col L)
                ws_entreprises.cell(
                    row=excel_row, column=12, value=f"=DATA_IMPORT!L{excel_row}"
                )
                # Col 13: Année Finances Entreprise (Source: DATA_IMPORT col M)
                ws_entreprises.cell(
                    row=excel_row, column=13, value=f"=DATA_IMPORT!M{excel_row}"
                )
                # SIREN column (formerly col 14) is removed from ENTREPRISES sheet

            # 3. VALEURS_LISTE Sheet
            vl_headers = [
                "CONTACTS_Direction",
                "ACTIONS_TypeAction",
                "ACTIONS_StatutAction",
                "ACTIONS_StatutOpportunuiteTaf",
            ]

            vl_data_from_config = {
                "CONTACTS_Direction": config.VALEURS_LISTE_CONTACTS_DIRECTION,
                "ACTIONS_TypeAction": config.VALEURS_LISTE_ACTIONS_TYPEACTION,
                "ACTIONS_StatutAction": config.VALEURS_LISTE_ACTIONS_STATUTACTION,
                "ACTIONS_StatutOpportunuiteTaf": config.VALEURS_LISTE_ACTIONS_STATUTOPPORTUNITE,
            }

            # Create DataFrame by padding shorter lists with None to make them equal length for DataFrame creation
            max_len = max(len(lst) for lst in vl_data_from_config.values())
            padded_vl_data = {
                col: lst + [None] * (max_len - len(lst))
                for col, lst in vl_data_from_config.items()
            }
            df_valeurs_liste = pd.DataFrame(padded_vl_data)
            df_valeurs_liste = df_valeurs_liste[vl_headers]  # Ensure column order
            df_valeurs_liste.to_excel(
                writer, sheet_name="VALEURS_LISTE", index=False, freeze_panes=(1, 0)
            )

            # 4. CONTACTS Sheet
            contacts_headers = [
                "Prénom Nom",
                "Entreprise",
                "Poste",
                "Direction",
                "Email",
                "Téléphone",
                "Profil LinkedIn URL",
                "Notes",
            ]
            df_contacts = pd.DataFrame(columns=contacts_headers)
            df_contacts.to_excel(
                writer, sheet_name="CONTACTS", index=False, freeze_panes=(1, 0)
            )

            # 5. ACTIONS Sheet
            actions_headers = [
                "Entreprise",
                "Contact (Prénom Nom)",
                "Type Action",
                "Date Action",
                "Description/Notes",
                "Statut Action",
                "Statut Opportunuité Taf",
            ]
            df_actions = pd.DataFrame(columns=actions_headers)
            df_actions.to_excel(
                writer, sheet_name="ACTIONS", index=False, freeze_panes=(1, 0)
            )

            # 6. Data Validation
            print(f"{dt.datetime.now()} - INFO - Setting up data validations.")
            max_row_validation = 5000

            # CONTACTS Sheet Validations
            ws_contacts = workbook["CONTACTS"]
            dv_contacts_entreprise = DataValidation(
                type="list",
                formula1=f"=ENTREPRISES!$B$2:$B${max_row_validation}",
                allow_blank=True,
            )
            dv_contacts_entreprise.error = "Veuillez choisir une entreprise de la liste (Feuille ENTREPRISES, colonne 'Dénomination - Enseigne')."
            dv_contacts_entreprise.errorTitle = "Entreprise Invalide"
            ws_contacts.add_data_validation(dv_contacts_entreprise)
            dv_contacts_entreprise.add(f"B2:B{max_row_validation}")

            dv_contacts_direction = DataValidation(
                type="list",
                formula1=f"=VALEURS_LISTE!$A$2:$A${max_row_validation}",
                allow_blank=True,
            )
            dv_contacts_direction.error = "Veuillez choisir une direction de la liste (Feuille VALEURS_LISTE, colonne 'CONTACTS_Direction')."
            dv_contacts_direction.errorTitle = "Direction Invalide"
            ws_contacts.add_data_validation(dv_contacts_direction)
            dv_contacts_direction.add(f"D2:D{max_row_validation}")

            # ACTIONS Sheet Validations
            ws_actions = workbook["ACTIONS"]
            dv_actions_entreprise = DataValidation(
                type="list",
                formula1=f"=ENTREPRISES!$B$2:$B${max_row_validation}",
                allow_blank=True,
            )
            dv_actions_entreprise.error = "Veuillez choisir une entreprise de la liste (Feuille ENTREPRISES, colonne 'Dénomination - Enseigne')."
            dv_actions_entreprise.errorTitle = "Entreprise Invalide"
            ws_actions.add_data_validation(dv_actions_entreprise)
            dv_actions_entreprise.add(f"A2:A{max_row_validation}")

            dv_actions_contact = DataValidation(
                type="list",
                formula1=f"=CONTACTS!$A$2:$A${max_row_validation}",
                allow_blank=True,
            )
            dv_actions_contact.error = "Veuillez choisir un contact de la liste (Feuille CONTACTS, colonne 'Prénom Nom')."
            dv_actions_contact.errorTitle = "Contact Invalide"
            ws_actions.add_data_validation(dv_actions_contact)
            dv_actions_contact.add(f"B2:B{max_row_validation}")

            dv_actions_type = DataValidation(
                type="list",
                formula1=f"=VALEURS_LISTE!$B$2:$B${max_row_validation}",
                allow_blank=True,
            )
            dv_actions_type.error = "Veuillez choisir un type d'action (Feuille VALEURS_LISTE, colonne 'ACTIONS_TypeAction')."
            dv_actions_type.errorTitle = "Type d'Action Invalide"
            ws_actions.add_data_validation(dv_actions_type)
            dv_actions_type.add(f"C2:C{max_row_validation}")

            dv_actions_statut = DataValidation(
                type="list",
                formula1=f"=VALEURS_LISTE!$C$2:$C${max_row_validation}",
                allow_blank=True,
            )
            dv_actions_statut.error = "Veuillez choisir un statut d'action (Feuille VALEURS_LISTE, colonne 'ACTIONS_StatutAction')."
            dv_actions_statut.errorTitle = "Statut d'Action Invalide"
            ws_actions.add_data_validation(dv_actions_statut)
            dv_actions_statut.add(f"F2:F{max_row_validation}")

            dv_actions_opportunite = DataValidation(
                type="list",
                formula1=f"=VALEURS_LISTE!$D$2:$D${max_row_validation}",
                allow_blank=True,
            )
            dv_actions_opportunite.error = "Veuillez choisir un statut d'opportunité (Feuille VALEURS_LISTE, colonne 'ACTIONS_StatutOpportunuiteTaf')."
            dv_actions_opportunite.errorTitle = "Statut Opportunité Invalide"
            ws_actions.add_data_validation(dv_actions_opportunite)
            dv_actions_opportunite.add(f"G2:G{max_row_validation}")
            print(f"{dt.datetime.now()} - INFO - Data validations set up.")

            # 7. Formatting: Auto-adjust column widths
            print(f"{dt.datetime.now()} - INFO - Adjusting column widths.")
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                for col_idx, column in enumerate(sheet.columns):
                    max_length = 0
                    column_letter = get_column_letter(col_idx + 1)

                    header_cell = sheet.cell(row=1, column=col_idx + 1)
                    if header_cell.value:
                        max_length = len(str(header_cell.value))

                    if sheet_name in ["DATA_IMPORT", "VALEURS_LISTE"]:
                        for i, cell in enumerate(column):
                            if i == 0:
                                continue
                            try:
                                if cell.value:
                                    cell_len = len(str(cell.value))
                                    if cell_len > max_length:
                                        max_length = cell_len
                            except:
                                pass
                    elif sheet_name == "ENTREPRISES":
                        if col_idx + 1 == 6 or col_idx + 1 == 7:
                            max_length = max(max_length, 30)
                        else:
                            for i in range(min(5, num_data_rows)):
                                cell_value_formula = sheet.cell(
                                    row=i + 2, column=col_idx + 1
                                ).value
                                if cell_value_formula:
                                    pass

                    adjusted_width = (max_length + 2) * 1.2
                    adjusted_width = min(adjusted_width, 60)
                    sheet.column_dimensions[column_letter].width = adjusted_width

            # 8. Styling Headers & Hyperlink styling for specific columns
            header_font = Font(bold=True, color="FFFFFFFF")
            header_fill = PatternFill(
                start_color="FF4472C4", end_color="FF4472C4", fill_type="solid"
            )
            header_alignment = Alignment(horizontal="center", vertical="center")

            sheets_to_style_headers = [
                "ENTREPRISES",
                "CONTACTS",
                "ACTIONS",
                "VALEURS_LISTE",
            ]
            for sheet_name in sheets_to_style_headers:
                if sheet_name in workbook.sheetnames:
                    sheet = workbook[sheet_name]
                    for cell in sheet[1]:
                        cell.font = header_font
                        cell.fill = header_fill
                        cell.alignment = header_alignment
            
            # Specific styling for hyperlink columns in ENTREPRISES
            ws_entreprises_style = workbook["ENTREPRISES"]
            link_font = Font(color="0563C1", underline="single")
            # Indices de colonnes pour openpyxl (1-basés):
            # Recherche LinkedIn = 3 (C)
            # Recherche Google Maps = 4 (D)
            # Recherche Indeed = 5 (E)
            link_columns_indices = [3, 4, 5]
            for col_idx in link_columns_indices:
                for row_idx in range(2, num_data_rows + 2): # Data rows + header
                    cell = ws_entreprises_style.cell(row=row_idx, column=col_idx)
                    if row_idx > 1: # Skip header
                        cell.font = link_font

            # 9. Hide DATA_IMPORT sheet
            if "DATA_IMPORT" in workbook.sheetnames:
                ws_data_import = workbook["DATA_IMPORT"]
                ws_data_import.sheet_state = "hidden"

            # 10. Set Sheet Order
            # Desired order of visible sheets, DATA_IMPORT will be last among (potentially) visible then hidden
            # The actual creation order was: DATA_IMPORT, ENTREPRISES, VALEURS_LISTE, CONTACTS, ACTIONS
            # New desired order: ENTREPRISES, CONTACTS, ACTIONS, VALEURS_LISTE, (DATA_IMPORT hidden)

            # Get all sheet titles currently in the workbook
            current_sheet_titles = [sheet.title for sheet in workbook._sheets]

            # Define the desired visible order
            desired_visible_order = [
                "ENTREPRISES",
                "CONTACTS",
                "ACTIONS",
                "VALEURS_LISTE",
            ]

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
            print(f"{dt.datetime.now()} - INFO - Sheet order set.")

        print(
            f"{dt.datetime.now()} - INFO - Excel file generation complete. Returning output."
        )
    except Exception as e:
        print(f"{dt.datetime.now()} - ERROR - Exception during Excel generation: {e}")
        st.error(
            f"Une erreur est survenue lors de la génération du fichier Excel : {e}"
        )
        import traceback

        st.error(traceback.format_exc())
        return None

    output.seek(0)
    return output.getvalue()


def generate_user_erm_excel(
    df_entreprises: pd.DataFrame, df_contacts: pd.DataFrame, df_actions: pd.DataFrame
) -> bytes:
    """
    Génère un fichier Excel (.xlsx) à partir des DataFrames ERM de l'utilisateur.
    """
    print(f"{dt.datetime.now()} - INFO - generate_user_erm_excel called.")
    print(
        f"{dt.datetime.now()} - INFO - Input df_entreprises shape: {df_entreprises.shape}, df_contacts shape: {df_contacts.shape}, df_actions shape: {df_actions.shape}"
    )
    output = BytesIO()
    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            workbook = writer.book
            print(
                f"{dt.datetime.now()} - INFO - ExcelWriter created for user ERM export."
            )

            # 1. DATA_IMPORT Sheet (from df_entreprises, but only relevant columns)
            print(
                f"{dt.datetime.now()} - INFO - Creating DATA_IMPORT sheet for user ERM."
            )
            # These are typically columns that might come from an initial API search or import,
            # excluding user-added notes or statuses if they are not part of the "raw" data concept.
            # For this version, we'll include most columns from df_entreprises but ensure
            # it matches the structure expected if it were raw data.
            data_import_cols = [
                "SIRET",
                "Dénomination - Enseigne",
                "Activité NAF/APE Etablissement",
                "Adresse établissement",
                "Nb salariés établissement",
                "Est siège social",
                "Date de création Entreprise",
                "Chiffre d'Affaires Entreprise",
                "Résultat Net Entreprise",
                "Année Finances Entreprise",
                "SIREN",
            ]
            df_data_import = pd.DataFrame()
            for col in data_import_cols:
                if col in df_entreprises.columns:
                    df_data_import[col] = df_entreprises[col]
                else:
                    df_data_import[col] = pd.NA

            df_data_import = df_data_import[data_import_cols]
            df_data_import.to_excel(
                writer, sheet_name="DATA_IMPORT", index=False, freeze_panes=(1, 0)
            )
            num_data_rows_entreprises = len(
                df_entreprises
            )  # Used for formula ranges later

            # 2. ENTREPRISES Sheet (direct from user's df_entreprises)
            df_entreprises_sheet = df_entreprises.copy()
            num_data_rows_entreprises_sheet = len(df_entreprises_sheet)

            # Define base columns for the ENTREPRISES sheet, excluding unwanted ones
            # SIREN, Code effectif établissement, Effectif Numérique are excluded here.
            entreprises_export_base_cols = [
                "SIRET",
                "Dénomination - Enseigne",
                "Recherche LinkedIn",
                "Recherche Google Maps",
                "Recherche Indeed",
                # Placeholder for hyperlink columns
                "Activité NAF/APE Etablissement",
                "Adresse établissement",
                "Nb salariés établissement",
                "Est siège social",
                "Date de création Entreprise",
                "Chiffre d'Affaires Entreprise",
                "Résultat Net Entreprise",
                "Année Finances Entreprise",
            ]
            
            # Define hyperlink column names
            hyperlink_col_names = ["Recherche LinkedIn", "Recherche Google Maps", "Recherche Indeed"]

            # Build the final list of columns for the sheet structure
            final_cols_for_sheet_structure = entreprises_export_base_cols[:]
            denom_index = final_cols_for_sheet_structure.index("Dénomination - Enseigne") + 1
            for col_name in reversed(hyperlink_col_names): # Insert in correct order
                final_cols_for_sheet_structure.insert(denom_index, col_name)

            # Add user-specific columns if they exist in the input df_entreprises
            user_specific_cols_to_check = ["Notes Personnelles", "Statut Piste"]
            for user_col in user_specific_cols_to_check:
                if user_col in df_entreprises.columns:
                    if user_col not in final_cols_for_sheet_structure:
                        final_cols_for_sheet_structure.append(user_col)
            
            # Create a DataFrame with only the necessary columns for the Excel sheet structure
            # Columns for hyperlinks will be present but data will be written by openpyxl formulas
            df_entreprises_to_export = pd.DataFrame(columns=final_cols_for_sheet_structure)
            for col in final_cols_for_sheet_structure:
                if col in df_entreprises_sheet.columns and col not in hyperlink_col_names:
                    df_entreprises_to_export[col] = df_entreprises_sheet[col]
                elif col not in hyperlink_col_names: # Ensure all structural columns exist even if not in source
                    df_entreprises_to_export[col] = pd.NA
            
            # Ensure correct order
            df_entreprises_to_export = df_entreprises_to_export.reindex(columns=final_cols_for_sheet_structure)

            df_entreprises_sheet.to_excel(
                writer, sheet_name="ENTREPRISES", index=False, freeze_panes=(1, 0)
            )
            ws_entreprises_export = workbook["ENTREPRISES"]

            # Get column letters for formula references
            # Assuming "Dénomination - Enseigne" is col B, "Adresse établissement" needs its letter
            col_letter_denomination = 'B' # Dénomination - Enseigne
            adresse_col_name = "Adresse établissement"
            col_letter_adresse = 'A' # Default, will be updated
            if adresse_col_name in final_cols_for_sheet_structure:
                col_letter_adresse = get_column_letter(final_cols_for_sheet_structure.index(adresse_col_name) + 1)

            # Write HYPERLINK formulas row by row
            for r_idx in range(num_data_rows_entreprises_sheet):
                excel_row = r_idx + 2  # Excel rows are 1-indexed

                # Recherche LinkedIn
                linkedin_col_idx = final_cols_for_sheet_structure.index("Recherche LinkedIn") + 1
                ws_entreprises_export.cell(
                    row=excel_row, column=linkedin_col_idx,
                    value=f'=HYPERLINK("https://www.google.com/search?q="&{col_letter_denomination}{excel_row}&"+site%3Alinkedin.com%2Fcompany%2F","Recherche LinkedIn")'
                )
                # Recherche Google Maps
                gmaps_col_idx = final_cols_for_sheet_structure.index("Recherche Google Maps") + 1
                ws_entreprises_export.cell(
                    row=excel_row, column=gmaps_col_idx,
                    value=f'=HYPERLINK("https://www.google.com/maps/search/?api=1&query="&{col_letter_denomination}{excel_row}&","&{col_letter_adresse}{excel_row}&"","Recherche Google Maps")'
                )
                # Recherche Indeed
                indeed_col_idx = final_cols_for_sheet_structure.index("Recherche Indeed") + 1
                ws_entreprises_export.cell(
                    row=excel_row, column=indeed_col_idx,
                    value=f'=HYPERLINK("https://www.google.com/search?q="&{col_letter_denomination}{excel_row}&"+site%3Aindeed.com","Recherche Indeed")'
                )

            # 3. VALEURS_LISTE Sheet (from config)
            vl_headers = [
                "CONTACTS_Direction",
                "ACTIONS_TypeAction",
                "ACTIONS_StatutAction",
                "ACTIONS_StatutOpportunuiteTaf",
            ]
            vl_data_from_config = {
                "CONTACTS_Direction": config.VALEURS_LISTE_CONTACTS_DIRECTION,
                "ACTIONS_TypeAction": config.VALEURS_LISTE_ACTIONS_TYPEACTION,
                "ACTIONS_StatutAction": config.VALEURS_LISTE_ACTIONS_STATUTACTION,
                "ACTIONS_StatutOpportunuiteTaf": config.VALEURS_LISTE_ACTIONS_STATUTOPPORTUNITE,
            }
            max_len_vl = max(len(lst) for lst in vl_data_from_config.values())
            padded_vl_data = {
                col: lst + [pd.NA] * (max_len_vl - len(lst))
                for col, lst in vl_data_from_config.items()
            }
            df_valeurs_liste = pd.DataFrame(padded_vl_data)
            df_valeurs_liste = df_valeurs_liste[vl_headers]
            df_valeurs_liste.to_excel(
                writer, sheet_name="VALEURS_LISTE", index=False, freeze_panes=(1, 0)
            )

            # 4. CONTACTS Sheet (direct from user's df_contacts)
            df_contacts_sheet = df_contacts.copy()
            expected_contact_cols = [
                "Prénom Nom",
                "Entreprise",
                "Poste",
                "Direction",
                "Email",
                "Téléphone",
                "Profil LinkedIn URL",
                "Notes",
            ]
            for col in expected_contact_cols:
                if col not in df_contacts_sheet.columns:
                    df_contacts_sheet[col] = pd.NA
            df_contacts_sheet = df_contacts_sheet[expected_contact_cols]
            df_contacts_sheet.to_excel(
                writer, sheet_name="CONTACTS", index=False, freeze_panes=(1, 0)
            )

            # 5. ACTIONS Sheet (direct from user's df_actions)
            df_actions_sheet = df_actions.copy()
            # Ensure 'Date Action' is string or Excel might format it poorly if NaT exists
            if "Date Action" in df_actions_sheet.columns:
                df_actions_sheet["Date Action"] = (
                    df_actions_sheet["Date Action"]
                    .astype(object)
                    .where(df_actions_sheet["Date Action"].notnull(), None)
                )

            expected_action_cols = [
                "Entreprise",
                "Contact (Prénom Nom)",
                "Type Action",
                "Date Action",
                "Description/Notes",
                "Statut Action",
                "Statut Opportunuité Taf",
            ]
            for col in expected_action_cols:
                if col not in df_actions_sheet.columns:
                    df_actions_sheet[col] = pd.NA
            df_actions_sheet = df_actions_sheet[expected_action_cols]
            df_actions_sheet.to_excel(
                writer, sheet_name="ACTIONS", index=False, freeze_panes=(1, 0)
            )

            # 6. Data Validation (similar to generate_erm_excel)
            print(
                f"{dt.datetime.now()} - INFO - Setting up data validations for user ERM export."
            )
            max_row_validation = 5000  # Consistent with other function

            # CONTACTS Sheet Validations
            ws_contacts = workbook["CONTACTS"]
            # Entreprise validation (from ENTREPRISES sheet, 'Dénomination - Enseigne' column - B)
            dv_contacts_entreprise = DataValidation(
                type="list",
                formula1=f"=ENTREPRISES!$B$2:$B${max_row_validation}",
                allow_blank=True,
            )
            ws_contacts.add_data_validation(dv_contacts_entreprise)
            dv_contacts_entreprise.add(f"B2:B{max_row_validation}")
            # Direction validation (from VALEURS_LISTE sheet, column A)
            dv_contacts_direction = DataValidation(
                type="list",
                formula1=f"=VALEURS_LISTE!$A$2:$A${max_row_validation}",
                allow_blank=True,
            )
            ws_contacts.add_data_validation(dv_contacts_direction)
            dv_contacts_direction.add(f"D2:D{max_row_validation}")

            # ACTIONS Sheet Validations
            ws_actions = workbook["ACTIONS"]
            # Entreprise validation
            dv_actions_entreprise = DataValidation(
                type="list",
                formula1=f"=ENTREPRISES!$B$2:$B${max_row_validation}",
                allow_blank=True,
            )
            ws_actions.add_data_validation(dv_actions_entreprise)
            dv_actions_entreprise.add(f"A2:A{max_row_validation}")
            # Contact validation (from CONTACTS sheet, 'Prénom Nom' column - A)
            dv_actions_contact = DataValidation(
                type="list",
                formula1=f"=CONTACTS!$A$2:$A${max_row_validation}",
                allow_blank=True,
            )
            ws_actions.add_data_validation(dv_actions_contact)
            dv_actions_contact.add(f"B2:B{max_row_validation}")
            # Type Action (from VALEURS_LISTE sheet, column B)
            dv_actions_type = DataValidation(
                type="list",
                formula1=f"=VALEURS_LISTE!$B$2:$B${max_row_validation}",
                allow_blank=True,
            )
            ws_actions.add_data_validation(dv_actions_type)
            dv_actions_type.add(f"C2:C{max_row_validation}")
            # Statut Action (from VALEURS_LISTE sheet, column C)
            dv_actions_statut = DataValidation(
                type="list",
                formula1=f"=VALEURS_LISTE!$C$2:$C${max_row_validation}",
                allow_blank=True,
            )
            ws_actions.add_data_validation(dv_actions_statut)
            dv_actions_statut.add(f"F2:F{max_row_validation}")
            # Statut Opportunuité Taf (from VALEURS_LISTE sheet, column D)
            dv_actions_opportunite = DataValidation(
                type="list",
                formula1=f"=VALEURS_LISTE!$D$2:$D${max_row_validation}",
                allow_blank=True,
            )
            ws_actions.add_data_validation(dv_actions_opportunite)
            dv_actions_opportunite.add(f"G2:G{max_row_validation}")
            print(
                f"{dt.datetime.now()} - INFO - Data validations set up for user ERM export."
            )

            # 7. Formatting: Auto-adjust column widths
            print(
                f"{dt.datetime.now()} - INFO - Adjusting column widths for user ERM export."
            )
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                for col_idx, column_cells in enumerate(sheet.columns):
                    max_length = 0
                    column_letter = get_column_letter(col_idx + 1)

                    # Header length
                    if sheet.cell(row=1, column=col_idx + 1).value:
                        max_length = len(
                            str(sheet.cell(row=1, column=col_idx + 1).value)
                        )

                    # Cell content length (check first N rows for performance)
                    for i, cell in enumerate(column_cells):
                        if i > 100:
                            break
                        try:
                            if cell.value:
                                cell_len = len(str(cell.value))
                                if cell_len > max_length:
                                    max_length = cell_len
                        except:
                            pass
                    adjusted_width = (max_length + 2) * 1.2
                    adjusted_width = min(adjusted_width, 60)  # Cap max width
                    sheet.column_dimensions[column_letter].width = adjusted_width

            # 8. Styling Headers & Hyperlinks
            header_font = Font(bold=True, color="FFFFFFFF")
            header_fill = PatternFill(
                start_color="FF4472C4", end_color="FF4472C4", fill_type="solid"
            )
            header_alignment = Alignment(horizontal="center", vertical="center")
            sheets_to_style_headers = [
                "ENTREPRISES",
                "CONTACTS",
                "ACTIONS",
                "VALEURS_LISTE",
                "DATA_IMPORT",
            ]
            for sheet_name in sheets_to_style_headers:
                if sheet_name in workbook.sheetnames:
                    sheet = workbook[sheet_name]
                    for cell in sheet[1]:
                        cell.font = header_font
                        cell.fill = header_fill
                        cell.alignment = header_alignment
            
            # Specific styling for hyperlink columns in ENTREPRISES
            ws_entreprises_user_style = workbook["ENTREPRISES"]
            link_font_user = Font(color="0563C1", underline="single")
            # Apply link style to the hyperlink formula columns
            for col_name_link in hyperlink_col_names:
                if col_name_link in final_cols_for_sheet_structure:
                    col_idx_excel = final_cols_for_sheet_structure.index(col_name_link) + 1
                    for row_idx_user in range(2, num_data_rows_entreprises_sheet + 2): # Data rows + header
                        cell_user = ws_entreprises_user_style.cell(row=row_idx_user, column=col_idx_excel)
                        if row_idx_user > 1: # Skip header
                            cell_user.font = link_font_user

            # 9. Hide DATA_IMPORT sheet
            if "DATA_IMPORT" in workbook.sheetnames:
                workbook["DATA_IMPORT"].sheet_state = "hidden"

            # 10. Set Sheet Order
            desired_visible_order = [
                "ENTREPRISES",
                "CONTACTS",
                "ACTIONS",
                "VALEURS_LISTE",
            ]
            current_sheet_titles = [sheet.title for sheet in workbook._sheets]
            final_ordered_sheets = []
            for title in desired_visible_order:
                if title in current_sheet_titles:
                    final_ordered_sheets.append(workbook[title])
            for title in current_sheet_titles:
                if title not in desired_visible_order:
                    final_ordered_sheets.append(workbook[title])
            workbook._sheets = final_ordered_sheets
            print(f"{dt.datetime.now()} - INFO - Sheet order set for user ERM export.")

    except Exception as e:
        print(
            f"{dt.datetime.now()} - ERROR - Exception during user ERM Excel generation: {e}"
        )
        import traceback

        print(traceback.format_exc())
        return None

    output.seek(0)
    print(
        f"{dt.datetime.now()} - INFO - User ERM Excel file generation complete. Returning output."
    )
    return output.getvalue()


def add_entreprise_records(
    current_df_entreprises: pd.DataFrame,
    new_records_df: pd.DataFrame,
    expected_cols: list,
) -> pd.DataFrame:
    """
    Adds new entreprise records to the current DataFrame of entreprises,
    handles deduplication, and ensures schema.
    """
    print(f"{dt.datetime.now()} - INFO - add_entreprise_records called.")
    print(
        f"{dt.datetime.now()} - INFO - Shape of current_df_entreprises: {current_df_entreprises.shape}"
    )
    print(
        f"{dt.datetime.now()} - INFO - Shape of new_records_df: {new_records_df.shape}"
    )

    # Ensure current_df_entreprises has the expected schema
    current_df_processed = current_df_entreprises.copy()
    for col in expected_cols:
        if col not in current_df_processed.columns:
            current_df_processed[col] = pd.NA
    current_df_processed = current_df_processed.reindex(columns=expected_cols)

    # Ensure new_records_df has the expected schema
    new_records_processed = new_records_df.copy()
    for col in expected_cols:
        if col not in new_records_processed.columns:
            new_records_processed[col] = pd.NA
    new_records_processed = new_records_processed.reindex(columns=expected_cols)

    if new_records_processed.empty:
        print(
            f"{dt.datetime.now()} - INFO - new_records_df is empty. Returning processed current_df_entreprises."
        )
        # If there are no new records to add, return the processed current DataFrame
        return current_df_processed

    # Concatenate
    combined_df = pd.concat(
        [current_df_processed, new_records_processed], ignore_index=True
    )
    print(
        f"{dt.datetime.now()} - INFO - Shape after concatenation: {combined_df.shape}"
    )

    # Drop duplicates, prioritizing the newly added records ('last')
    # Only attempt drop_duplicates if 'SIRET' is present and DataFrame is not empty
    if "SIRET" in combined_df.columns and not combined_df.empty:
        # Fill NA in SIRET column before dropping duplicates to avoid issues with pd.NA comparison if any
        # However, SIRET is expected to be non-null for valid records.
        # If SIRET can be legitimately NA and these rows should be kept, this needs adjustment.
        # For now, assuming SIRET is a key that should exist.
        combined_df.drop_duplicates(subset=["SIRET"], keep="last", inplace=True)
        print(
            f"{dt.datetime.now()} - INFO - Shape after dropping duplicates on SIRET: {combined_df.shape}"
        )

    combined_df = combined_df.reindex(columns=expected_cols)
    print(
        f"{dt.datetime.now()} - INFO - add_entreprise_records finished. Final shape: {combined_df.shape}"
    )
    return combined_df


def ensure_df_schema(df: pd.DataFrame, expected_cols: list) -> pd.DataFrame:
    """
    Ensures the DataFrame has all expected columns with pd.NA for missing ones,
    and reorders columns to match expected_cols.
    """
    print(
        f"{dt.datetime.now()} - INFO - ensure_df_schema called for DataFrame with shape {df.shape}."
    )
    df_processed = df.copy()
    added_cols = []
    for col in expected_cols:
        if col not in df_processed.columns:
            df_processed[col] = pd.NA
            added_cols.append(col)
    if added_cols:
        print(
            f"{dt.datetime.now()} - INFO - ensure_df_schema: Added missing columns: {added_cols}"
        )
    else:
        print(
            f"{dt.datetime.now()} - INFO - ensure_df_schema: No columns were added, all expected columns present."
        )

    # Ensure correct column order and drop any columns not in expected_cols
    final_df = df_processed.reindex(columns=expected_cols)
    print(
        f"{dt.datetime.now()} - INFO - ensure_df_schema finished. Output DataFrame shape: {final_df.shape}"
    )
    return final_df


def get_erm_data_for_saving() -> dict:
    """
    Retrieves ERM DataFrames from session state, performs necessary cleaning,
    and returns a dictionary formatted for JSON saving.
    """
    print(f"{dt.datetime.now()} - INFO - get_erm_data_for_saving called.")
    # Ensure DataFrames exist in session_state and have a default schema if empty
    # This part relies on the main app ensuring df_entreprises, df_contacts, df_actions exist
    # and preferably have their schemas (expected_cols) applied.

    df_e = st.session_state.get("df_entreprises", pd.DataFrame())
    df_c = st.session_state.get("df_contacts", pd.DataFrame())
    df_a = st.session_state.get("df_actions", pd.DataFrame())
    print(
        f"{dt.datetime.now()} - INFO - Retrieved from session state: {len(df_e)} entreprises, {len(df_c)} contacts, {len(df_a)} actions."
    )

    # Perform data cleaning, especially for JSON serialization compatibility
    # Example: Convert NaT in 'Date Action' to None for df_actions
    df_a_cleaned = df_a.copy()
    if "Date Action" in df_a_cleaned.columns:
        # Ensure it's datetime first, then convert NaT to None
        df_a_cleaned["Date Action"] = pd.to_datetime(
            df_a_cleaned["Date Action"], errors="coerce"
        )
        df_a_cleaned["Date Action"] = (
            df_a_cleaned["Date Action"]
            .astype(object)
            .where(df_a_cleaned["Date Action"].notnull(), None)
        )
        print(
            f"{dt.datetime.now()} - INFO - Cleaned 'Date Action' column for JSON serialization."
        )

    erm_data = {
        "entreprises": df_e.to_dict(orient="records"),
        "contacts": df_c.to_dict(orient="records"),
        "actions": df_a_cleaned.to_dict(orient="records"),
    }
    print(f"{dt.datetime.now()} - INFO - ERM data converted to dict. Ready for saving.")
    return erm_data

#https://recherche-entreprises.api.gouv.fr/docs/#tag/Recherche-textuelle/paths/~1search/get 
import requests
import json
import openpyxl
import pandas as pd
from openpyxl.utils.dataframe import dataframe_to_rows

def rechercher_entreprises_restauration_detaillees(departement, tranche_effectif):
    """
    Recherche les entreprises du secteur de la restauration actives avec la tranche
    d'effectif salarié spécifiée dans le département donné et récupère les
    informations détaillées.

    Args:
        departement (str): Le code du département (ex: "62").
        tranche_effectif (list): Une liste des codes de tranche d'effectif salarié.

    Returns:
        list: Une liste d'informations détaillées sur les entreprises trouvées.
    """
    url = "https://recherche-entreprises.api.gouv.fr/search"
    params = {
        'section_activite_principale': 'I',
        'etat_administratif': 'A',
        'departement': departement,
        'tranche_effectif_salarie': ','.join(tranche_effectif),
        'per_page': 25  # Nombre maximum de résultats par page
    }
    headers = {'accept': 'application/json'}
    entreprises_detaillees = []
    page = 1

    while True:
        params['page'] = page
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()  # Lève une exception en cas d'erreur HTTP
        data = response.json()
        results = data.get('results', [])
        if not results:
            break  # Plus de résultats

        entreprises_detaillees.extend(results)
        page += 1
        if page > data.get('total_pages', page):  # Pour éviter une boucle infinie
            break

    return entreprises_detaillees


def preparer_donnees_pour_excel_etablissements(entreprises):
    """
    Prépare les données pour l'export Excel, une ligne par établissement.

    Args:
        entreprises (list): Une liste d'informations détaillées sur les entreprises.

    Returns:
        list: Une liste de dictionnaires représentant les établissements,
              prêtes pour l'export Excel.
    """
    etablissements_pour_excel = []
    for entreprise in entreprises:
        siren = entreprise.get('siren', 'N/A')
        nom_entreprise = entreprise.get('nom_raison_sociale', 'N/A')
        dirigeants = entreprise.get('dirigeants', [])
        noms_dirigeants = ", ".join(
            [f"{dirigeant.get('nom', 'N/A')} {dirigeant.get('prenoms', 'N/A')}".strip() for dirigeant in dirigeants])

        siege = entreprise.get('siege', {})
        adresse_siege = siege.get('adresse', 'N/A')
        latitude_siege = siege.get('latitude', 'N/A')
        longitude_siege = siege.get('longitude', 'N/A')

        finances = entreprise.get('finances', {})
        finance_annee = str(list(finances.keys())[0]) if finances and finances.keys() else 'N/A'
        ca = str(finances.get(finance_annee, {}).get('ca', 'N/A')) if finances and finances.get(finance_annee, {}) else 'N/A'
        resultat_net = str(finances.get(finance_annee, {}).get('resultat_net', 'N/A')) if finances and finances.get(finance_annee, {}) else 'N/A'

        matching_etablissements = entreprise.get('matching_etablissements', [])
        for etablissement in matching_etablissements:
            etablissement_info_excel = {
                'SIREN': siren,
                'Nom Entreprise': nom_entreprise,
                'Dirigeants': noms_dirigeants,
                'Adresse Siège': adresse_siege,
                'Latitude Siège': latitude_siege,
                'Longitude Siège': longitude_siege,
                'Adresse Etablissement': etablissement.get('adresse', 'N/A'),
                'Activité Principale Etablissement': etablissement.get('activite_principale', 'N/A'),
                'Année CA/Résultat': finance_annee,
                'Chiffre d\'affaires': ca,
                'Résultat Net': resultat_net
            }
            etablissements_pour_excel.append(etablissement_info_excel)

    return etablissements_pour_excel


def exporter_vers_excel(data, nom_fichier="entreprises_restauration.xlsx"):
    """
    Exporte les données vers un fichier Excel, une ligne par établissement.

    Args:
        data (list): Une liste de dictionnaires représentant les établissements.
        nom_fichier (str): Le nom du fichier Excel à créer.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Etablissements"  # Nom de la feuille

    # Créer les en-têtes
    headers = list(data[0].keys()) if data else []
    ws.append(headers)

    # Ajouter les données
    for etablissement in data:
        row = list(etablissement.values())
        ws.append(row)

    try:
        wb.save(nom_fichier)
        print(f"\nLes données ont été exportées vers le fichier Excel : {nom_fichier}")
    except Exception as e:
        print(f"Erreur lors de l'enregistrement du fichier Excel : {e}")


if __name__ == "__main__":
    departement_recherche = "62"
    tranches_effectif_recherche = ['03', '11', '12', '21', '22', '31', '32', '41', '42', '51', '52', '53']

    print(
        f"Recherche détaillée des entreprises de la restauration (section I) actives avec plus de 2 salariés dans le département {departement_recherche}...")
    entreprises_detaillees_trouvees = rechercher_entreprises_restauration_detaillees(departement_recherche,
                                                                                    tranches_effectif_recherche)
    print(f"{len(entreprises_detaillees_trouvees)} entreprises trouvées.")

    print("\nPréparation des données pour l'export Excel (une ligne par établissement)...")
    etablissements_pour_excel = preparer_donnees_pour_excel_etablissements(entreprises_detaillees_trouvees)

    print("\nExportation vers Excel...")
    exporter_vers_excel(etablissements_pour_excel)

    print("\nScript terminé.")

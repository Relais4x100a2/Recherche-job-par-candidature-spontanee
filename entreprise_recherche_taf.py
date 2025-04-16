
import requests
import pandas as pd
import datetime


def rechercher_geographiquement_entreprises(lat, long, radius, section_activite_principale):
    """
    Recherche les entreprises dans des secteurs d'activités spécifiques par rapport à une coordonnée géographique
    et récupère les informations détaillées.

    Args:
        lat (float): Latitude de l'établissement
        long (float): Longitude de l'établissement
        radius (float): Radius de recherche, inférieur ou égal à 50km.
        section_activite_principale (string): Nomenclature d’activités française – NAF rév. 2. Ce paramètre accepte une valeur unique ou une liste de valeurs séparées par des virgules.

    Returns:
        list: Une liste d'informations détaillées sur les entreprises trouvées.
    """
    url = "https://recherche-entreprises.api.gouv.fr/near_point"
    params = {
        'lat': lat,
        'long': long,
        'radius': radius,
        'section_activite_principale': section_activite_principale,
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


def traitement_reponse_api(entreprises):
    """
    Prépare les données pour l'affichage sur une carte et pour Data Wrangler,
    en géocodant les adresses des établissements avec BANFrance si nécessaire,
    et inclut le SIREN, le SIRET et les informations des dirigeants.

    Args:
        entreprises (list): Une liste d'informations détaillées sur les entreprises.

    Returns:
        pandas.DataFrame: Un DataFrame contenant le SIREN, le SIRET, le nom de
                          l'entreprise, l'adresse de l'établissement, la latitude,
                          la longitude et le dictionnaire des dirigeants.
    """
    data = []

    # rajouter si siege social, exclure structure publique
    for entreprise in entreprises:
        siren = entreprise.get('siren', 'N/A')
        nom_complet = entreprise.get('nom_complet', 'N/A')
        nom_entreprise = entreprise.get('nom_raison_sociale', 'N/A')
        finances = entreprise.get('finances', {})
        matching_etablissements = entreprise.get('matching_etablissements', [])
        for etablissement in matching_etablissements:
            tranche_effectif_salarie = etablissement.get('tranche_effectif_salarie', 'N/A')
            if tranche_effectif_salarie in ['12', '21', '22', '31', '32', '41', '42', '51', '52', '53']:
                siret = etablissement.get('siret', 'N/A')
                adresse = etablissement.get('adresse_etablissement', etablissement.get('adresse', 'N/A'))
                latitude = etablissement.get('latitude')
                longitude = etablissement.get('longitude')
                #categorie_entreprise = etablissement.get('categorie_entreprise', 'N/A')
                data.append({
                    'SIREN': siren,
                    'Dénomination sociale': nom_entreprise,
                    'Nom complet': nom_complet,
                    'SIRET': siret,
                    'Tranche effectif salarié': tranche_effectif_salarie,
                    'Adresse': adresse,
                    'Latitude': latitude,
                    'Longitude': longitude,
                    "Finances": finances
                })
    return pd.DataFrame(data)

def enregistrer_dataframe_csv(df, nom_fichier_csv):
    """
    Enregistre le DataFrame dans un fichier CSV.

    Args:
        df (pandas.DataFrame): Le DataFrame à enregistrer.
        nom_fichier_csv (str): Le nom du fichier CSV à créer.
    """
    try:
        df.to_csv(nom_fichier_csv, index=False, encoding='utf-8')
        print(f"\nDataFrame des établissements sauvegardé dans : {nom_fichier_csv}")
    except Exception as e:
        print(f"Erreur lors de l'enregistrement du DataFrame au format CSV : {e}")


if __name__ == "__main__":
    # Coordonnées géographiques de l'établissement
    latitude = 48.802527
    longitude = 2.487473
    rayon = 5  # Rayon de recherche en km  
    setion_activite_principale = "C,D, E, F, G, H, J, K, M, Q, R, S" 
    # Recherche d'entreprises
    entreprises = rechercher_geographiquement_entreprises(latitude, longitude, rayon, setion_activite_principale)
    # Traitement de la réponse API
    df_etablissements = traitement_reponse_api(entreprises)
    # Enregistrement du DataFrame au format CSV
    print("\nEnregistrement du DataFrame au format CSV...")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    nom_fichier_csv = f"entreprises_{timestamp}.csv" # Use f-string for cleaner formatting
    enregistrer_dataframe_csv(df_etablissements, nom_fichier_csv)
    print("\nScript terminé.")
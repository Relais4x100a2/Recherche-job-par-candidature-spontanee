import requests
import json
import pandas as pd
import folium
from geopy.geocoders import BANFrance

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


def geocoder_ban_france(adresse):
    """
    Géocode une adresse en utilisant l'API de la Base Adresse Nationale (BAN) France.

    Args:
        adresse (str): L'adresse à géocoder.

    Returns:
        tuple or None: Un tuple contenant (latitude, longitude) si le géocodage réussit,
                       None sinon.
    """
    geolocator = BANFrance(user_agent="mon_application_datawrangler")
    try:
        location = geolocator.geocode(adresse, exactly_one=True, timeout=10)
        if location:
            return location.latitude, location.longitude
        else:
            return None
    except Exception as e:
        print(f"Erreur de géocodage pour '{adresse}': {e}")
        return None


def preparer_donnees_pour_la_carte_datawrangler(entreprises):
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
    for entreprise in entreprises:
        siren = entreprise.get('siren', 'N/A')
        nom_complet = entreprise.get('nom_complet', 'N/A')
        nom_entreprise = entreprise.get('nom_raison_sociale', 'N/A')
        nombre_etablissements = entreprise.get('nombre_etablissements', 0)
        nombre_etablissements_ouverts = entreprise.get('nombre_etablissements_ouverts', 0)
        dirigeants = entreprise.get('dirigeants', [])
        finances = entreprise.get('finances', {})
        matching_etablissements = entreprise.get('matching_etablissements', [])
        for etablissement in matching_etablissements:
            siret = etablissement.get('siret', 'N/A')
            adresse = etablissement.get('adresse_etablissement', etablissement.get('adresse', 'N/A'))
            latitude = etablissement.get('latitude')
            longitude = etablissement.get('longitude')

            if latitude is not None and longitude is not None:
                data.append({
                    'SIREN': siren,
                    'Nombre etablissements': nombre_etablissements,
                    'dont ouverts': nombre_etablissements_ouverts,
                    'SIRET': siret,
                    'Dénomination sociale': nom_entreprise,
                    'Nom complet': nom_complet,
                    'Adresse': adresse,
                    'Latitude': latitude,
                    'Longitude': longitude,
                    'Dirigeants': dirigeants,
                    "Finances": finances
                })
            else:
                coordonnees = geocoder_ban_france(adresse)
                if coordonnees:
                    data.append({
                        'SIREN': siren,
                        'Nombre etablissements': nombre_etablissements,
                        'dont ouverts': nombre_etablissements_ouverts,
                        'SIRET': siret,
                        'Dénomination sociale': nom_entreprise,
                        'Nom complet': nom_complet,
                        'Adresse': adresse,
                        'Latitude': coordonnees[0],
                        'Longitude': coordonnees[1],
                        'Dirigeants': dirigeants,
                        "Finances": finances
                    })
                else:
                    print(f"Impossible de géocoder l'établissement : {adresse}")
    return pd.DataFrame(data)


def generer_carte_html(df_etablissements, nom_fichier_html="carte_restauration.html", departement="France"):
    """
    Génère un fichier HTML contenant une carte interactive des établissements.

    Args:
        df_etablissements (pandas.DataFrame): DataFrame contenant les informations
                                               des établissements (Nom, Adresse, Latitude, Longitude).
        nom_fichier_html (str): Le nom du fichier HTML à créer.
        departement (str): Le nom du pays ou d'une région pour centrer initialement la carte.
    """
    geolocator = BANFrance(user_agent="mon_application_datawrangler_carte")
    try:
        location_departement = geolocator.geocode(departement, exactly_one=True, timeout=10)
        if location_departement:
            latitude_centre = location_departement.latitude
            longitude_centre = location_departement.longitude
            m = folium.Map(location=[latitude_centre, longitude_centre], zoom_start=9)
        else:
            print(f"Impossible de géolocaliser '{departement}', centrage de la carte par défaut.")
            m = folium.Map(location=[46.2276, 2.2137], zoom_start=5)  # Centre de la France par défaut
    except Exception as e:
        print(f"Erreur lors de la géolocalisation du département '{departement}': {e}")
        m = folium.Map(location=[46.2276, 2.2137], zoom_start=5)  # Centre de la France par défaut

    for index, row in df_etablissements.iterrows():
        if pd.notna(row['Latitude']) and pd.notna(row['Longitude']):
            folium.Marker([row['Latitude'], row['Longitude']], popup=f"{row['Nom complet']} (SIRET: {row['SIRET']})").add_to(m)

    m.save(nom_fichier_html)
    print(f"\nCarte interactive sauvegardée dans : {nom_fichier_html}")


def enregistrer_dataframe_csv(df, nom_fichier_csv="etablissements_carte.csv"):
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
    departement_recherche = "62"
    tranches_effectif_recherche = ['03', '11', '12', '21', '22', '31', '32', '41', '42', '51', '52', '53']

    print(
        f"Recherche détaillée des entreprises de la restauration (section I) actives avec plus de 2 salariés dans le département {departement_recherche}...")
    entreprises_detaillees_trouvees = rechercher_entreprises_restauration_detaillees(departement_recherche,
                                                                                    tranches_effectif_recherche)
    print(f"{len(entreprises_detaillees_trouvees)} entreprises trouvées.")

    print("\nPréparation des données pour la carte et Data Wrangler (géocodage des adresses)...")
    df_etablissements_carte = preparer_donnees_pour_la_carte_datawrangler(entreprises_detaillees_trouvees)
    print(f"\n{len(df_etablissements_carte)} établissements prêts pour la carte et Data Wrangler.")
    print(df_etablissements_carte.head())

    print("\nCréation et sauvegarde de la carte HTML...")
    generer_carte_html(df_etablissements_carte, departement=f"France, {departement_recherche}")

    print("\nEnregistrement du DataFrame au format CSV...")
    enregistrer_dataframe_csv(df_etablissements_carte)

    print("\nScript terminé.")
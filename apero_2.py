import click
import requests
from terminaltables import AsciiTable
from operator import itemgetter
import csv


@click.group()
def sirene():
    """
    Petit outil CLI pour dénicher des des petits-producteurs de victuailles pour apératifs & co.
    Affiche le numéro de SIRET, l'enseigne, l'adresse et la date de création de l'entreprise.
    Les ETI et GRANDES ENTREPRISES ont été exclues des résultats. Des améliorations sont à venir.

     4 commandes possibles :

     -biere

     -fromage

     - code_NAF : Autres productions en tapant le code NAF
     voir liste de l'INSEE : https://entreprise.data.gouv.fr/api-doc/codes_naf

     - recherche plein texte

     2 options possibles (cumulables) pour chaque commande:

     - limitation des résultats pour un département (numéro de département à indiquer) : -d numéro_du_département

     - impression dans un fichier csv en indiquant nom_du_fichier.csv : -imp nom_du_fichier.csv

     **Dolorean:2012-12-20 - Relais4x100a2**
     """

    return True


@sirene.command("biere")
@click.option("-d", "--departement", type=str, default="",
              help="Sélectionne les résultats dans le numéro de département indiqué classé selon ordre alphabétique des villes")
@click.option("-imp", "--impression", type=click.File(mode="w"), default=None,
              help="Imprime la liste des résultats")
def scope_content(departement=None, impression=None):
    #   URL de recherche API SIRENE pour les fabricants de bière
    url = "https://entreprise.data.gouv.fr/api/sirene/v1/full_text/*?per_page=100&departement={}&activite_principale=1105Z".format(
        departement)
    #   Avec la variable R, on passera une requête GET sur URL qui est le paramètre de la fonction"""
    r = requests.get(url)
    #  Avec la variable DATA, on récupera la réponse(le body) au format JSON """
    data = r.json()
    if "message" in data:
        print("Oups! Pas de résultat pour cette requête")
    else:
        current_page = int(data["page"])
        next_page = current_page
        total_page = int(data["total_pages"]) + 1
        """création d'une liste vide avec la varialble SIMPLIFIED"""
        header = [["SIRET", "Enseigne", "Adresse", "Date de création entreprise"]]
        simplified = []
        resultat = []

        # Comme on connait le nombre total de pages de résultats, on va faire une boucle pour chaque page
        for i in range(1, total_page):
            url = url + "&page={}".format(i)
            f = requests.get(url)
            """avec la variable DATA, on récupera la réponse(le body) au format JSON """
            dataf = f.json()
            """pour chaque fabricant de bière dans SIRENE"""
            for item in dataf["etablissement"]:
                """définition des éléments qu'on souhaite récupérer pour chaque item"""
                siret = item["siret"]
                denomination = item["nom_raison_sociale"]
                adresse = item["geo_adresse"]
                enseigne = item["enseigne"]
                categoriejur = item["categorie_entreprise"]
                nom = item["l1_normalisee"]
                date_creation = item["date_creation_entreprise"][0:4]
                num_departement = item["departement"]
                commune = item["libelle_commune"]
                """ajout des éléments dans la liste SIMPLIFIED parès nettoyage qualitatif"""
                # si l'adresse n'est pas renseignée, il y a un grand risque que l'affaire ne marche plus
                if adresse:
                    # on ne garde que les PME
                    if categoriejur == "PME":
                        if enseigne:
                            simplified.append([num_departement, commune, siret, enseigne, adresse, date_creation])
                        else:
                            if "*" in denomination:
                                simplified.append([num_departement, commune, siret, nom, adresse, date_creation])
                            else:
                                # lorsqu'il y a une indivision (succession), il y a un grand risque que l'affaire ne marche plus
                                if "INDIVISION" not in denomination:
                                    simplified.append(
                                        [num_departement, commune, siret, denomination, adresse, date_creation])
                    simplified = sorted(simplified, key=itemgetter(0, 1, 5))
        if impression:
            writer = csv.writer(impression)
            writer.writerow(["SIRET", "nom", "adresse", "date de création entreprise"])
            for item in simplified:
                writer.writerow([item[2], item[3], item[4], item[5]])
            print("Fichier CSV imprimé !")
        else:
            # on crée une nouvelle liste avec les seuls élèments qu'on souhaite afficher
            for entity in simplified:
                resultat.append(entity[2:])
            table = AsciiTable(header + resultat)
            print(table.table)


@sirene.command("fromage")
@click.option("-d", "--departement", type=str, default="",
              help="Sélectionne les résultats dans le numéro de département indiqué classé selon ordre alphabétique des villes puis de la date de création")
@click.option("-imp", "--impression", type=click.File(mode="w"), default=None,
              help="Imprime la liste des résultats")
def scope_content(departement=None, impression=None):
    # URL de recherche API SIRENE pour les fabricants de bière
    url = "https://entreprise.data.gouv.fr/api/sirene/v1/full_text/*?per_page=100&departement={}&activite_principale=1051C".format(
        departement)
    # Avec la variable R, on passera une requête GET sur URL qui est le paramètre de la fonction
    r = requests.get(url)
    # Avec la variable DATA, on récupera la réponse(le body) au format JSON """
    data = r.json()
    if "message" in data:
        print("Oups! Pas de résultat pour cette requête")
    else:
        current_page = int(data["page"])
        total_page = int(data["total_pages"]) + 1
        # Création d'une liste vide avec la varialble SIMPLIFIED
        header = [["SIRET", "Enseigne", "Adresse", "Date de création entreprise"]]
        simplified = []
        resultat = []

        # Comme on connait le nombre total de pages de résultats, on va faire une boucle pour chaque page
        for i in range(1, total_page):
            url = url + "&page={}".format(i)
            f = requests.get(url)
            # Avec la variable DATA, on récupera la réponse(le body) au format JSON """
            dataf = f.json()
            # Pour chaque fabricant de bière dans SIRENE"""
            for item in dataf["etablissement"]:
                """définition des éléments qu'on souhaite récupérer pour chaque item"""
                siret = item["siret"]
                denomination = item["nom_raison_sociale"]
                adresse = item["geo_adresse"]
                enseigne = item["enseigne"]
                categoriejur = item["categorie_entreprise"]
                nom = item["l1_normalisee"]
                date_creation = item["date_creation_entreprise"][0:4]
                num_departement = item["departement"]
                commune = item["libelle_commune"]
                # Ajout des éléments dans la liste SIMPLIFIED parès nettoyage qualitatif
                # si l'adresse n'est pas renseignée, il y a un grand risque que l'affaire ne marche plus
                if adresse:
                    # On ne garde que les PME
                    if categoriejur == "PME":
                        if enseigne:
                            simplified.append([num_departement, commune, siret, enseigne, adresse, date_creation])
                        else:
                            if "*" in denomination:
                                simplified.append([num_departement, commune, siret, nom, adresse, date_creation])
                            else:
                                # Lorsqu'il y a une indivision (succession), il y a un grand risque que l'affaire ne marche plus
                                if "INDIVISION" not in denomination:
                                    simplified.append(
                                        [num_departement, commune, siret, denomination, adresse, date_creation])
                    simplified = sorted(simplified, key=itemgetter(0, 1, 5))
        if impression:
            writer = csv.writer(impression)
            writer.writerow(["SIRET", "nom", "adresse", "date de création entreprise"])
            for item in simplified:
                writer.writerow([item[2], item[3], item[4], item[5]])
            print("Fichier CSV imprimé !")
        else:
            # On crée une nouvelle liste avec les seuls élèments qu'on souhaite afficher
            for entity in simplified:
                resultat.append(entity[2:])
            table = AsciiTable(header + resultat)
            print(table.table)


@sirene.command("code_NAF")
@click.argument("code", type=str)
@click.option("-d", "--departement", type=str, default="",
              help="Sélectionne les résultats dans le numéro de département indiqué classé selon ordre alphabétique des villes")
@click.option("-imp", "--impression", type=click.File(mode="w"), default=None,
              help="Imprime la liste des résultats")
def scope_content(code, departement, impression=None):
    print("Code de NAF de l'INSEE - pour plus d'aide voir la liste : https://entreprise.data.gouv.fr/api-doc/codes_naf")
    url = "https://entreprise.data.gouv.fr/api/sirene/v1/full_text/*?per_page=100&departement={}&activite_principale={}".format(
        departement, code)
    """avec la variable R, on passera une requête GET sur URL qui est le paramètre de la fonction"""
    r = requests.get(url)
    """avec la variable DATA, on récupera la réponse(le body) au format JSON """
    data = r.json()
    if "message" in data:
        print("Oups! Pas de résultat pour cette requête")
    else:
        current_page = int(data["page"])
        next_page = current_page
        total_page = int(data["total_pages"]) + 1
        """création d'une liste vide avec la varialble SIMPLIFIED"""
        header = [["SIRET", "Enseigne", "Adresse", "Date de création entreprise"]]
        simplified = []
        resultat = []
        # Comme on connait le nombre total de pages de résultats, on va faire une boucle pour chaque page
        for i in range(1, total_page):
            url = url + "&page={}".format(i)
            f = requests.get(url)
            # avec la variable DATA, on récupera la réponse(le body) au format JSON
            dataf = f.json()
            # pour chaque fabricant de bière dans SIRENE
            for item in dataf["etablissement"]:
                # définition des éléments qu'on souhaite récupérer pour chaque item
                siret = item["siret"]
                denomination = item["nom_raison_sociale"]
                adresse = item["geo_adresse"]
                enseigne = item["enseigne"]
                categoriejur = item["categorie_entreprise"]
                nom = item["l1_normalisee"]
                date_creation = item["date_creation_entreprise"][0:4]
                num_departement = item["departement"]
                commune = item["libelle_commune"]
                tranche_eff = item["tranche_effectif_salarie"]
                # ajout des éléments dans la liste SIMPLIFIED parès nettoyage qualitatif
                # si l'adresse n'est pas renseignée, il y a un grand risque que l'affaire ne marche plus
                if adresse:
                        simplified.append([num_departement, commune, siret, denomination, nom, enseigne, adresse, date_creation,tranche_eff])
                #simplified = sorted(simplified, key=itemgetter(0))
        if impression:
            writer = csv.writer(impression)
            writer.writerow(["num_departement", "commune", "siret", "denomination", "nom", "enseigne", "adresse", "date_creation","tranche_eff"])
            for item in simplified:
                writer.writerow(item)
            print("Fichier CSV imprimé !")
        else:
            # On crée une nouvelle liste avec les seuls élèments qu'on souhaite afficher
            for entity in simplified:
                resultat.append(entity[2:])
            table = AsciiTable(header + resultat)
            print(table.table)


@sirene.command("plein_texte")
@click.argument("mot", type=str)
@click.option("-d", "--departement", type=str, default="",
              help="Sélectionne les résultats dans le numéro de département indiqué classé selon ordre alphabétique des villes")
@click.option("-imp", "--impression", type=click.File(mode="w"), default=None,
              help="Imprime la liste des résultats")
def scope_content(mot, departement, impression=None):
    print("Code de NAF de l'INSEE - pour plus d'aide voir la liste : https://entreprise.data.gouv.fr/api-doc/codes_naf")
    url = "https://entreprise.data.gouv.fr/api/sirene/v1/full_text/{}?per_page=100&departement={}".format(mot,
                                                                                                          departement)

    """avec la variable R, on passera une requête GET sur URL qui est le paramètre de la fonction"""
    r = requests.get(url)
    """avec la variable DATA, on récupera la réponse(le body) au format JSON """
    data = r.json()
    if "message" in data:
        print("Oups! Pas de résultat pour cette requête")
    else:
        current_page = int(data["page"])
        next_page = current_page
        total_page = int(data["total_pages"]) + 1
        """création d'une liste vide avec la varialble SIMPLIFIED"""
        header = [["SIRET", "Enseigne", "Adresse", "Date de création entreprise"]]
        simplified = []
        resultat = []
        # Comme on connait le nombre total de pages de résultats, on va faire une boucle pour chaque page
        for i in range(1, total_page):
            url = url + "&page={}".format(i)
            f = requests.get(url)
            """avec la variable DATA, on récupera la réponse(le body) au format JSON """
            dataf = f.json()
            """pour chaque fabricant de bière dans SIRENE"""
            for item in dataf["etablissement"]:
                """définition des éléments qu'on souhaite récupérer pour chaque item"""
                siret = item["siret"]
                denomination = item["nom_raison_sociale"]
                adresse = item["geo_adresse"]
                enseigne = item["enseigne"]
                categoriejur = item["categorie_entreprise"]
                nom = item["l1_normalisee"]
                date_creation = item["date_creation_entreprise"][0:4]
                num_departement = item["departement"]
                commune = item["libelle_commune"]
                lib_act = item["libelle_activite_principale_entreprise"]
                code_act = item["activite_principale_entreprise"]
                """ajout des éléments dans la liste SIMPLIFIED parès nettoyage qualitatif"""
                # si l'adresse n'est pas renseignée, il y a un grand risque que l'affaire ne marche plus
                if adresse:
                    # on ne garde que les PME
                    if categoriejur == "PME":
                        if enseigne:
                            simplified.append([num_departement, commune, siret, enseigne, adresse, date_creation, lib_act, code_act])
                        else:
                            if "*" in denomination:
                                simplified.append([num_departement, commune, siret, nom, adresse, date_creation, lib_act, code_act])
                            else:
                                # lorsqu'il y a une indivision (succession), il y a un grand risque que l'affaire ne marche plus
                                if "INDIVISION" not in denomination:
                                    simplified.append(
                                        [num_departement, commune, siret, denomination, adresse, date_creation, lib_act, code_act])
                    simplified = sorted(simplified, key=itemgetter(0, 1, 5))
        if impression:
            writer = csv.writer(impression)
            writer.writerow(["SIRET", "nom", "adresse", "date de création entreprise"])
            for item in simplified:
                writer.writerow([item[7], item[2], item[4], item[5]])
            print("Fichier CSV imprimé !")
        else:
            # on crée une nouvelle liste avec les seuls élèments qu'on souhaite afficher
            for entity in simplified:
                resultat.append(entity[2:])
            table = AsciiTable(header + resultat)
            print(table.table)


if __name__ == "__main__":
    sirene()

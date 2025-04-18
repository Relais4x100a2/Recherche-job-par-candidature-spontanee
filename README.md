# Recherche Job - Candidatures Spontanées

## Application Streamlit pour la recherche géographique d'entreprises

Cette application web, développée avec Streamlit, permet de rechercher des entreprises situées dans un périmètre géographique défini autour d'une adresse. Elle est conçue pour faciliter la recherche d'employeurs potentiels pour des candidatures spontanées, en filtrant par secteur d'activité (codes NAF) et tranche d'effectifs salariés.

## Fonctionnalités principales

*   **Recherche par localisation :** Définissez une adresse de référence et un rayon de recherche en kilomètres.
*   **Géocodage d'adresse :** Utilise l'API BAN France (via Geopy) pour convertir l'adresse en coordonnées GPS.
*   **Filtrage par activité :** Sélectionnez une ou plusieurs grandes sections d'activité NAF (Agriculture, Industrie, Commerce, etc.).
*   **Filtrage par taille :** Ciblez les entreprises selon leurs tranches d'effectifs salariés (au niveau de l'établissement).
*   **Visualisation des résultats :**
    *   **Tableau détaillé :** Affiche les informations clés des établissements trouvés (SIRET, nom, enseignes, adresse, NAF détaillé, effectifs, date de création, données financières si disponibles).
    *   **Carte interactive :** Représente les entreprises sur une carte (utilisant PyDeck), avec des points colorés par section NAF et dimensionnés par tranche d'effectifs. Une infobulle affiche les détails au survol.
*   **Export des données :** Téléchargez la liste complète des résultats au format CSV (séparateur point-virgule, encodage UTF-8-SIG pour compatibilité Excel) pour une utilisation ultérieure.

*(Il serait utile d'ajouter ici une capture d'écran de l'application)*

## Installation

1.  **Prérequis :** Assurez-vous d'avoir Python 3 (version 3.7 ou supérieure recommandée) et `pip` installés sur votre système.
2.  **Cloner le dépôt :**
    ```bash
    git clone https://github.com/VOTRE_NOM_UTILISATEUR/recherche_job_candidature_spontanée.git
    cd recherche_job_candidature_spontanée
    ```
    *(Remplacez `VOTRE_NOM_UTILISATEUR` par votre nom d'utilisateur GitHub)*
3.  **Installer les dépendances :**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Fichier NAF :** Assurez-vous que le fichier `NAF.csv` (contenant les codes et libellés NAF détaillés) est présent dans le même dossier que `app.py`. Ce fichier est nécessaire au bon fonctionnement de l'application pour afficher les libellés d'activité.

## Utilisation

1.  Placez-vous dans le dossier du projet via votre terminal.
2.  Lancez l'application Streamlit avec la commande :
    ```bash
    streamlit run app.py
    ```
3.  L'application s'ouvrira automatiquement dans votre navigateur web par défaut (généralement à l'adresse `http://localhost:8501`).
4.  Utilisez la barre latérale (sidebar) pour :
    *   Saisir l'adresse de référence pour la recherche.
    *   Ajuster le rayon de recherche en kilomètres.
    *   Affiner les filtres en cliquant sur "Modifier les filtres" pour sélectionner les sections NAF et les tranches d'effectifs souhaitées.
5.  Cliquez sur le bouton "**🚀 Rechercher les Entreprises**" pour lancer la recherche.
6.  Les résultats s'afficheront sous forme de tableau et de carte interactive dans la partie principale de la page.
7.  Utilisez le bouton "**📥 Télécharger en CSV**" en bas des résultats pour exporter les données.

## Dépendances et APIs

*   **Bibliothèques Python principales :**
    *   `streamlit` : Framework pour la création de l'application web.
    *   `requests` : Pour effectuer les appels aux APIs externes.
    *   `pandas` : Pour la manipulation et l'affichage des données tabulaires.
    *   `geopy` : Pour interagir avec les services de géocodage (ici, BAN France).
    *   `pydeck` : Pour la création de la carte interactive basée sur WebGL.
    *(Voir `requirements.txt` pour la liste complète).*
*   **APIs externes utilisées :**
    *   API Recherche d'entreprises : Fournie par l'INSEE et Etalab pour rechercher des entreprises et établissements via divers critères.
    *   API Base Adresse Nationale (BAN) : Utilisée via `geopy` pour convertir les adresses textuelles en coordonnées géographiques précises.


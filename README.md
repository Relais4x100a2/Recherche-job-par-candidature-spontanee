[![Python Tests](https://github.com/Relais4x100a2/Recherche-job-par-candidature-spontanee/actions/workflows/python-tests.yml/badge.svg)](https://github.com/Relais4x100a2/Recherche-job-par-candidature-spontanee/actions/workflows/python-tests.yml)

# Recherche d'Entreprises pour Candidatures Spontanées

Cette application Streamlit permet de rechercher des entreprises dans un rayon géographique donné autour d'une adresse, en filtrant par secteur d'activité (NAF) et tranche d'effectifs. Elle est conçue pour aider à la recherche d'entreprises cibles pour des candidatures spontanées.

## Fonctionnalités


*   **Recherche Géographique :** Localise les entreprises autour d'une adresse de référence dans un rayon spécifié (en km). Utilise l'API [Adresse (BAN)](https://geo.api.gouv.fr/adresse) pour le géocodage initial, puis identifie les codes postaux pertinents dans le rayon pour interroger l'API des entreprises.
*   **Filtrage par Activité (NAF) :**
    *   Sélectionnez des **sections NAF** larges (ex: Industrie, Construction, Information/Communication).
    *   **Affinez optionnellement** en sélectionnant des **codes NAF spécifiques** à l'intérieur des sections choisies. Si aucun code spécifique n'est sélectionné pour une section donnée, tous les codes de cette section seront inclus dans la recherche.
    *   Utilise l'API Recherche d'entreprises et un fichier `NAF.csv` pour les libellés.
*   **Filtrage par Effectifs :** Sélectionnez des tranches d'effectifs simplifiées pour les établissements (ex: "10 à 49 salariés", "250 salariés et plus").
*   **Visualisation des Résultats :**
    *   Tableau détaillé des établissements trouvés (SIRET, nom, adresse, activité, effectifs, etc.).
    *   Liens rapides (ex: vers LinkedIn, Google Maps, Indeed) pour obtenir plus d'informations sur les entreprises listées.
    *   Carte interactive (2D, vue de dessus) affichant les établissements, avec des marqueurs dont la taille représente l'effectif et la couleur représente la section NAF.
    *   Légende pour la carte.
*   **Exports :**
    *   **CSV :** Téléchargez les résultats détaillés dans un fichier CSV (séparateur point-virgule).
    *   **Excel ERM :** Téléchargez un classeur Excel (`.xlsx`) pré-formaté pour le suivi des candidatures, contenant 3 feuilles :
        1.  `Entreprises` : Liste des entreprises/établissements trouvés.
        2.  `Contacts` : Feuille vide pour ajouter manuellement des contacts (avec validation pour lier le SIRET à la feuille `Entreprises`).
        3.  `Actions` : Feuille vide pour suivre les actions (avec validation pour lier le SIRET et l'ID Contact, et listes déroulantes pour Type/Statut).
*   **Gestion du Rate Limiting et des Requêtes API :** Respecte les limites de l'API Recherche d'entreprises, effectue des appels par lots de codes de localisation, et gère les réponses volumineuses pour éviter les erreurs 429 et améliorer la performance.
*   **Structure Modulaire :** Le code est organisé en plusieurs fichiers Python pour une meilleure lisibilité et maintenabilité.

## Installation

1.  **Prérequis :** Assurez-vous d'avoir Python 3 (idéalement 3.9+) et `pip` installés.
2.  **Cloner le dépôt :**
    ```bash
    git clone https://github.com/Relais4x100a2/Recherche-job-par-candidature-spontanee.git
    cd Recherche-job-par-candidature-spontanee
    ```
3.  **(Recommandé) Créer un environnement virtuel :**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Sur Linux/macOS
    # ou
    # .\venv\Scripts\activate  # Sur Windows
    ```
4.  **Installer les dépendances :**
    ```bash
    pip install -r requirements.txt
    ```
5.  **Fichier NAF :** Assurez-vous que le fichier `NAF.csv` (contenant les codes et libellés NAF) est présent à la racine du projet (`Recherche-job-par-candidature-spontanee/NAF.csv`).

## Utilisation

1.  Naviguez dans le terminal jusqu'au dossier du projet (`Recherche-job-par-candidature-spontanee`).
2.  Si vous utilisez un environnement virtuel, activez-le (voir étape d'installation).
3.  Lancez l'application Streamlit :
    ```bash
    streamlit run app.py
    ```
4.  L'application devrait s'ouvrir automatiquement dans votre navigateur web.
5.  Utilisez la barre latérale pour entrer l'adresse, le rayon, et sélectionner les filtres NAF et d'effectifs.
6.  Cliquez sur le bouton "🚀 Rechercher les Entreprises".
7.  Consultez les résultats (tableau, carte) et utilisez les boutons de téléchargement si besoin.

## Structure du Projet

```
Recherche-job-par-candidature-spontanee/ 
├── app.py # Point d'entrée principal de l'application Streamlit, gère l'UI et l'orchestration ├── config.py # Constantes (limites API, chemins), dictionnaires (NAF, effectifs, couleurs, colonnes ERM) 
├── data_utils.py # Fonctions pour charger/traiter NAF.csv, traiter la réponse API, générer l'Excel ERM 
├── api_client.py # Fonctions pour interagir avec l'API Recherche d'entreprises : effectue les recherches par lots de codes de localisation (codes postaux ou INSEE), gère la limitation de débit (rate limiting), traite les réponses volumineuses et déduplique les entreprises trouvées par SIREN. 
├── geo_utils.py # Fonctions pour le géocodage de l'adresse de référence (via API BAN) et la détermination des codes postaux des communes situées dans le rayon de recherche spécifié (utilise un cache local des données communales via communes_cache.json). 
├── NAF.csv # Fichier de données des codes NAF 
├── requirements.txt # Dépendances Python du projet 
└── README.md # Ce fichier
```

## Sources de Données

*   **API Recherche d'entreprises :** `https://recherche-entreprises.api.gouv.fr/search`
*   **API Adresse (BAN) :** `https://geo.api.gouv.fr/adresse` (utilisée via `geopy` pour le géocodage initial)
*   **API Géo - Communes :** `https://geo.api.gouv.fr/communes` (utilisée par `geo_utils.py` pour construire un cache local des communes)
*   **Fichier `NAF.csv` :** Fichier local contenant la nomenclature d'activités française.
*   **Fichier `communes_cache.json` :** Cache local des données des communes françaises, généré par `geo_utils.py`.


## Configuration

Les paramètres principaux comme les limites de l'API, les chemins de fichiers, et les dictionnaires de mapping (NAF, effectifs, couleurs) sont définis dans `config.py`.

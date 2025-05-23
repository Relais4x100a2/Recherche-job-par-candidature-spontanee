# Recherche d'Entreprises pour Candidatures Spontanées

Cette application Streamlit permet de rechercher des entreprises dans un rayon géographique donné autour d'une adresse, en filtrant par secteur d'activité (NAF) et tranche d'effectifs. Elle est conçue pour aider à la recherche d'entreprises cibles pour des candidatures spontanées.

## Fonctionnalités

*   **Recherche Géographique :** Localise les entreprises autour d'une adresse de référence dans un rayon spécifié (en km). Utilise l'API [Adresse (BAN)](https://geo.api.gouv.fr/adresse) via `geopy`.
*   **Filtrage par Activité (NAF) :**
    *   Sélectionnez des **sections NAF** larges (ex: Industrie, Construction, Information/Communication).
    *   **Affinez optionnellement** en sélectionnant des **codes NAF spécifiques** à l'intérieur des sections choisies. Si aucun code spécifique n'est sélectionné pour une section donnée, tous les codes de cette section seront inclus dans la recherche.
    *   Utilise l'API Recherche d'entreprises et un fichier `NAF.csv` pour les libellés.
*   **Filtrage par Effectifs :** Sélectionnez des tranches d'effectifs simplifiées pour les établissements (ex: "10 à 49 salariés", "250 salariés et plus").
*   **Visualisation des Résultats :**
    *   Tableau détaillé des établissements trouvés (SIRET, nom, adresse, activité, effectifs, etc.).
    *   Carte interactive (2D, vue de dessus) affichant les établissements, avec des marqueurs dont la taille représente l'effectif et la couleur représente la section NAF.
    *   Légende pour la carte.
*   **Exports :**
    *   **CSV :** Téléchargez les résultats détaillés dans un fichier CSV (séparateur point-virgule).
    *   **Excel CRM :** Téléchargez un classeur Excel (`.xlsx`) pré-formaté pour le suivi des candidatures, contenant 3 feuilles :
        1.  `Entreprises` : Liste des entreprises/établissements trouvés.
        2.  `Contacts` : Feuille vide pour ajouter manuellement des contacts (avec validation pour lier le SIRET à la feuille `Entreprises`).
        3.  `Actions` : Feuille vide pour suivre les actions (avec validation pour lier le SIRET et l'ID Contact, et listes déroulantes pour Type/Statut).
*   **Gestion du Rate Limiting :** Respecte les limites de l'API Recherche d'entreprises pour éviter les erreurs 429.
*   **Structure Modulaire :** Le code est organisé en plusieurs fichiers Python pour une meilleure lisibilité et maintenabilité.

## Installation

1.  **Prérequis :** Assurez-vous d'avoir Python 3 (idéalement 3.9+) et `pip` installés.
2.  **Cloner le dépôt :**
    ```bash
    git clone <url_de_votre_depot>
    cd recherche_job_candidature_spontanée
    ```
3.  **(Recommandé) Créer un environnement virtuel :**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Sur Linux/macOS
    # ou
    .\venv\Scripts\activate  # Sur Windows
    ```
4.  **Installer les dépendances :**
    ```bash
    pip install -r requirements.txt
    ```
5.  **Fichier NAF :** Assurez-vous que le fichier `NAF.csv` (contenant les codes et libellés NAF) est présent à la racine du projet (`recherche_job_candidature_spontanée/NAF.csv`).

## Utilisation

1.  Naviguez dans le terminal jusqu'au dossier du projet (`recherche_job_candidature_spontanée`).
2.  Lancez l'application Streamlit :
    ```bash
    streamlit run app.py
    ```
3.  L'application devrait s'ouvrir automatiquement dans votre navigateur web.
4.  Utilisez la barre latérale pour entrer l'adresse, le rayon, et sélectionner les filtres NAF et d'effectifs.
5.  Cliquez sur le bouton "🚀 Rechercher les Entreprises".
6.  Consultez les résultats (tableau, carte) et utilisez les boutons de téléchargement si besoin.

## Structure du Projet

```
recherche_job_candidature_spontanée/
├── app.py                 # Point d'entrée principal de l'application Streamlit, gère l'UI et l'orchestration
├── config.py              # Constantes (limites API, chemins), dictionnaires (NAF, effectifs, couleurs)
├── data_utils.py          # Fonctions pour charger/traiter NAF.csv, traiter la réponse API, générer l'Excel CRM
├── api_client.py          # Fonctions pour interagir avec l'API Recherche d'entreprises (appels, rate limiting)
├── geo_utils.py           # Fonction pour le géocodage via l'API Adresse (BAN)
├── NAF.csv                # Fichier de données des codes NAF
├── requirements.txt       # Dépendances Python du projet
└── .gitignore             # Fichiers/dossiers ignorés par Git (ex: venv, __pycache__)
```


## Sources de Données

*   **API Recherche d'entreprises :** `https://recherche-entreprises.api.gouv.fr`
*   **API Adresse (BAN) :** `https://geo.api.gouv.fr/adresse` (utilisée via `geopy`)
*   **Fichier `NAF.csv` :** Fichier local contenant la nomenclature d'activités française.

## Configuration

Les paramètres principaux comme les limites de l'API, les chemins de fichiers, et les dictionnaires de mapping (NAF, effectifs, couleurs) sont définis dans `config.py`.

import pandas as pd

# --- Constantes API & Rate Limiting ---
# Defines parameters for interacting with external APIs, focusing on rate limiting.
MAX_REQUESTS_PER_SECOND = 6
MIN_DELAY_BETWEEN_REQUESTS = (1.0 / MAX_REQUESTS_PER_SECOND) + 0.02
MAX_RETRIES_ON_429 = 3
INITIAL_RETRY_DELAY = 5
API_BASE_URL = "https://recherche-entreprises.api.gouv.fr"
API_MAX_TOTAL_RESULTS = 10000 # Documented limit for the API
API_RESULTS_PER_PAGE = 25 # Standard per_page value used
API_MAX_PAGES = API_MAX_TOTAL_RESULTS // API_RESULTS_PER_PAGE



# --- File Paths ---
# Defines paths for data files used by the application.
DEFAULT_ERM_FILE_PATH = "erm_data.json"
NAF_FILE_PATH = "NAF.csv"

# --- ERM (Enterprise Relationship Management) DataFrame Column Definitions ---
# Specifies the column structure for DataFrames used to store ERM data.
ENTREPRISES_ERM_COLS = [
    "SIRET",
    "Dénomination - Enseigne",
    "Activité NAF/APE Etablissement",
    "Adresse établissement",
    "Commune",
    "Code effectif établissement",
    "Nb salariés établissement",
    "Effectif Numérique",
    "Est siège social",
    "Date de création Entreprise",
    "Chiffre d'Affaires Entreprise",
    "Résultat Net Entreprise",
    "Année Finances Entreprise",
    "Notes Personnelles",  # User-editable notes for an enterprise.
    "Statut Piste",        # User-editable status for an enterprise lead.
]

ENTREPRISES_ERM_DTYPES = {
    "SIRET": pd.StringDtype(),
    "Dénomination - Enseigne": pd.StringDtype(),
    "Activité NAF/APE Etablissement": pd.StringDtype(),
    "Adresse établissement": pd.StringDtype(),
    "Commune": pd.StringDtype(),
    "Code effectif établissement": pd.StringDtype(),
    "Nb salariés établissement": pd.StringDtype(),
    "Effectif Numérique": pd.Int64Dtype(),
    "Est siège social": pd.BooleanDtype(),
    "Date de création Entreprise": "datetime64[ns]",
    "Chiffre d'Affaires Entreprise": pd.Float64Dtype(),
    "Résultat Net Entreprise": pd.Float64Dtype(),
    "Année Finances Entreprise": pd.StringDtype(),
    "Notes Personnelles": pd.StringDtype(),
    "Statut Piste": pd.StringDtype(),
}


CONTACTS_ERM_COLS = [
    "ID Contact", # Unique identifier for a contact.
    "SIRET Entreprise", 
    "Prénom Nom",
    "Poste",
    "Direction",
    "Email",
    "Téléphone",
    "Profil LinkedIn URL",
    "Notes"
]

ACTIONS_ERM_COLS = [
    "ID Action", # Unique identifier for an action.
    "SIRET Entreprise", 
    "ID Contact", # Link to a specific contact, if applicable.
    "Type Action",
    "Date Action",
    "Date Échéance",
    "Description/Notes",
    "Statut Action",
]

# --- NAF Code to Section Mapping ---
# Maps the first two digits of a NAF code to its corresponding section letter.
NAF_SECTION_MAP = {
    "01": "A",
    "02": "A",
    "03": "A",
    "05": "B",
    "06": "B",
    "07": "B",
    "08": "B",
    "09": "B",
    "10": "C",
    "11": "C",
    "12": "C",
    "13": "C",
    "14": "C",
    "15": "C",
    "16": "C",
    "17": "C",
    "18": "C",
    "19": "C",
    "20": "C",
    "21": "C",
    "22": "C",
    "23": "C",
    "24": "C",
    "25": "C",
    "26": "C",
    "27": "C",
    "28": "C",
    "29": "C",
    "30": "C",
    "31": "C",
    "32": "C",
    "33": "C",
    "35": "D",
    "36": "E",
    "37": "E",
    "38": "E",
    "39": "E",
    "41": "F",
    "42": "F",
    "43": "F",
    "45": "G",
    "46": "G",
    "47": "G",
    "49": "H",
    "50": "H",
    "51": "H",
    "52": "H",
    "53": "H",
    "55": "I",
    "56": "I",
    "58": "J",
    "59": "J",
    "60": "J",
    "61": "J",
    "62": "J",
    "63": "J",
    "64": "K",
    "65": "K",
    "66": "K",
    "68": "L",
    "69": "M",
    "70": "M",
    "71": "M",
    "72": "M",
    "73": "M",
    "74": "M",
    "75": "M",
    "77": "N",
    "78": "N",
    "79": "N",
    "80": "N",
    "81": "N",
    "82": "N",
    "84": "O",
    "85": "P",
    "86": "Q",
    "87": "Q",
    "88": "Q",
    "90": "R",
    "91": "R",
    "92": "R",
    "93": "R",
    "94": "S",
    "95": "S",
    "96": "S",
    "97": "T",
    "98": "T",
    "99": "U",
}

# --- Workforce Size (Effectifs) Dictionaries ---
# Provides descriptions for workforce size codes.
effectifs_tranches = {
    "NN": "Non employeuse",
    "00": "0 salarié",
    "01": "1 ou 2 salariés",
    "02": "3 à 5 salariés",
    "03": "6 à 9 salariés",
    "11": "10 à 19 salariés",
    "12": "20 à 49 salariés",
    "21": "50 à 99 salariés",
    "22": "100 à 199 salariés",
    "31": "200 à 249 salariés",
    "32": "250 à 499 salariés",
    "41": "500 à 999 salariés",
    "42": "1 000 à 1 999 salariés",
    "51": "2 000 à 4 999 salariés",
    "52": "5 000 à 9 999 salariés",
    "53": "10 000 salariés et plus",
}

# Maps workforce size codes to a numerical value for sorting or quantitative analysis.
effectifs_numerical_mapping = {
    "NN": 0, # Non employeuse
    "00": 0, # 0 salarié
    "01": 1, # 1 ou 2 salariés
    "02": 3, # 3 à 5 salariés
    "03": 6, # 6 à 9 salariés
    "11": 10, # 10 à 19 salariés
    "12": 20, # 20 à 49 salariés
    "21": 50, # 50 à 99 salariés
    "22": 100, # 100 à 199 salariés
    "31": 200, # 200 à 249 salariés
    "32": 250, # 250 à 499 salariés
    "41": 500, # 500 à 999 salariés
    "42": 1000, # 1 000 à 1 999 salariés
    "51": 2000, # 2 000 à 4 999 salariés
    "52": 5000, # 5 000 à 9 999 salariés
    "53": 10000, # 10 000 salariés et plus
}

# Maps numerical workforce values to an alphabetical prefix for display purposes (e.g., sorting in tables).
effectif_numeric_to_letter_prefix = {
    # La valeur 0 (pour "NN" et "00") n'est pas incluse ici, 
    # donc ces tranches n'auront pas de préfixe alphabétique par défaut.
    1: "a",    # Corresponds à "01" (1 ou 2 salariés)
    3: "b",    # Corresponds à "02" (3 à 5 salariés)
    6: "c",    # Corresponds à "03" (6 à 9 salariés)
    10: "d",   # Corresponds à "11" (10 à 19 salariés)
    20: "e",   # Corresponds à "12" (20 à 49 salariés)
    50: "f",   # Corresponds à "21" (50 à 99 salariés)
    100: "g",  # Corresponds à "22" (100 à 199 salariés)
    200: "h",  # Corresponds à "31" (200 à 249 salariés)
    250: "i",  # Corresponds à "32" (250 à 499 salariés)
    500: "j",  # Corresponds à "41" (500 à 999 salariés)
    1000: "k", # Corresponds à "42" (1 000 à 1 999 salariés)
    2000: "l", # Corresponds à "51" (2 000 à 4 999 salariés)
    5000: "m", # Corresponds à "52" (5 000 à 9 999 salariés)
    10000: "n" # Corresponds à "53" (10 000 salariés et plus)
}

# --- NAF Section Details ---
# Provides descriptions and icons for NAF sections, used in UI elements.
naf_sections_details = {
    "A": {"description": "Agriculture, sylviculture et pêche", "icon": "🚜"},
    "B": {"description": "Industries extractives", "icon": "⛏️"},
    "C": {"description": "Industrie manufacturière", "icon": "🏭"},
    "D": {"description": "Electricité, gaz, vapeur et air conditionné ", "icon": "💡"},
    "E": {
        "description": "Eau, assainissement, gestion déchets, dépollution",
        "icon": "💧",
    },
    "F": {"description": "Construction", "icon": "🏗️"},
    "G": {"description": "Commerce ; réparation auto / moto", "icon": "🛒"},
    "H": {"description": "Transports et entreposage", "icon": "🚚"},
    "I": {"description": "Hébergement et restauration", "icon": "🏨"},
    "J": {"description": "Information et communication", "icon": "💻"},
    "K": {"description": "Activités financières et d'assurance", "icon": "💰"},
    "L": {"description": "Activités immobilières", "icon": "🏘️"},
    "M": {
        "description": "Activités spécialisées, scientifiques et techniques",
        "icon": "🔬",
    },
    "N": {"description": "Services administratifs et de soutien", "icon": "👥"},
    # "O": {"description": "Administration publique", "icon": "🏛️"},
    "P": {"description": "Enseignement", "icon": "🎓"},
    "Q": {"description": "Santé humaine et action sociale", "icon": "❤️"},
    "R": {"description": "Arts, spectacles et activités récréatives", "icon": "🎭"},
    "S": {"description": "Autres activités de services", "icon": "🛠️"},
    # "T": {"description": "Activités des ménages (employeurs ou producteurs de biens et services pour usage propre", "icon": "🏠"},
    # "U": {"description": "Activités extra-territoriales", "icon": "🌍"} #
}

# --- Workforce Size Groupings (Legacy or Alternative) ---
effectifs_groupes = {
    "0 salarié": ["00"],
    "1 à 9 salariés": ["01", "02", "03"],
    "10 à 49 salariés": ["11", "12"],
    "50 à 249 salariés": ["21", "22"],
    "250 salariés et plus": ["31", "32", "41", "42", "51", "52", "53"],
    "Unités non-employeuses": ["NN"],
}

# --- Detailed Workforce Size Groupings for UI ---
# Defines groups of workforce size codes with labels and icons for UI selection.
effectifs_groupes_details = {
    "INDIV": {
        "label": "0 salarié (entreprise individuelle)",
        "codes": ["00"],
        "icon": "👤",
    },
    "TPE": {"label": "1-9 salariés (TPE)", "codes": ["01", "02", "03"], "icon": "👥"},
    "PME_S": {
        "label": "10-49 salariés (PME)",
        "codes": ["11", "12"],
        "icon": "👨‍👩‍👧‍👦",
    },
    "PME_M": {
        "label": "50-249 salariés (PME/ETI)",
        "codes": ["21", "22"],
        "icon": "🏢",
    },
    "GE": {
        "label": "250+ salariés (Grande Ent.)",
        "codes": ["31", "32", "41", "42", "51", "52", "53"],
        "icon": "🏙️",
    },
    "NN": {"label": "Unités non-employeuses", "codes": ["NN"], "icon": "❓"},
}


# --- Pydeck Map Visualization Mappings ---
# Defines color and radius mappings for visualizing NAF sections and workforce sizes on a map.
naf_color_mapping = {
    "A": [210, 4, 45],
    "B": [139, 69, 19],
    "C": [255, 140, 0],
    "D": [255, 215, 0],
    "E": [173, 255, 47],
    "F": [255, 105, 180],
    "G": [0, 191, 255],
    "H": [70, 130, 180],
    "I": [255, 0, 0],
    "J": [128, 0, 128],
    "K": [0, 128, 0],
    "L": [160, 82, 45],
    "M": [0, 0, 128],
    "N": [128, 128, 128],
    "O": [0, 0, 0],
    "P": [255, 255, 0],
    "Q": [0, 255, 0],
    "R": [255, 20, 147],
    "S": [192, 192, 192],
    "T": [245, 245, 220],
    "U": [112, 128, 144],
    "N/A": [220, 220, 220],
}

size_mapping = {
    "NN": 15,
    "00": 20,
    "01": 30,
    "02": 40,
    "03": 50,
    "11": 70,
    "12": 90,
    "21": 120,
    "22": 150,
    "31": 180,
    "32": 220,
    "41": 260,
    "42": 300,
    "51": 350,
    "52": 400,
    "53": 450,
    "N/A": 10,
}

# --- Column Definitions for Display and Export ---
# Specifies the order and selection of columns for table displays and Excel exports.
COLS_DISPLAY_TABLE = [
    "SIRET",
    "Dénomination - Enseigne",
    "Est siège social",
    "Adresse établissement",
    "Commune",
    "Activité NAF/APE Etablissement",
    "Activité NAF/APE Entreprise",
    "Nb salariés établissement",
    "Année nb salariés établissement",
    "Date de création Entreprise",
    "Chiffre d'Affaires Entreprise",
    "Résultat Net Entreprise",
    "Année Finances Entreprise",
]

COLS_EXPORT_ORDER = [
    "SIRET",
    "Dénomination - Enseigne",
    "Activité NAF/APE Etablissement",
    "code_naf_etablissement",
    "Activité NAF/APE Entreprise",
    "code_naf_entreprise",
    "Est siège social",
    "Adresse établissement",
    "Commune",
    "Nb salariés établissement",
    "Année nb salariés établissement",
    "Code effectif établissement",
    "Effectif Numérique", # Added for sorting
    "Raison sociale",
    "Date de création Entreprise", # Note: This is company creation date, not establishment.
    "Nb total établissements ouverts",
    "Nb salariés entreprise",
    "Année Finances Entreprise",
    "Chiffre d'Affaires Entreprise",
    "Résultat Net Entreprise",
    "Latitude",
    "Longitude",
    "Section NAF",  # Section NAF est basé sur code_naf_etablissement
    "Color",
    "Radius",
]

# --- Dropdown List Values for ERM ---
# Defines static lists used to populate dropdown menus in the ERM interface (e.g., for Excel data validation).
VALEURS_LISTE_CONTACTS_DIRECTION = [
    "Dir. Achats",
    "Dir. Commerciale",
    "Dir. Communication",
    "Dir. Financière / Admin&Fin",
    "Dir. Générale",
    "Dir. Juridique",
    "Dir. Marketing",
    "Dir. Production",
    "Dir. R&D",
    "Dir. RH",
]

VALEURS_LISTE_ACTIONS_TYPEACTION = [
    "Mise en relation",
    "Prise de contact",
    "Visite de l'entreprise",
    "Échange par e-mail",
    "Envoi de CV et lettre de motivation",
    "Entretien téléphonique",
    "Test de compétences",
    "Entretien physique",
    "Relance",
]

VALEURS_LISTE_ACTIONS_STATUTACTION = [
    "A faire",
    "En attente",
    "En cours",
    "Terminé",
    "Annulé",
]

VALEURS_LISTE_ACTIONS_STATUTOPPORTUNITE = [
    "Ciblée",
    "En veille",
    "Postulée",
    "Abandonnée",
    "Refusée",
    "Offre reçue",
    "Acceptée",
]

VALEURS_LISTE_ENTREPRISE_STATUTPISTE = [
    "À contacter",
    "Contacté",
    "En discussion",
    "Proposition envoyée",
    "Stand-by",
    "Non intéressé",
    "Contrat signé",
]

# --- Constantes API & Rate Limiting ---
MAX_REQUESTS_PER_SECOND = 6
MIN_DELAY_BETWEEN_REQUESTS = (1.0 / MAX_REQUESTS_PER_SECOND) + 0.02
MAX_RETRIES_ON_429 = 3
INITIAL_RETRY_DELAY = 5
API_BASE_URL = "https://recherche-entreprises.api.gouv.fr"

# --- Fichiers ---
NAF_FILE_PATH = 'NAF.csv'

# --- Dictionnaires NAF ---
naf_sections = {
    "A": "A - Agriculture, sylviculture et pêche", "B": "B - Industries extractives", "C": "C - Industrie manufacturière",
    "D": "D - Production et distribution d'électricité, gaz, vapeur/eau chaude, air conditionné ", "E": "E - Production et distribution d'eau ; assainissement, gestion des déchets et dépollution",
    "F": "F - Construction", "G": "G - Commerce de gros et de détail ; réparation d'automobiles et de motocycles", "H": "H - Transports et entreposage",
    "I": "I - Hébergement et restauration", "J": "J - Information et communication", "K": "K - Activités financières et d'assurance",
    "L": "L - Activités immobilières", "M": "M - Activités spécialisées, scientifiques et techniques",
    "N": "N - Activités de services administratifs et de soutien aux activités générales des entreprises",
    "Q": "Q - Santé humaine et action sociale", "R": "R - Arts, spectacles et activités récréatives"
    # Note: Sections O, P, S, T, U existent mais sont moins courantes pour ces recherches
}

NAF_SECTION_MAP = {'01': 'A', '02': 'A', '03': 'A', '05': 'B', '06': 'B', '07': 'B', '08': 'B', '09': 'B', '10': 'C', '11': 'C', '12': 'C', '13': 'C', '14': 'C', '15': 'C', '16': 'C', '17': 'C', '18': 'C', '19': 'C', '20': 'C', '21': 'C', '22': 'C', '23': 'C', '24': 'C', '25': 'C', '26': 'C', '27': 'C', '28': 'C', '29': 'C', '30': 'C', '31': 'C', '32': 'C', '33': 'C', '35': 'D', '36': 'E', '37': 'E', '38': 'E', '39': 'E', '41': 'F', '42': 'F', '43': 'F', '45': 'G', '46': 'G', '47': 'G', '49': 'H', '50': 'H', '51': 'H', '52': 'H', '53': 'H', '55': 'I', '56': 'I', '58': 'J', '59': 'J', '60': 'J', '61': 'J', '62': 'J', '63': 'J', '64': 'K', '65': 'K', '66': 'K', '68': 'L', '69': 'M', '70': 'M', '71': 'M', '72': 'M', '73': 'M', '74': 'M', '75': 'M', '77': 'N', '78': 'N', '79': 'N', '80': 'N', '81': 'N', '82': 'N', '84': 'O', '85': 'P', '86': 'Q', '87': 'Q', '88': 'Q', '90': 'R', '91': 'R', '92': 'R', '93': 'R', '94': 'S', '95': 'S', '96': 'S', '97': 'T', '98': 'T', '99': 'U'}

# --- Dictionnaires Effectifs ---
effectifs_tranches = {
    "NN": "Non employeuse", "00": "0 salarié", "01": "1 ou 2 salariés", "02": "3 à 5 salariés",
    "03": "6 à 9 salariés", "11": "10 à 19 salariés", "12": "20 à 49 salariés", "21": "50 à 99 salariés",
    "22": "100 à 199 salariés", "31": "200 à 249 salariés", "32": "250 à 499 salariés",
    "41": "500 à 999 salariés", "42": "1 000 à 1 999 salariés", "51": "2 000 à 4 999 salariés",
    "52": "5 000 à 9 999 salariés", "53": "10 000 salariés et plus"
}

effectifs_groupes = {
    "Jusqu'à 2 salariés": ["NN", "00", "01"],
    "De 3 à 9 salariés": ["02", "03"],
    "De 10 à 49 salariés": ["11", "12"],
    "De 50 à 249 salariés": ["21", "22", "31"],
    "250 salariés et plus": ["32", "41", "42", "51", "52", "53"]
}

# --- Mappings pour Pydeck ---
naf_color_mapping = {
    "A": [210, 4, 45], "B": [139, 69, 19], "C": [255, 140, 0], "D": [255, 215, 0],
    "E": [173, 255, 47], "F": [255, 105, 180], "G": [0, 191, 255], "H": [70, 130, 180],
    "I": [255, 0, 0], "J": [128, 0, 128], "K": [0, 128, 0], "L": [160, 82, 45],
    "M": [0, 0, 128], "N": [128, 128, 128], "O": [0, 0, 0], "P": [255, 255, 0],
    "Q": [0, 255, 0], "R": [255, 20, 147], "S": [192, 192, 192], "T": [245, 245, 220],
    "U": [112, 128, 144], "N/A": [220, 220, 220]
}

size_mapping = {
    "NN": 15, "00": 20, "01": 30, "02": 40, "03": 50, "11": 70, "12": 90,
    "21": 120, "22": 150, "31": 180, "32": 220, "41": 260, "42": 300,
    "51": 350, "52": 400, "53": 450, "N/A": 10
}

# --- Colonnes pour l'affichage et l'export ---
COLS_DISPLAY_TABLE = [
    'SIRET', 'Nom complet', 'Enseignes', 'Est siège social', 'Adresse établissement',
    'Activité NAF/APE', 'Nb salariés établissement', 'Année nb salariés établissement',
    'Date de création', 'Chiffre d\'Affaires', 'Résultat Net', 'Année Finances'
]

COLS_EXPORT_ORDER = [
    'SIRET', 'Nom complet', 'Enseignes', 'Activité NAF/APE', 'Code NAF', 'Est siège social', 'Adresse établissement',
    'Nb salariés établissement', 'Année nb salariés établissement', 'Code effectif établissement',
    'SIREN', 'Raison sociale', 'Date de création', 'Nb total établissements ouverts',
    'Nb salariés entreprise', 'Année Finances', 'Chiffre d\'Affaires', 'Résultat Net',
    'Latitude', 'Longitude', 'Section NAF', 'Color', 'Radius'
]

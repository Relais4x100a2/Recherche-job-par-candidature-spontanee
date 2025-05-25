import bcrypt
import json
import os

# Directory for user-specific CRM data
USER_DATA_DIR = "user_data"

def hash_password(password: str) -> str:
    """Hashes a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain text password against a stored bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_users() -> list:
    """Reads users from users.json."""
    try:
        with open("users.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def verify_user(username, password) -> bool:
    """Verifies user credentials."""
    users = get_users()
    for user in users:
        if user["username"] == username and verify_password(password, user["hashed_password"]):
            return True
    return False

# --- CRM Data Management Functions ---

def get_user_crm_filepath(username: str) -> str:
    """Returns the path to the user's CRM data file."""
    # Ensure the user_data directory exists
    if not os.path.exists(USER_DATA_DIR):
        os.makedirs(USER_DATA_DIR)
    return os.path.join(USER_DATA_DIR, f"{username}_crm.json")

def load_user_crm_data(username: str) -> dict:
    """Loads CRM data for a user. Returns default structure if file not found."""
    filepath = get_user_crm_filepath(username)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure all main keys are present
                data.setdefault('entreprises', [])
                data.setdefault('contacts', [])
                data.setdefault('actions', [])
                return data
        except (json.JSONDecodeError, IOError) as e:
            # Log error or handle appropriately
            print(f"Error loading CRM data for {username}: {e}")
            # Fallback to default structure
    return {
        "entreprises": [],
        "contacts": [],
        "actions": []
    }

def save_user_crm_data(username: str, data: dict):
    """Saves CRM data for a user."""
    filepath = get_user_crm_filepath(username)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        # Log error or handle appropriately
        print(f"Error saving CRM data for {username}: {e}")

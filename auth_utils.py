import datetime
import json
import os

import streamlit as st

# Directory for user-specific ERM data
USER_DATA_DIR = "user_data"


def verify_password(plain_password: str, stored_plain_password: str) -> bool:
    """Verifies a plain text password against a stored plain text password."""
    print(
        f"{datetime.datetime.now()} - INFO - Comparing provided password with stored password."
    )
    # In a real scenario, avoid logging the passwords themselves.
    result = plain_password == stored_plain_password
    print(f"{datetime.datetime.now()} - INFO - Password verification result: {result}")
    return result


def get_users() -> list:
    """Reads users from users.json."""
    print(f"{datetime.datetime.now()} - INFO - get_users function called.")
    try:
        with open("users.json", "r") as f:
            users = json.load(f)
            print(
                f"{datetime.datetime.now()} - INFO - users.json found and loaded. Number of users: {len(users)}."
            )
            return users
    except FileNotFoundError:
        print(f"{datetime.datetime.now()} - WARNING - users.json not found.")
        return []


def verify_user(username, password) -> bool:
    """Verifies user credentials by comparing plain text passwords."""
    print(f"{datetime.datetime.now()} - INFO - Verifying user: {username}.")
    users = get_users()
    user_found = False
    for user in users:
        if user["username"] == username:
            user_found = True
            print(
                f"{datetime.datetime.now()} - INFO - User '{username}' found. Verifying password."
            )
            if verify_password(password, user.get("password", "")):
                print(
                    f"{datetime.datetime.now()} - INFO - Password verification successful for user '{username}'."
                )
                return True
            else:
                print(
                    f"{datetime.datetime.now()} - WARNING - Password verification failed for user '{username}'."
                )
                return False
    if not user_found:
        print(f"{datetime.datetime.now()} - WARNING - User '{username}' not found.")
    return False


# --- ERM Data Management Functions ---


def get_user_erm_filepath(username: str) -> str:
    """Returns the path to the user's ERM data file."""
    # Ensure the user_data directory exists
    if not os.path.exists(USER_DATA_DIR):
        print(
            f"{datetime.datetime.now()} - INFO - USER_DATA_DIR ('{USER_DATA_DIR}') does not exist. Creating it."
        )
        os.makedirs(USER_DATA_DIR)
    filepath = os.path.join(USER_DATA_DIR, f"{username}_erm.json")
    print(
        f"{datetime.datetime.now()} - INFO - Generated ERM filepath for user '{username}': {filepath}"
    )
    return filepath


def load_user_erm_data(username: str) -> dict:
    """Loads ERM data for a user. Returns default structure if file not found."""
    print(f"{datetime.datetime.now()} - INFO - Loading ERM data for user: {username}.")
    filepath = get_user_erm_filepath(username)
    print(f"{datetime.datetime.now()} - INFO - Accessing ERM data file: {filepath}")
    if os.path.exists(filepath):
        print(
            f"{datetime.datetime.now()} - INFO - ERM data file exists for user '{username}'."
        )
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure all main keys are present
                data.setdefault("entreprises", [])
                data.setdefault("contacts", [])
                data.setdefault("actions", [])
                num_entreprises = len(data.get("entreprises", []))
                num_contacts = len(data.get("contacts", []))
                num_actions = len(data.get("actions", []))
                print(
                    f"{datetime.datetime.now()} - INFO - ERM data loaded successfully for '{username}'. Entreprises: {num_entreprises}, Contacts: {num_contacts}, Actions: {num_actions}."
                )
                return data
        except (json.JSONDecodeError, IOError) as e:
            print(
                f"{datetime.datetime.now()} - ERROR - Error loading ERM data for '{username}' from {filepath}: {e}"
            )
            # Fallback to default structure
    else:
        print(
            f"{datetime.datetime.now()} - WARNING - ERM data file not found for user '{username}' at {filepath}. Returning default structure."
        )
    return {"entreprises": [], "contacts": [], "actions": []}


def save_user_erm_data(username: str, data: dict):
    """Saves ERM data for a user."""
    print(f"{datetime.datetime.now()} - INFO - Saving ERM data for user: {username}.")
    filepath = get_user_erm_filepath(username)
    print(f"{datetime.datetime.now()} - INFO - Writing ERM data to file: {filepath}")
    num_entreprises = len(data.get("entreprises", []))
    num_contacts = len(data.get("contacts", []))
    num_actions = len(data.get("actions", []))
    print(
        f"{datetime.datetime.now()} - INFO - Data to save for '{username}': Entreprises: {num_entreprises}, Contacts: {num_contacts}, Actions: {num_actions}."
    )
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(
            f"{datetime.datetime.now()} - INFO - ERM data saved successfully for '{username}' to {filepath}."
        )
    except IOError as e:
        print(
            f"{datetime.datetime.now()} - ERROR - Error saving ERM data for '{username}' to {filepath}: {e}"
        )
        st.error(f"Failed to save ERM data to {filepath}. Error: {e}")

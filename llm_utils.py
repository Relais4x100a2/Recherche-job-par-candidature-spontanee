import json
import os
from openai import OpenAI
import streamlit as st
from pydantic import BaseModel, ValidationError
from typing import List, Optional

# --- CONFIGURATION ---
# Attempt to get API key from Streamlit secrets first, then environment variables
OPENROUTER_API_KEY = None
if hasattr(st, 'secrets') and "OPENROUTER_API_KEY" in st.secrets:
    OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
else:
    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Replace with your actual site URL and name, or make them configurable
HTTP_REFERER = os.environ.get("LLM_HTTP_REFERER", "https://your-streamlit-app-url.com")
X_TITLE = os.environ.get("LLM_X_TITLE", "Streamlit Job Search App")
LLM_MODEL = "google/gemma-3-27b-it:free" # Or your preferred model

# --- PYDANTIC MODEL FOR LLM RESPONSE ---
class LLMSuggestionOutput(BaseModel):
    naf_sections: Optional[List[str]] = []
    naf_specific_codes: Optional[List[str]] = []
    effectifs_codes: Optional[List[str]] = []


def get_llm_suggestions(
    user_text_prompt: str,
    naf_sections_config: dict,
    effectifs_groupes_config: dict,
    all_specific_naf_codes: list = None,
    naf_detailed_lookup_for_libelles: dict = None,
    effectifs_tranches_map_for_summary: dict = None  # NEW: For effectifs descriptions
) -> tuple[dict | None, str | None]:
    """
    Sends user text to an LLM and attempts to parse its response
    to extract NAF sections/codes and effectifs codes.

    Args:
        user_text_prompt: The user's description of the desired company profile.
        naf_sections_config: Dictionary of NAF section details (e.g., config.naf_sections_details).
        effectifs_groupes_config: Dictionary of effectifs group details (e.g., config.effectifs_groupes_details).
        all_specific_naf_codes: An optional list of all valid specific NAF codes for stricter validation.
        naf_detailed_lookup_for_libelles: Optional dict of NAF code -> libellé for summary.
        effectifs_tranches_map_for_summary: Optional dict of effectif code -> description for summary.

    Returns:
        A tuple: (dictionary_with_codes, human_readable_summary_string) if successful, else (None, None).
    """
    if not OPENROUTER_API_KEY:
        st.error(
            "Clé API OpenRouter non configurée. "
            "Veuillez la définir dans les secrets Streamlit (OPENROUTER_API_KEY) "
            "ou comme variable d'environnement."
        )
        return None, None

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )

    # Prepare data for the prompt
    prompt_naf_sections = {
        key: details["description"] for key, details in naf_sections_config.items()
    }
    prompt_effectifs_groups = {
        group_key: {
            "label": details["label"],
            "codes": details["codes"]
        } for group_key, details in effectifs_groupes_config.items()
    }

    system_prompt = f"""
Vous êtes un assistant expert en recherche d'emploi. Votre rôle est d'aider l'utilisateur à définir des critères de recherche d'entreprises.
En fonction de la description fournie par l'utilisateur, vous devez suggérer :
1. Les sections NAF pertinentes (codes alphabétiques).
2. Optionnellement, des codes NAF spécifiques (format XXXXX ou XX.XXZ) s'ils sont clairement identifiables.
3. Les catégories de tranches d'effectifs salariés (codes numériques).

Voici les sections NAF disponibles (utilisez la lettre comme code) :
{json.dumps(prompt_naf_sections, indent=2, ensure_ascii=False)}

Voici les groupes de tranches d'effectifs disponibles (utilisez les codes numériques listés dans 'codes' pour chaque groupe) :
{json.dumps(prompt_effectifs_groups, indent=2, ensure_ascii=False)}

Veuillez retourner votre réponse UNIQUEMENT sous forme d'objet JSON avec la structure suivante :
{{
  "naf_sections": ["LISTE_DES_LETTRES_DE_SECTION_NAF"],
  "naf_specific_codes": ["LISTE_DES_CODES_NAF_SPECIFIQUES_OU_LISTE_VIDE"],
  "effectifs_codes": ["LISTE_DES_CODES_DE_TRANCHES_EFFECTIFS"]
}}

---
**Règles d'interprétation supplémentaires :**

* **Taille d'effectifs (exclusion des petites structures par défaut) :**
    * **NE PAS inclure** les codes d'effectifs correspondant aux "0 salarié" et "1 à 9 salariés" par défaut.
    * **Incluez ces petits effectifs UNIQUEMENT si l'utilisateur mentionne explicitement des termes comme** "startup", "nouvelle entreprise", "petite entreprise", "TPE", "indépendant", "freelance", ou si le **contexte du poste ou du secteur** d'activité suggère fortement des structures de très petite taille (par exemple, "artisanat", "consultant indépendant", "micro-entreprise").

* **Déduction des secteurs (quand seul le poste est mentionné) :**
    * Si l'utilisateur ne mentionne qu'un métier sans secteur d'activité, analysez la nature du poste.
    * **Si le poste est générique et peut s'appliquer à une multitude de secteurs** (ex: "comptable", "assistant(e) de direction", "responsable marketing"), et qu'aucune indication de petite taille n'est donnée (moins de 10 personnes), **NE PAS restreindre les `naf_sections` ou `naf_specific_codes` à un petit ensemble**. Réfléchissez à une large gamme de secteurs pertinents pour un tel poste dans des entreprises de taille plus significative.
    * **Si le poste est très spécifique à un ou quelques secteurs/codes NAF** (ex: "soudeur", "œnologue", "développeur front-end"), alors identifiez les `naf_sections` et `naf_specific_codes` correspondants. Essaie néanmoins d'être le plus large possible.

---

Exemple de description utilisateur : "Je cherche des PME dans le développement logiciel et le conseil informatique."
Exemple de sortie JSON attendue :
{{
  "naf_sections": ["J"],
  "naf_specific_codes": ["62.01Z", "62.02A", "62.09Z"],
  "effectifs_codes": ["11", "12", "21", "22", "31", "32"]
}}

Si vous ne pouvez pas déterminer avec certitude certains critères, retournez une liste vide pour la clé correspondante.
Assurez-vous que les lettres de section NAF et les codes d'effectifs sont valides d'après les listes fournies.
N'incluez aucune explication ou texte en dehors de l'objet JSON.
"""

    try:
        with st.spinner("L'assistant IA réfléchit à des suggestions..."):
            completion = client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": HTTP_REFERER,
                    "X-Title": X_TITLE,
                },
                model="google/gemma-3-27b-it:free",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text_prompt}
                ],
                response_format={"type": "json_object"} # Request JSON output
            )
        
        response_content = completion.choices[0].message.content
        
        llm_response_data: LLMSuggestionOutput
        try:
            # Validate the JSON structure and types using Pydantic
            llm_response_data = LLMSuggestionOutput.model_validate_json(response_content)
        except json.JSONDecodeError:
            st.error("Erreur : La réponse de l'assistant IA n'était pas un JSON valide.")
            print(f"LLM JSONDecodeError. Raw response: {response_content}") # For server-side logs
            return None, None
        except ValidationError as e:
            st.error(f"Erreur de validation de la structure de la réponse IA : {e}")
            print(f"LLM Pydantic ValidationError. Raw response: {response_content}\nError: {e}")
            return None, None
            
        validated_suggestions = {
            "naf_sections": [],
            "naf_specific_codes": [],
            "effectifs_codes": []
        }

        # Validate NAF sections
        if llm_response_data.naf_sections: # Pydantic ensures it's a list of strings if not None
            valid_naf_section_keys = naf_sections_config.keys()
            validated_suggestions["naf_sections"] = [
                s.upper() for s in llm_response_data.naf_sections if s.upper() in valid_naf_section_keys
            ]

        # Validate specific NAF codes
        if llm_response_data.naf_specific_codes:
            temp_specific_codes = []
            # Prepare a set of valid specific NAF codes for efficient lookup, if available.
            # Ensure codes from all_specific_naf_codes are uppercase for consistent comparison.
            valid_specific_codes_master_set = (
                set(s.upper() for s in all_specific_naf_codes if isinstance(s, str))
                if all_specific_naf_codes
                else None
            )

            for code_suggestion_str in llm_response_data.naf_specific_codes:
                if not isinstance(code_suggestion_str, str) or not code_suggestion_str.strip():
                    continue # Skip if not a non-empty string

                code_to_validate = code_suggestion_str.strip().upper()

                if valid_specific_codes_master_set:
                    # If a master list (from NAF.csv) is provided, the code MUST be in it.
                    if code_to_validate in valid_specific_codes_master_set:
                        temp_specific_codes.append(code_to_validate)
                else:
                    # Fallback: No master list provided. Use basic format validation.
                    # NAF.csv codes are "XX.XXZ". Prompt allows "XXXXX" or "XX.XXZ".
                    if (len(code_to_validate) == 6 and code_to_validate[2] == '.' and
                        code_to_validate[0:2].isdigit() and code_to_validate[3:5].isdigit() and
                        code_to_validate[5].isalpha()): # XX.DDZ format
                        temp_specific_codes.append(code_to_validate)
                    elif len(code_to_validate) == 5 and code_to_validate.isalnum(): # XXXXX format
                        temp_specific_codes.append(code_to_validate)

            validated_suggestions["naf_specific_codes"] = temp_specific_codes

        # Validate effectifs codes
        if llm_response_data.effectifs_codes: # Pydantic ensures it's a list of strings
            all_valid_effectifs_codes = set()
            for group_details in effectifs_groupes_config.values():
                all_valid_effectifs_codes.update(group_details.get("codes", []))
            
            validated_suggestions["effectifs_codes"] = [
                e for e in llm_response_data.effectifs_codes if e in all_valid_effectifs_codes
            ]
            
        if not validated_suggestions["naf_sections"] and \
           not validated_suggestions["naf_specific_codes"] and \
           not validated_suggestions["effectifs_codes"]:
            st.info("L'assistant IA n'a pas pu extraire de critères pertinents à partir de votre description.")
            return None, None

        # --- Build Human-Readable Summary ---
        summary_parts = ["**L'IA a suggéré et validé les critères suivants :**"]

        if validated_suggestions["naf_sections"]:
            section_descs = []
            for sec_code in validated_suggestions["naf_sections"]:
                desc = naf_sections_config.get(sec_code, {}).get("description", sec_code)
                section_descs.append(f"_{sec_code} ({desc})_")
            summary_parts.append(f"🔍 **Secteurs NAF :** {', '.join(section_descs)}")

        if validated_suggestions["naf_specific_codes"]:
            specific_code_descs = []
            for code in validated_suggestions["naf_specific_codes"]:
                libelle = naf_detailed_lookup_for_libelles.get(code, "Libellé inconnu") if naf_detailed_lookup_for_libelles else code
                specific_code_descs.append(f"_{code} ({libelle})_")
            summary_parts.append(f"🏷️ **Codes NAF spécifiques :** {', '.join(specific_code_descs)}")

        if validated_suggestions["effectifs_codes"]:
            effectif_descs = []
            if effectifs_tranches_map_for_summary:
                for code in validated_suggestions["effectifs_codes"]:
                    desc = effectifs_tranches_map_for_summary.get(code, code)
                    effectif_descs.append(f"_{desc} (code: {code})_")
            else: # Fallback if the map is not passed
                for code in validated_suggestions["effectifs_codes"]:
                    effectif_descs.append(f"_Code: {code}_")
            summary_parts.append(f"👥 **Tranches d'effectifs :** {', '.join(effectif_descs)}")

        human_readable_summary = "\n\n".join(summary_parts)
        return validated_suggestions, human_readable_summary

    except Exception as e:
        st.error(f"Erreur lors de la communication avec l'assistant IA : {e}")
        print(f"LLM Exception: {e}") # For server-side logs
        return None, None

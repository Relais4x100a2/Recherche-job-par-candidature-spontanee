import json
import os
from openai import OpenAI
import streamlit as st
from pydantic import BaseModel, ValidationError
from typing import List, Optional

import data_utils # For NAF code utilities
import config # For NAF_SECTION_MAP if used directly, though get_section_for_code is preferred

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
2. **Impérativement**, des codes NAF spécifiques (format XXXXX ou XX.XXZ) s'ils sont clairement identifiables à partir du métier ou du secteur décrit. Soyez précis si possible.
3. Les catégories de tranches d'effectifs salariés (codes numériques).

Voici les sections NAF disponibles (utilisez la lettre comme code) :
{json.dumps(prompt_naf_sections, indent=2, ensure_ascii=False)}

Voici les groupes de tranches d'effectifs disponibles (utilisez les codes numériques listés dans 'codes' pour chaque groupe) :
{json.dumps(prompt_effectifs_groups, indent=2, ensure_ascii=False)}

Veuillez retourner votre réponse UNIQUEMENT sous forme d'objet JSON avec la structure suivante :
{{
  "naf_sections": ["LISTE_DES_LETTRES_DE_SECTION_NAF"],
  "naf_specific_codes": ["LISTE_DES_CODES_NAF_SPECIFIQUES_OU_LISTE_VIDE_SI_AUCUN_N_EST_EVIDENT"],
  "effectifs_codes": ["LISTE_DES_CODES_DE_TRANCHES_EFFECTIFS"]
}}

---
**Règles d'interprétation supplémentaires :**

* **Codes NAF spécifiques :**
    * Si un métier précis est mentionné (ex: "ambulancier", "boulanger", "développeur web"), **faites votre possible pour identifier le(s) code(s) NAF spécifique(s) le(s) plus direct(s)** correspondant à ce métier, en plus de la section NAF.
    * Si le secteur est très spécifique (ex: "fabrication de pain", "transport médicalisé"), identifiez également les codes NAF spécifiques.

* **Taille d'effectifs (exclusion des petites structures par défaut) :**
    * **NE PAS inclure** les codes d'effectifs correspondant aux "0 salarié" et "1 à 9 salariés" par défaut.
    * **Incluez ces petits effectifs UNIQUEMENT si l'utilisateur mentionne explicitement des termes comme** "startup", "nouvelle entreprise", "petite entreprise", "TPE", "indépendant", "freelance", ou si le **contexte du poste ou du secteur** d'activité suggère fortement des structures de très petite taille (par exemple, "artisanat", "consultant indépendant", "micro-entreprise").

* **Déduction des secteurs (quand seul le poste est mentionné) :**
    * Si l'utilisateur ne mentionne qu'un métier sans secteur d'activité, analysez la nature du poste.
    * **Si le poste est générique et peut s'appliquer à une multitude de secteurs** (ex: "comptable", "assistant(e) de direction", "responsable marketing"), et qu'aucune indication de petite taille n'est donnée (moins de 10 personnes), **NE PAS restreindre les `naf_sections` ou `naf_specific_codes` à un petit ensemble**. Réfléchissez à une large gamme de secteurs pertinents pour un tel poste dans des entreprises de taille plus significative.
    * **Si le poste est très spécifique à un ou quelques secteurs/codes NAF** (ex: "soudeur", "œnologue", "développeur front-end"), alors identifiez les `naf_sections` et `naf_specific_codes` correspondants. Essaie néanmoins d'être le plus large possible.
---

Exemple de description utilisateur : "Je cherche un poste d'ambulancier."
Exemple de sortie JSON attendue (si "ambulancier" correspond à 86.90A dans la section Q) :
{{
  "naf_sections": ["Q"],
  "naf_specific_codes": ["86.90A"],
  "effectifs_codes": ["11", "12", "21", "22"]
}}

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
                model=LLM_MODEL, # Utiliser la variable LLM_MODEL
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
                # Normalisation : si le code est XXXXX, on essaie de le convertir en XX.XXZ si possible
                # ou plutôt, on s'assure que le format est cohérent avec NAF.csv (XX.XXZ)
                # Pour l'instant, on accepte les deux formats si valid_specific_codes_master_set n'est pas là.
                # Si NAF.csv contient "86.90A", et que l'IA sort "8690A", la validation échouera si on ne normalise pas.
                # Cependant, NAF.csv est la source de vérité pour les codes valides.
                # Donc, si `all_specific_naf_codes` est fourni, on se fie à ça.

                if valid_specific_codes_master_set:
                    # If a master list (from NAF.csv) is provided, the code MUST be in it.
                    # On va essayer de matcher "8690A" avec "86.90A"
                    normalized_code_for_lookup = code_to_validate
                    if len(code_to_validate) == 5 and code_to_validate[0:2].isdigit() and code_to_validate[2:4].isdigit() and code_to_validate[4].isalpha():
                        # Format XDDDA -> XD.DDA
                        normalized_code_for_lookup = f"{code_to_validate[0:2]}.{code_to_validate[2:4]}{code_to_validate[4]}"

                    if code_to_validate in valid_specific_codes_master_set:
                        temp_specific_codes.append(code_to_validate)
                    elif normalized_code_for_lookup != code_to_validate and normalized_code_for_lookup in valid_specific_codes_master_set:
                        temp_specific_codes.append(normalized_code_for_lookup) # Add the NAF.csv format
                else:
                    # Fallback: No master list provided. Use basic format validation.
                    if (len(code_to_validate) == 6 and code_to_validate[2] == '.' and
                        code_to_validate[0:2].isdigit() and code_to_validate[3:5].isdigit() and
                        code_to_validate[5].isalpha()): # XX.DDZ format
                        temp_specific_codes.append(code_to_validate)
                    elif len(code_to_validate) == 5 and code_to_validate.isalnum(): # XXXXX format
                        temp_specific_codes.append(code_to_validate)


            validated_suggestions["naf_specific_codes"] = list(set(temp_specific_codes)) # Ensure uniqueness

        # Validate effectifs codes
        if llm_response_data.effectifs_codes: # Pydantic ensures it's a list of strings
            all_valid_effectifs_codes = set()
            for group_details in effectifs_groupes_config.values():
                all_valid_effectifs_codes.update(group_details.get("codes", []))
            
            validated_suggestions["effectifs_codes"] = [
                e for e in llm_response_data.effectifs_codes if e in all_valid_effectifs_codes
            ]

        # --- Cross-validate specific NAF codes against suggested NAF sections ---
        # If both NAF sections and specific NAF codes are suggested,
        # ensure that the specific codes belong to one of the suggested sections.
        if validated_suggestions["naf_sections"] and validated_suggestions["naf_specific_codes"]:
            # data_utils.get_naf_lookup() should have been called in app.py to initialize NAF data
            # needed by data_utils.get_section_for_code.
            
            original_specific_code_count = len(validated_suggestions["naf_specific_codes"])
            codes_to_keep = []
            for specific_code in validated_suggestions["naf_specific_codes"]:
                # data_utils.get_section_for_code uses config.NAF_SECTION_MAP internally
                section_for_this_specific_code = data_utils.get_section_for_code(specific_code)
                if section_for_this_specific_code and section_for_this_specific_code in validated_suggestions["naf_sections"]:
                    codes_to_keep.append(specific_code)
                else:
                    print(f"LLM DEBUG: Specific code {specific_code} (actual section: {section_for_this_specific_code}) "
                          f"dropped because its section is not in suggested sections {validated_suggestions['naf_sections']}.")
            
            if original_specific_code_count > 0 and not codes_to_keep and validated_suggestions["naf_sections"]:
                # Si l'IA a suggéré des codes spécifiques, mais qu'aucun ne correspond aux sections NAF suggérées,
                # il est préférable de ne pas appliquer de codes spécifiques du tout plutôt que de potentiellement
                # filtrer tous les résultats si l'utilisateur choisit "Appliquer Secteurs ET Codes Spécifiques".
                # On pourrait logger cela.
                print(f"LLM WARNING: All {original_specific_code_count} specific NAF codes suggested by AI were inconsistent with suggested NAF sections {validated_suggestions['naf_sections']}. Clearing specific codes.")
                validated_suggestions["naf_specific_codes"] = []
            else:
                validated_suggestions["naf_specific_codes"] = codes_to_keep


        if not validated_suggestions["naf_sections"] and \
           not validated_suggestions["naf_specific_codes"] and \
           not validated_suggestions["effectifs_codes"]:
            # st.info("L'assistant IA n'a pas pu extraire de critères pertinents (ou cohérents entre eux) à partir de votre description.")
            # Le message sera affiché dans app.py si suggestions est None
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
        elif llm_response_data.naf_specific_codes and not validated_suggestions["naf_specific_codes"]: # Codes suggérés mais tous invalidés/incohérents
            summary_parts.append("🏷️ **Codes NAF spécifiques :** _Aucun code spécifique suggéré par l'IA n'a pu être validé ou n'était cohérent avec les sections NAF._")

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
        
        # S'assurer qu'on ne retourne pas de listes vides si elles n'étaient pas demandées ou si rien n'a été trouvé
        final_suggestions = {}
        if validated_suggestions["naf_sections"]:
            final_suggestions["naf_sections"] = validated_suggestions["naf_sections"]
        if validated_suggestions["naf_specific_codes"]:
            final_suggestions["naf_specific_codes"] = validated_suggestions["naf_specific_codes"]
        if validated_suggestions["effectifs_codes"]:
            final_suggestions["effectifs_codes"] = validated_suggestions["effectifs_codes"]

        if not final_suggestions: # Si tout est vide après filtrage
             return None, "L'IA n'a pas pu extraire de critères pertinents ou cohérents."

        return final_suggestions, human_readable_summary

    except Exception as e:
        st.error(f"Erreur lors de la communication avec l'assistant IA : {e}")
        import traceback
        print(f"LLM Exception: {e}\n{traceback.format_exc()}") # For server-side logs
        return None, None

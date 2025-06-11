# llm_utils.py (Version finale avec architecture en 2 appels)
import json
import os
from openai import OpenAI, RateLimitError, APIError
import streamlit as st
from pydantic import BaseModel, ValidationError
from typing import List, Optional

import data_utils  # Pour les utilitaires de code NAF
import rag_utils  # Pour l'intégration RAG

# --- CONFIGURATION ---
OPENROUTER_API_KEY = st.secrets.get("OPENROUTER_API_KEY", os.environ.get("OPENROUTER_API_KEY"))

HTTP_REFERER = os.environ.get("LLM_HTTP_REFERER", "https://recherche-job-par-candidature-spontanee.streamlit.app/")
X_TITLE = os.environ.get("LLM_X_TITLE", "Streamlit Job Search App")
LLM_MODEL = "google/gemma-3-27b-it:free" 

# --- MODÈLE PYDANTIC POUR LA RÉPONSE LLM ---
class LLMSuggestionOutput(BaseModel):
    developed_text: Optional[str] = None
    naf_sections: Optional[List[str]] = []
    naf_specific_codes: Optional[List[str]] = []
    effectifs_codes: Optional[List[str]] = []


# --- FONCTION HELPER POUR LA VALIDATION ET LE RÉSUMÉ ---
def _validate_and_summarize_llm_response(
    llm_response_data: LLMSuggestionOutput,
    naf_sections_config: dict,
    effectifs_groupes_config: dict,
    all_specific_naf_codes: list,
    naf_detailed_lookup_for_libelles: dict,
    effectifs_tranches_map_for_summary: dict
) -> tuple[dict | None, str | None]:
    """
    Valide la réponse parsée du LLM, la nettoie et crée un résumé lisible.
    Cette fonction est une refactorisation de votre logique de validation originale.
    """
    validated_suggestions = {
        "naf_sections": [],
        "naf_specific_codes": [],
        "effectifs_codes": []
    }

    # Valider les sections NAF
    if llm_response_data.naf_sections:
        valid_naf_section_keys = naf_sections_config.keys()
        validated_suggestions["naf_sections"] = [
            s.upper() for s in llm_response_data.naf_sections if s.upper() in valid_naf_section_keys
        ]

    # Valider les codes NAF spécifiques
    if llm_response_data.naf_specific_codes and all_specific_naf_codes:
        valid_specific_codes_master_set = set(s.upper() for s in all_specific_naf_codes if isinstance(s, str))
        temp_specific_codes = []
        for code_suggestion_str in llm_response_data.naf_specific_codes:
            if not isinstance(code_suggestion_str, str) or not code_suggestion_str.strip():
                continue
            code_to_validate = code_suggestion_str.strip().upper()
            if code_to_validate in valid_specific_codes_master_set:
                temp_specific_codes.append(code_to_validate)
        validated_suggestions["naf_specific_codes"] = list(set(temp_specific_codes))

    # Valider les codes d'effectifs
    if llm_response_data.effectifs_codes:
        all_valid_effectifs_codes = set()
        for group_details in effectifs_groupes_config.values():
            all_valid_effectifs_codes.update(group_details.get("codes", []))
        validated_suggestions["effectifs_codes"] = [
            e for e in llm_response_data.effectifs_codes if e in all_valid_effectifs_codes
        ]

    # Validation croisée : s'assurer que les codes spécifiques appartiennent aux sections suggérées
    if validated_suggestions["naf_sections"] and validated_suggestions["naf_specific_codes"]:
        codes_to_keep = [
            code for code in validated_suggestions["naf_specific_codes"]
            if data_utils.get_section_for_code(code) in validated_suggestions["naf_sections"]
        ]
        if len(codes_to_keep) < len(validated_suggestions["naf_specific_codes"]):
            print(f"LLM WARNING: Certains codes NAF spécifiques ont été retirés car ils ne correspondaient pas aux sections suggérées.")
        validated_suggestions["naf_specific_codes"] = codes_to_keep

    # Si rien n'est validé, retourner None
    if not any(validated_suggestions.values()):
        return None, "L'IA n'a pas pu extraire de critères pertinents ou cohérents."

    # Construire le résumé lisible
    summary_parts = []
    if llm_response_data.developed_text and llm_response_data.developed_text.strip():
        summary_parts.append(f"**Analyse de l'IA :**\n_{llm_response_data.developed_text.strip()}_")
        summary_parts.append("\n**Critères suggérés et validés :**")
    else:
        summary_parts.append("**L'IA a suggéré et validé les critères suivants :**")

    if validated_suggestions["naf_sections"]:
        section_descs = [f"_{sc} ({naf_sections_config.get(sc, {}).get('description', sc)})_" for sc in validated_suggestions["naf_sections"]]
        summary_parts.append(f"🔍 **Secteurs NAF :** {', '.join(section_descs)}")

    if validated_suggestions["naf_specific_codes"]:
        specific_code_descs = [f"_{code} ({naf_detailed_lookup_for_libelles.get(code, 'Libellé inconnu')})_" for code in validated_suggestions["naf_specific_codes"]]
        summary_parts.append(f"🏷️ **Codes NAF spécifiques :** {', '.join(specific_code_descs)}")

    if validated_suggestions["effectifs_codes"]:
        effectif_descs = [f"_{effectifs_tranches_map_for_summary.get(code, code)} (code: {code})_" for code in validated_suggestions["effectifs_codes"]]
        summary_parts.append(f"👥 **Tranches d'effectifs :** {', '.join(effectif_descs)}")

    human_readable_summary = "\n\n".join(summary_parts)

    return validated_suggestions, human_readable_summary


# --- FONCTION D'APPEL N°1 : Le "Brainstormer" ---
def _get_brainstormed_domains(user_text_prompt: str, client: OpenAI) -> tuple[list[str], str | None]:
    """
    Premier appel LLM pour brainstormer les types d'entreprises en langage naturel.
    """
    system_prompt_brainstorm = """
    Vous êtes un conseiller d'orientation expert. Votre unique mission est d'analyser la description d'un métier ou d'un projet professionnel.
    En réponse, listez de manière concise sous forme de puces les types d'entreprises ou de secteurs d'activités concrets où cette personne pourrait travailler.
    Ne vous souciez pas des codes NAF. Soyez descriptif. Ne fournissez aucune phrase d'introduction ou de conclusion, juste la liste à puces.

    Exemple de demande : "Je suis développeur web."
    Votre réponse attendue :
    - Entreprises de services du numérique (ESN)
    - Agences web et de communication
    - Éditeurs de logiciels
    - Startups technologiques
    - Le département informatique de grandes entreprises
    - Conseil en systèmes et logiciels informatiques
    """
    try:
        completion = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt_brainstorm},
                {"role": "user", "content": user_text_prompt}
            ],
            temperature=0.5,
        )
        response_text = completion.choices[0].message.content
        domains = []
        if response_text: # Ensure response_text is not None
            for line in response_text.split('\n'):
                stripped_line = line.strip()
                if stripped_line.startswith("- ") or stripped_line.startswith("* "):
                    domains.append(stripped_line.lstrip("-* ").strip())
        return domains, response_text
    except Exception as e:
        print(f"LLM Brainstorming Error: {e}")
        return [], None

# --- ORCHESTRATEUR PRINCIPAL ---
def get_llm_suggestions(
    user_text_prompt: str,
    naf_sections_config: dict,
    effectifs_groupes_config: dict,
    all_specific_naf_codes: list = None,
    naf_detailed_lookup_for_libelles: dict = None,
    effectifs_tranches_map_for_summary: dict = None,
    rag_model=None,
    rag_index=None,
    rag_codes_map=None
) -> tuple[dict | None, str | None]:
    """
    Orchestre le processus en 2 appels LLM pour générer des suggestions précises.
    """
    if not OPENROUTER_API_KEY:
        st.error("Clé API OpenRouter non configurée.")
        return None, None

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
        default_headers={"HTTP-Referer": HTTP_REFERER, "X-Title": X_TITLE}
    )

    # === ÉTAPE 1: APPEL LLM N°1 - Le "Brainstormer" ===
    with st.spinner("Analyse du métier et des secteurs potentiels... (Étape 1/3)"):
        brainstormed_domains, raw_brainstorm_response = _get_brainstormed_domains(user_text_prompt, client)


    if not brainstormed_domains:
        log_message = f"LLM Brainstorming Warning: Aucun domaine d'activité identifié pour la requête utilisateur : '{user_text_prompt}'."
        if raw_brainstorm_response:
            log_message += f"\nRéponse brute du LLM (Brainstormer) :\n---\n{raw_brainstorm_response}\n---"
        print(log_message)
        st.warning("L'IA n'a pas pu identifier de domaines d'activité. Essayez de reformuler votre demande.")
        return None, None
    
    print(f"Domaines brainstormés par l'IA : {brainstormed_domains}")

    # === ÉTAPE 2: LE "MATCHER" - Recherche RAG en boucle ===
    with st.spinner("Recherche des codes NAF correspondants... (Étape 2/3)"):
        relevant_naf_codes_set = set()
        for domain in brainstormed_domains:
            codes_from_rag = rag_utils.find_relevant_naf_codes(
                query=domain, model=rag_model, index=rag_index, codes_mapping=rag_codes_map, k=5
            )
            relevant_naf_codes_set.update(codes_from_rag)
    
    final_naf_codes_list = sorted(list(relevant_naf_codes_set))
    if not final_naf_codes_list:
        st.warning("Aucun code NAF spécifique trouvé pour les domaines identifiés.")
        return None, None
    print(f"Codes NAF pertinents trouvés via RAG : {final_naf_codes_list}")

    # === ÉTAPE 3: APPEL LLM N°2 - Le "Synthétiseur" ===
    with st.spinner("Synthèse des suggestions finales... (Étape 3/3)"):
        prompt_naf_sections = {key: details["description"] for key, details in naf_sections_config.items()}
        prompt_effectifs_groups = {group_key: {"label": details["label"], "codes": details["codes"]} for group_key, details in effectifs_groupes_config.items()}

        system_prompt_synthesize = f"""
        Vous êtes un assistant expert qui finalise une recherche de critères d'emploi.
        Votre mission est de synthétiser les informations fournies pour générer un objet JSON final.

        CONTEXTE FOURNI :
        1. Requête initiale de l'utilisateur : "{user_text_prompt}"
        2. Domaines d'activités pertinents identifiés : {json.dumps(brainstormed_domains, ensure_ascii=False)}
        3. Liste de codes NAF spécifiques pertinents trouvés : {json.dumps(final_naf_codes_list, ensure_ascii=False)}

        VOTRE TÂCHE :
        1.  **Choisir les codes NAF spécifiques** : À partir de la "Liste de codes NAF spécifiques pertinents trouvés", sélectionnez les plus appropriés pour la requête de l'utilisateur.
        2.  **Déduire les sections NAF** : Déduisez les sections NAF (lettres) à partir des codes spécifiques que vous avez choisis.
        3.  **Suggérer les effectifs** : Suggérez les tranches d'effectifs pertinentes. Excluez par défaut les TPE (<10 salariés) sauf si la requête initiale le suggère explicitement (startup, freelance, etc.).
        En vous basant sur la requête utilisateur et les `Groupes d'effectifs disponibles` (fournis en JSON dans le prompt système global sous `prompt_effectifs_groups`), sélectionnez les codes d'effectifs appropriés.
            - Pour une description de poste générale (exemples: "horticulteur", "développeur web"), votre sélection doit typiquement inclure les catégories pour PME (codes "11", "12", "21", "22"), ETI/Grandes Entreprises (codes "31", "32", "41", "42", "51", "52", "53"), ET AUSSI "Unités non-employeuses" (code "NN", pour couvrir les indépendants).
            - Si la requête utilisateur mentionne explicitement des termes comme "startup", "petite structure", "artisan", "commerce de proximité", alors AJOUTEZ les TPE (codes "01", "02", "03") à votre sélection précédente.
            - Si la requête est très ciblée sur "freelance", "consultant indépendant", "auto-entrepreneur", alors "Unités non-employeuses" ("NN") est le plus pertinent, potentiellement accompagné des TPE.
            Assurez-vous que les codes retournés dans `effectifs_codes` correspondent aux catégories que vous avez jugées pertinentes.
        4.  **Rédiger un texte de synthèse** (`developed_text`) : Rédigez un court texte qui explique votre raisonnement final (y compris pour les effectifs) en vous basant sur le contexte fourni.

        RÉFÉRENCES (à utiliser pour valider vos choix) :
        - Sections NAF disponibles : {json.dumps(prompt_naf_sections, indent=2, ensure_ascii=False)}
        - Groupes d'effectifs disponibles : {json.dumps(prompt_effectifs_groups, indent=2, ensure_ascii=False)}
        
        FORMAT DE SORTIE :
        Retournez UNIQUEMENT l'objet JSON final. Ne mettez aucun commentaire.
        ```json
        {{
          "developed_text": "TEXTE DE SYNTHÈSE JUSTIFIANT LES CHOIX FINALS.",
          "naf_sections": ["LISTE_DES_LETTRES_DE_SECTION_NAF"],
          "naf_specific_codes": ["LISTE_FINALE_DES_CODES_NAF_SPECIFIQUES"],
          "effectifs_codes": ["LISTE_DES_CODES_DE_TRANCHES_EFFECTIFS"]
        }}
        ```
        """
        try:
            completion = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "system", "content": system_prompt_synthesize}],
                response_format={"type": "json_object"}
            )
            response_content = completion.choices[0].message.content
            
            # Valider la structure de la réponse avec Pydantic
            llm_response_data = LLMSuggestionOutput.model_validate_json(response_content)
            
            # Utiliser la fonction helper pour valider le contenu et créer le résumé
            return _validate_and_summarize_llm_response(
                llm_response_data,
                naf_sections_config,
                effectifs_groupes_config,
                all_specific_naf_codes,
                naf_detailed_lookup_for_libelles,
                effectifs_tranches_map_for_summary
            )

        except (RateLimitError, APIError, ValidationError, json.JSONDecodeError) as e:
            error_message = f"Une erreur est survenue lors de la phase de synthèse de l'IA : {e}"
            st.error(error_message)
            print(f"LLM Synthesis Error: {e}")
            import traceback
            print(traceback.format_exc())
            return None, None
        except Exception as e:
            st.error(f"Une erreur inattendue est survenue : {e}")
            import traceback
            print(f"Unexpected LLM Error: {e}\n{traceback.format_exc()}")
            return None, None
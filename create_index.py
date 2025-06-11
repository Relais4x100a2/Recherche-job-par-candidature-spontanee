# create_index.py
import faiss
from sentence_transformers import SentenceTransformer
import numpy as np
import json
import os
import sys 

import data_utils 

# --- CONFIGURATION ---
INDEX_DIR = "rag_index"
INDEX_PATH = os.path.join(INDEX_DIR, "naf_index.faiss")
MAPPING_PATH = os.path.join(INDEX_DIR, "naf_codes_mapping.json")
EMBEDDING_MODEL = 'dangvantuan/sentence-camembert-base'

def create_rag_index():
    """
    Crée et sauvegarde l'index FAISS pour les libellés NAF et le mapping des codes NAF correspondants.
    Ce script est destiné à être exécuté une fois pour préparer les ressources nécessaires au RAG.
    """
    print(f"Création du répertoire pour l'index : {os.path.abspath(INDEX_DIR)}")
    try:
        os.makedirs(INDEX_DIR, exist_ok=True)
    except OSError as e:
        print(f"Erreur critique lors de la création du répertoire {INDEX_DIR}: {e}")
        sys.exit(1)

    # 1. Charger vos données NAF
    print("Chargement des données NAF via data_utils.get_naf_lookup()...")
    # get_naf_lookup() appelle load_naf_dictionary() qui est décoré par @st.cache_data.
    # Si ce script est exécuté en dehors d'une application Streamlit,
    # le décorateur @st.cache_data pourrait ne pas fournir de mise en cache effective,
    # mais la fonction load_naf_dictionary() devrait s'exécuter normalement.
    # L'environnement d'exécution doit avoir 'streamlit' installé car data_utils.py l'importe.
    naf_detailed_lookup = data_utils.get_naf_lookup()

    if naf_detailed_lookup is None:
        print("Erreur critique: Le dictionnaire NAF n'a pas pu être chargé (retourné None).")
        print("Veuillez vérifier la configuration de NAF_FILE_PATH dans config.py et l'état du fichier NAF.")
        # Essaye d'afficher le chemin configuré pour aider au débogage
        try:
            naf_file_path_from_config = data_utils.config.NAF_FILE_PATH
            print(f"Le chemin configuré dans config.NAF_FILE_PATH est: {naf_file_path_from_config}")
        except AttributeError:
            print("Impossible de lire config.NAF_FILE_PATH. Assurez-vous que config.py est accessible et correct.")
        sys.exit(1)

    if not isinstance(naf_detailed_lookup, dict) or not naf_detailed_lookup:
        print("Erreur: Les données NAF chargées ne sont pas un dictionnaire valide ou sont vides.")
        print(f"Type reçu: {type(naf_detailed_lookup)}")
        if isinstance(naf_detailed_lookup, dict):
            print(f"Nombre d'éléments: {len(naf_detailed_lookup)}")
        sys.exit(1)

    print(f"Nombre de codes NAF chargés avec succès: {len(naf_detailed_lookup)}")

    # --- Construction des libellés combinés pour l'indexation ---
    # On ne garde que les codes NAF dont la section est définie dans config.naf_sections_details
    # et on combine le libellé de la section avec le libellé du code spécifique.
    
    codes_for_index = []
    combined_libelles_for_index = []
    
    print("Construction des textes enrichis pour l'indexation RAG...")
    for code_specific, libelle_specific in naf_detailed_lookup.items():
        section_letter = data_utils.get_section_for_code(code_specific)

        # On continue de s'assurer que la section est valide et désirée
        if section_letter and section_letter in data_utils.config.naf_sections_details:
            # Nettoyage simple du libellé pour en faire des mots-clés
            keywords = libelle_specific.replace(',', ' ').replace(' et ', ' ').replace("d'", "").replace("l'", "")

            # Création d'un texte plus riche pour l'embedding
            # Ce format aide le modèle à mieux comprendre le contexte.
            text_for_embedding = f"Activité principale : {libelle_specific}. Mots-clés pertinents : {keywords}."

            codes_for_index.append(code_specific)
            combined_libelles_for_index.append(text_for_embedding)
        else:
            # Optionnel: logguer les codes NAF spécifiques dont la section n'est pas dans naf_sections_details
            print(f"Info: Le code NAF {code_specific} (section {section_letter}) est ignoré car sa section n'est pas dans config.naf_sections_details.")
            pass

    if not combined_libelles_for_index:
        print("Erreur: Aucun libellé combiné NAF (Section + Spécifique) n'a pu être construit pour l'indexation.")
        print("Vérifiez que NAF_SECTION_MAP et naf_sections_details dans config.py sont cohérents et non vides,")
        print("et que les codes NAF chargés ont des sections correspondantes.")
        sys.exit(1)

    if len(codes_for_index) != len(combined_libelles_for_index):
        # Ceci ne devrait pas arriver si naf_detailed_lookup est un dictionnaire standard
        print("Erreur: Incohérence critique entre le nombre de codes et de libellés NAF.")
        sys.exit(1)
    # 2. Charger le modèle d'embedding
    print(f"Chargement du modèle d'embedding : {EMBEDDING_MODEL}...")
    try:
        model = SentenceTransformer(EMBEDDING_MODEL)
    except Exception as e:
        print(f"Erreur critique lors du chargement du modèle d'embedding '{EMBEDDING_MODEL}': {e}")
        print("Vérifiez le nom du modèle et votre connexion internet si le modèle doit être téléchargé.")
        sys.exit(1)

    # 3. Créer les embeddings (vecteurs) pour tous les libellés NAF
    print(f"Création des embeddings pour {len(combined_libelles_for_index)} libellés NAF combinés (cela peut prendre du temps)...")
    try:
        libelle_embeddings = model.encode(combined_libelles_for_index, convert_to_tensor=False, show_progress_bar=True)
    except Exception as e:
        print(f"Erreur critique lors de la création des embeddings: {e}")
        sys.exit(1)

    if not isinstance(libelle_embeddings, np.ndarray) or libelle_embeddings.ndim != 2:
        print("Erreur: Le résultat de l'encodage des embeddings n'est pas une matrice numpy 2D valide.")
        sys.exit(1)
    if libelle_embeddings.shape[0] != len(combined_libelles_for_index):
        print(f"Erreur: Le nombre d'embeddings ({libelle_embeddings.shape[0]}) ne correspond pas au nombre de libellés combinés ({len(combined_libelles_for_index)}).")
        sys.exit(1)
    print(f"Embeddings créés avec succès. Shape: {libelle_embeddings.shape}")

    # 4. Créer et peupler l'index FAISS
    print("Création de l'index FAISS...")
    try:
        dimension = libelle_embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)  # L2 distance (Euclidean)
        # SentenceTransformer.encode() avec convert_to_tensor=False retourne float32 par défaut.
        # L'appel .astype('float32') est une bonne pratique pour s'en assurer.
        index.add(libelle_embeddings.astype(np.float32))
    except Exception as e:
        print(f"Erreur critique lors de la création ou du peuplement de l'index FAISS: {e}")
        sys.exit(1)
    print(f"Index FAISS créé et peuplé. Nombre d'éléments dans l'index: {index.ntotal}")

    # 5. Sauvegarder l'index et la liste de mapping des codes
    try:
        print(f"Sauvegarde de l'index FAISS dans {INDEX_PATH}")
        faiss.write_index(index, INDEX_PATH)
    except Exception as e:
        print(f"Erreur critique lors de la sauvegarde de l'index FAISS dans {INDEX_PATH}: {e}")
        sys.exit(1)

    try:
        print(f"Sauvegarde du mapping des codes (liste ordonnée des codes NAF) dans {MAPPING_PATH}")
        with open(MAPPING_PATH, "w", encoding="utf-8") as f:
            json.dump(codes_for_index, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Erreur critique lors de la sauvegarde du mapping des codes dans {MAPPING_PATH}: {e}")
        sys.exit(1)

    print("\n--- Préparation de l'index RAG terminée avec succès! ---")
    print(f"L'index FAISS a été sauvegardé ici : {os.path.abspath(INDEX_PATH)}")
    print(f"Le mapping des codes NAF a été sauvegardé ici : {os.path.abspath(MAPPING_PATH)}")
    print("Ces fichiers sont prêts à être utilisés par votre application RAG.")

if __name__ == "__main__":
    create_rag_index()
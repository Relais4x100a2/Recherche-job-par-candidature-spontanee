# rag_utils.py
import streamlit as st
import faiss
from sentence_transformers import SentenceTransformer
import numpy as np
import json
import os

# --- CONFIGURATION ---
INDEX_DIR = "rag_index"
INDEX_PATH = os.path.join(INDEX_DIR, "naf_index.faiss")
MAPPING_PATH = os.path.join(INDEX_DIR, "naf_codes_mapping.json")
EMBEDDING_MODEL = 'dangvantuan/sentence-camembert-base'

@st.cache_resource
def load_rag_assets():
    """
    Charge le modèle d'embedding et l'index FAISS en utilisant le cache de Streamlit.
    Cette fonction ne s'exécutera qu'une seule fois.
    """
    print("Chargement des ressources RAG (modèle + index)...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    index = faiss.read_index(INDEX_PATH)
    with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
        codes_mapping = json.load(f)
    print("Ressources RAG chargées avec succès.")
    return model, index, codes_mapping

def find_relevant_naf_codes(query: str, model, index, codes_mapping: list, k: int = 15) -> list[str]:
    """
    Prend une requête utilisateur, la transforme en vecteur et cherche les codes NAF
    les plus pertinents dans l'index FAISS.
    """
    if not query.strip():
        return []
        
    query_embedding = model.encode([query], convert_to_tensor=False).astype('float32')
    _distances, indices = index.search(query_embedding, k)
    
    relevant_codes = [codes_mapping[i] for i in indices[0]]
    return relevant_codes
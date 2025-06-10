import unsloth
from transformers import AutoTokenizer, AutoModelForCausalLM
from sentence_transformers import SentenceTransformer
from unsloth import FastLanguageModel
from app.utils.logger import get_logger
import torch
from app.utils.config import EMBEDDING_MODEL_ID, EMBEDDING_DIMENSION
import os
from dotenv import load_dotenv
import numpy as np 


logger = get_logger(__name__, subsystem="embedding")

load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")
try:
    embedding_model = SentenceTransformer(
        EMBEDDING_MODEL_ID,
        device=device
    )
    logger.info(f"Loaded SentenceTransformer: {EMBEDDING_MODEL_ID} ({EMBEDDING_DIMENSION} dimensions)")
except Exception as e:
    logger.error(f"Failed to load embedding model {EMBEDDING_MODEL_ID}: {e}")
    raise


def get_embedding(text):
    """
    Generate embedding from text using the SentenceTransformer model.
    Args:
        text (str): Input text to embed.
    Returns:
        np.ndarray: Embedding vector, or None if generation fails.
        Note: This will now return a **1024-dimensional** numpy array.
    """
    if not isinstance(text, str) or not text.strip():
        logger.warning(f"Invalid input to get_embedding: {text}")
        return None
    

    try:
        embedding = embedding_model.encode(text, convert_to_numpy=True, device=device, show_progress_bar=False)
        if embedding is None or not isinstance(embedding, np.ndarray) or embedding.size == 0:
            logger.error(f"Embedding returned None or empty array for text: '{text[:100]}...'")
            return None

        logger.debug(f"Generated embedding: shape={embedding.shape}, dtype={embedding.dtype}")

      
        if embedding.shape[-1] != EMBEDDING_DIMENSION:
             logger.warning(f"Generated embedding dimension mismatch! Expected {EMBEDDING_DIMENSION}, got {embedding.shape[-1]}.")
            
             return None
        return embedding
    except Exception as e:
        logger.exception(f"Error generating embedding for text (first 100 chars: '{text[:100]}...'): {e}")
        return None
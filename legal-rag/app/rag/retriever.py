from app.utils.embedding import get_embedding as embed
from app.utils.config import RETRIEVAL_THRESHOLD, RETRIEVAL_TOP_K, RETRIEVAL_PROBES, VECTOR_FUNCTION_NAME, EMBEDDING_DIMENSION

from supabase import create_client, Client
import os
import time
from dotenv import load_dotenv
from app.utils.logger import get_logger
import numpy as np 

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

assert SUPABASE_URL and SUPABASE_KEY, "Supabase credentials are missing."


supabase: Client | None = None 
try:
    supabase = create_client(
        SUPABASE_URL, 
        SUPABASE_KEY
    )
    logger = get_logger(__name__, subsystem="retriever") 
    logger.info(f"Supabase client created successfully in retriever")

except Exception as e:
    logger = get_logger(__name__, subsystem="retriever") 
    logger.exception(f"Failed to create Supabase client in retriever: {e}")


DATABASE_STATEMENT_TIMEOUT_STR = '60s' 


def retrieve(query: str, top_k=RETRIEVAL_TOP_K, threshold=RETRIEVAL_THRESHOLD, probes=RETRIEVAL_PROBES) -> tuple[list[dict], float]: 
    """
    Retrieves relevant legal documents from Supabase using vector similarity search.

    Args:
        query: The user's legal question.
        top_k: The maximum number of documents to retrieve.
        threshold: The minimum similarity threshold.
        probes: The number of probes for the ivfflat index search.

    Returns:
        - A list of dictionaries, where each dictionary represents a retrieved document
            including 'content', 'metadata', 'source_url', and 'similarity'.
        - float: Time taken for retrieval in seconds.
        Returns ([], 0.0) if an error occurs or no documents is found or retrieval fails.
    """
    if supabase is None:
        logger.error("Supabase client is not initialized. Cannot perform retrieval.")
        return [], 0.0
    
    logger.debug(f"Starting retrieval for query: '{query[:50]}...' with top_k={top_k}, threshold={threshold}, probes={probes}")
    
    retrieval_start_time = time.time()

    try:
        logger.debug(f"Setting database statement_timeout to '{DATABASE_STATEMENT_TIMEOUT_STR}' for the current session...")
        timeout_response = supabase.rpc(
            "set_statement_timeout", 
            {"timeout": DATABASE_STATEMENT_TIMEOUT_STR}
        ).execute()

        logger.debug("Statement timeout RPC call executed successfully.")

        query_embedding = embed(query)

        if query_embedding is None or not isinstance(query_embedding, np.ndarray) or query_embedding.shape[-1] != EMBEDDING_DIMENSION:
            logger.error(f"Failed to generate valid embedding for the query. Expected dimension {EMBEDDING_DIMENSION}.")
            retrieval_end_time = time.time() 
            retrieval_time = retrieval_end_time - retrieval_start_time
            return [], retrieval_time

        query_embedding_list = query_embedding.tolist()

        logger.debug(f"Calling RPC function '{VECTOR_FUNCTION_NAME}' with embedding shape {query_embedding.shape} and probes={probes}...")
        response = supabase.rpc(
            VECTOR_FUNCTION_NAME,
            {
                "query_embedding": query_embedding_list,
                "match_threshold": threshold,
                "match_count": top_k,
                "probes": probes,  
            },
        ).execute()

       
        
        retrieved_docs = [] 

        if response.data:
            logger.info(f"Retrieved {len(response.data)} documents matching query above threshold {threshold}.")
            retrieved_docs = response.data 
            logger.debug("--- Retrieved Documents Details ---")
            for i, doc in enumerate(retrieved_docs):
                 doc_id = doc.get('id', 'N/A')
                 similarity = doc.get('similarity', -1.0)
                 metadata = doc.get('metadata', {})
                 content_preview = doc.get('content', '')[:100]
                 chunk_urls_preview = metadata.get('chunk_urls', [])[:5]
                 logger.debug(f"  Doc {i+1}: ID={doc_id}, Sim={similarity:.4f}, Meta (part): {metadata.get('law_name')}, {metadata.get('section_heading')}, URLs (first 5): {chunk_urls_preview}, Content='{content_preview}...'")
            logger.debug("--- End Retrieved Documents ---")
        else:
            
            logger.warning(f"No documents found matching the query above the threshold {threshold}.")

    except Exception as e:
        
        logger.exception(f"An unexpected error occurred during retrieval for query '{query[:50]}...': {e}")
        
        retrieval_end_time = time.time()
        retrieval_time = retrieval_end_time - retrieval_start_time
        return [], retrieval_time 

    retrieval_end_time = time.time()
    retrieval_time = retrieval_end_time - retrieval_start_time

    return retrieved_docs, retrieval_time 
 
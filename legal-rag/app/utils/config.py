MODEL_PATH = "/home/jovyan/legalBeacon-SE/legal-rag/model/checkpoint-729" 
BASE_MODEL="unsloth/gemma-3-4b-it-unsloth-bnb-4bit"


EMBEDDING_MODEL_ID = "intfloat/multilingual-e5-large"
EMBEDDING_DIMENSION = 1024 


RETRIEVAL_THRESHOLD = 0.85 
RETRIEVAL_TOP_K = 7       
RETRIEVAL_PROBES = 120      
VECTOR_FUNCTION_NAME = "match_legal_vectors" 

CHUNK_SIZE = 2000      
CHUNK_OVERLAP = 200   

CHUNK_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

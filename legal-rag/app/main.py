import uvicorn
from fastapi import FastAPI
from .api import routes as api_routes 
import logging
import os
import sys
import time
from pathlib import Path
from logging.handlers import RotatingFileHandler



if not logging.getLogger().handlers:
    
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True) 

 
    LOG_FILE_PATH = log_dir / "legal_rag.log"
    try:
        
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG) 

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

       
        file_handler = RotatingFileHandler(
            LOG_FILE_PATH,
            maxBytes=10 * 1024 * 1024, 
            backupCount=3, 
            mode='a', 
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG) 
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO) 
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

     

        logging.info("Root logger configured for main.py entry point.") 

    except Exception as e:
      
        print(f"FATAL ERROR: Failed to configure logging handlers in main.py: {e}", file=sys.stderr)
        logging.basicConfig(level=logging.INFO, stream=sys.stderr, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        logging.error("Using minimal fallback console logging.")


logger = logging.getLogger("app") 

logger.info("Creating LegalWise Genie SE FastAPI application instance...")

app = FastAPI(
    title="Swedish Legal RAG API",
    description="API for querying a RAG system specialized in Swedish legal documents.",
    version="0.1.0",
)


app.include_router(api_routes.router, prefix="/api/v1") 

logger.info("Included API router from app.api.routes.")


@app.on_event("startup")
async def startup_event():
    start_time = time.time()
    
    logger.info("FastAPI application startup complete.")
    try:
        from app.rag.generator import model_loaded
        if model_loaded:
             logger.info("Generator model confirmed loaded.")
        else:
             logger.warning("Generator model does not appear to be loaded after startup.")
    except ImportError:
        logger.error("Could not import generator status for confirmation.")
    except Exception as e:
        logger.error(f"Error during startup check: {e}")

    end_time = time.time()
    logger.info(f"Startup event processing took {end_time - start_time:.2f} seconds.")


@app.get("/", summary="Root endpoint", description="Basic health check or welcome message.")
async def read_root():
    logger.debug("Root endpoint '/' accessed.")
    return {"message": "Welcome to the Swedish Legal RAG API!"}


if __name__ == "__main__":
    logger.info("Starting Uvicorn server directly from main.py...")
    
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("DEV_MODE", "false").lower() == "true" 

    uvicorn.run(
        "app.main:app", 
        host=host,
        port=port,
        reload=reload, 
        log_level="info"
    )
    logger.info("Uvicorn server stopped.")
from fastapi import APIRouter, HTTPException 
from pydantic import BaseModel
from app.rag.pipeline import rag_pipeline
from app.utils.logger import get_logger 
from fastapi.concurrency import run_in_threadpool 
import time 
import os
from datetime import datetime 
import hashlib 
import json 
import re
from pathlib import Path


logger = get_logger(__name__, subsystem="app")

RESULTS_DIR_NAME = "query_results" 


project_root = Path(__file__).parent.parent.parent

results_directory = project_root / RESULTS_DIR_NAME

results_directory.mkdir(exist_ok=True)
logger.info(f"Query results will be saved to: {results_directory.resolve()}")

router = APIRouter()

class QueryRequest(BaseModel):
    query: str
   

class QueryResponse(BaseModel):
    answer: str
   
def save_result_to_markdown(query: str, results: dict, end_to_end_time: float):
    """
    Saves the query results, metrics, and retrieval details to a markdown file,
    parsing the reasoning and answer from the LLM's raw output.
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:8]
        filename = f"{timestamp}_{query_hash}.md"
        filepath = results_directory / filename

        raw_llm_answer_string = results.get('answer', '')
        retrieved_records = results.get('retrieved_records', [])
        metrics = results.get('metrics', {})
        retrieval_time = metrics.get('retrieval_time', 0.0)
        generation_time = metrics.get('generation_time', 0.0)
        prompt_token_count = metrics.get('prompt_token_count', 0)
        generated_token_count = metrics.get('generated_token_count', 0)


        reasoning_match = re.search(r'<reasoning>(.*?)</reasoning>', raw_llm_answer_string, re.DOTALL) 
        answer_match = re.search(r'<answer>(.*?)</answer>', raw_llm_answer_string, re.DOTALL)

        parsed_reasoning = reasoning_match.group(1).strip() if reasoning_match else "Could not parse reasoning."
        parsed_answer = answer_match.group(1).strip() if answer_match else "Could not parse answer."

        references_match = re.search(r'Referenser:(.*)', raw_llm_answer_string, re.DOTALL)
        parsed_references_string = "Referenser:\n" + references_match.group(1).strip() if references_match else "No references found."

        markdown_content = f"# Query Result\n\n"
        markdown_content += f"## Query\n\n```\n{query}\n```\n\n---\n\n"
        markdown_content += f"## Reasoning\n\n{parsed_reasoning}\n\n---\n\n"
        markdown_content += f"## Answer\n\n{parsed_answer}\n\n---\n\n"
        markdown_content += f"## Metrics\n\n"
        markdown_content += f"- **End-to-End Time:** {end_to_end_time:.4f} seconds\n"
        markdown_content += f"- **Retrieval Time:** {retrieval_time:.4f} seconds\n"
        markdown_content += f"- **Generation Time:** {generation_time:.4f} seconds\n"
        markdown_content += f"- **Prompt Token Count:** {prompt_token_count}\n"
        markdown_content += f"- **Generated Token Count:** {generated_token_count}\n\n---\n\n"
        markdown_content += f"## Retrieved Documents ({len(retrieved_records)} found)\n\n"

        if retrieved_records:
            for i, doc in enumerate(retrieved_records):
                doc_id = doc.get('id', 'N/A')
                similarity = doc.get('similarity', -1.0)
                metadata = doc.get('metadata', {})
                source_file = metadata.get('source_file', 'N/A')
                law_name = metadata.get('law_name', 'N/A')
                section_heading = metadata.get('section_heading', 'N/A')
                source_url = doc.get('source_url', 'N/A')
                chunk_urls = metadata.get('chunk_urls', [])
                chunk_content_preview = doc.get('content', '')[:300]

                markdown_content += f"### Document {i+1}\n\n"
                markdown_content += f"- **ID:** `{doc_id}`\n"
                markdown_content += f"- **Similarity:** `{similarity:.4f}`\n"
                markdown_content += f"- **Source File:** `{source_file}`\n"
                markdown_content += f"- **Law Name:** {law_name}\n"
                markdown_content += f"- **Section Heading:** {section_heading}\n"
                markdown_content += f"- **Document URL:** {source_url}\n"
                markdown_content += f"- **Chunk URLs:** {json.dumps(chunk_urls)}\n"

            markdown_content += "---\n\n" 

        else:
            markdown_content += "No documents were retrieved for this query.\n\n---\n\n"

        markdown_content += f"## References\n\n"
        markdown_content += f"{parsed_references_string}\n\n" 


        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        logger.info(f"Query result saved to: {filepath}")

    except Exception as e:
        logger.exception(f"Failed to save query result to markdown file for query '{query[:50]}...': {e}")


@router.post("/query", response_model=QueryResponse) 
async def ask_query(request: QueryRequest): 
    """
    Receives a user query, processes it through the RAG pipeline,
    and returns the generated answer.
    """
    query = request.query
    logger.info(f"Received query request: '{query}'") 

    start_time = time.time()

    results = {} 

    try:
       
        logger.debug(f"Dispatching query to RAG pipeline in threadpool...")
        results = await run_in_threadpool(rag_pipeline, query)
        logger.debug(f"RAG pipeline processing complete for query: '{query[:50]}...'")

        
        if results.get('answer', '').startswith("Fel:") or results.get('answer', '').startswith("Ett internt fel"):
            logger.error(f"RAG pipeline returned an error answer: {results.get('answer', 'Unknown Error')}")
            end_time = time.time()
            elapsed_time = end_time - start_time
            logger.error(f"Processing time before RAG error for query '{query[:50]}...': {elapsed_time:.4f} seconds")
            raise HTTPException(status_code=503, detail=results.get('answer', "Ett internt fel inträffade i behandlingen.")) 
        
        end_time = time.time()
        end_to_end_time  = end_time - start_time 

        
        logger.info(f"End-to-end processing time for query '{query[:50]}...': {end_to_end_time:.4f} seconds")

       
        full_answer_string = results.get('answer', 'N/A')
        logger.info(f"Final Generated Answer for query '{query[:50]}...':\n{full_answer_string[:50]}...") 

      
        save_result_to_markdown(query, results, end_to_end_time)

       
        return QueryResponse(answer=full_answer_string) 

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.exception(f"An unexpected error occurred while processing query '{query[:100]}...': {e}")
        end_time = time.time()
        end_to_end_time = end_time - start_time
        logger.error(f"Processing time before unexpected error for query '{query[:50]}...': {end_to_end_time:.4f} seconds")
        save_result_to_markdown(query, {'answer': f"Error: {e}", 'retrieved_records': results.get('retrieved_records', [])}, end_to_end_time) 
        raise HTTPException(status_code=500, detail="Ett oväntat internt serverfel inträffade.")
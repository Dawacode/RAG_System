import os
import glob
import numpy as np
import sys
import logging
from pathlib import Path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from app.utils.embedding import get_embedding
from app.utils.logger import get_logger
from supabase import create_client, Client
from dotenv import load_dotenv
import re
from tqdm import tqdm
from app.utils.config import CHUNK_SIZE, CHUNK_OVERLAP, CHUNK_SEPARATORS, EMBEDDING_DIMENSION
from logging.handlers import RotatingFileHandler
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
import httpx


logger = get_logger(__name__, subsystem="ingestion")

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

assert SUPABASE_URL and SUPABASE_KEY, "Supabase credentials are missing."


data_dir = os.path.join(os.path.dirname(__file__), '../../scraper/output')

def extract_markdown_urls(text: str) -> list[str]:
    """
    Extracts URLs from standard markdown links [text](url) and images ![alt](url).
    Also handles the Lagen.nu specific [![...](...)](url) format.
    Returns a list of unique, cleaned URLs found. Filters out image URLs.
    """
    if not isinstance(text, str):
        logger.debug("extract_markdown_urls received non-string input.")
        return []

    urls = []

    
    standard_link_pattern = re.compile(r'\[[^\]]*\]\(([^)]+)\)')
    extracted_standard = standard_link_pattern.findall(text)
    urls.extend(extracted_standard)

    image_link_pattern = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')
    extracted_images = image_link_pattern.findall(text)
    urls.extend(extracted_images)

    
    lagen_nu_nested_pattern = re.compile(r'\[!\[.*?\]\(.*?\)\]\(([^)]+)\)')
    extracted_nested = lagen_nu_nested_pattern.findall(text)
    urls.extend(extracted_nested)


    quoted_url_pattern = re.compile(r'\[[^\]]*\]\("([^"]+)"\)')
    extracted_quoted = quoted_url_pattern.findall(text)
    urls.extend(extracted_quoted)

    image_quoted_url_pattern = re.compile(r'!\[[^\]]*\]\("([^"]+)"\)')
    extracted_image_quoted = image_quoted_url_pattern.findall(text)
    urls.extend(extracted_image_quoted)

    
    lagen_nu_quoted_pattern = re.compile(r'\[!\[.*?\]\(.*?\)\]\("([^"]+)"\)') 
    extracted_nested_quoted = lagen_nu_quoted_pattern.findall(text)
    urls.extend(extracted_nested_quoted)


    
    cleaned_urls = []
    image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.bmp')

    for original_url in urls: 
        url = original_url.strip()

        if not url:
            logger.debug(f"extract_markdown_urls - Skipping empty URL after strip: '{original_url}'")
            continue

        if url.startswith('"') and url.endswith('"'):
            logger.debug(f"extract_markdown_urls - Removing outer quotes from URL: '{url}'")
            url = url[1:-1]
        if url.startswith("'") and url.endswith("'"):
             logger.debug(f"extract_markdown_urls - Removing outer quotes from URL: '{url}'")
             url = url[1:-1]


        if url.lower().endswith(image_extensions):
             logger.debug(f"extract_markdown_urls - Filtered out potential image URL: '{original_url}'")
             continue

       
        if (url.startswith('http') or url.startswith('https')):
             problematic_suffixes_or_content = ('"', "'", '\\', 'Permalänk till detta stycke')
             if any(item in url for item in problematic_suffixes_or_content):
                  logger.debug(f"extract_markdown_urls - Filtered out URL with problematic content: '{url}'")
                  continue
        elif not (url.startswith('/') or url.startswith('#')):
             logger.debug(f"extract_markdown_urls - Filtered out non-standard URL start: '{url}'")
             continue


        cleaned_urls.append(url)
        logger.debug(f"extract_markdown_urls - Kept and cleaned URL: '{original_url}' -> '{url}'")


    unique_cleaned_urls = list(set(cleaned_urls))
    logger.debug(f"extract_markdown_urls - Final unique cleaned URLs: {unique_cleaned_urls}")
    return unique_cleaned_urls

def clean_markdown_formatting(text: str) -> str:
    """
    Removes markdown link syntax, image syntax, and other common noise
    while keeping the link text. Also removes specific lagen.nu noise.
    """
    if not isinstance(text, str):
        return ""

    cleaned_text = text

   
    cleaned_text = re.sub(r'\[!\[.*?\]\(.*?\)\]', '', cleaned_text)
    cleaned_text = re.sub(r'\[\[.*?\]\]', '', cleaned_text)
    cleaned_text = re.sub(r'!\[.*?\]\(.*?\)', '', cleaned_text)
    cleaned_text = re.sub(r'\[([^\]]*)\]\([^\)]*\)', r'\1', cleaned_text)
    cleaned_text = re.sub(r'^#+\s*', '', cleaned_text, flags=re.MULTILINE)
    cleaned_text = re.sub(r'^>\s*', '', cleaned_text, flags=re.MULTILINE)
    cleaned_lines = [line.strip() for line in cleaned_text.splitlines()]
    cleaned_text = "\n".join(cleaned_lines)


    return cleaned_text.strip() #Strip leading/trailing whitespace from the whole result

"""
Overlap Strategy:
    It prioritizes splitting on larger separators (like \n\n) first.
    If a block between larger separators is still too big, it attempts to split on the next smaller separator (\n, ., etc.).
    If a block still cannot be split by any provided separators within the chunk_size, it falls back to simple character-based splitting.
    When a split occurs, the last chunk_overlap characters of the preceding segment are included at the beginning of the next segment to create the overlap.
"""
def split_text_recursively(text: str, separators: list[str], chunk_size: int, chunk_overlap: int):
    """
    Splits text recursively based on a list of separators.
    Handles overlap and tries to keep chunks within size limits while respecting separators.
    Returns a list of text chunks. This simplified version focuses on text.
    """
    final_chunks = []
   
    max_iterations = len(text) * 2 

    def _split(txt: str, s: list[str], iteration_count=0):
        if iteration_count > max_iterations:
             logger.error("Max iterations exceeded in recursive splitter. Possible infinite loop.")
             return

        if not txt:
            return

        if not s: 
            for i in range(0, len(txt), max(1, chunk_size - chunk_overlap)): 
                final_chunks.append(txt[i:i + chunk_size])
            return

        current_separator = s[0]
        other_separators = s[1:]

        if not current_separator: 
             for i in range(0, len(txt), max(1, chunk_size - chunk_overlap)):
                final_chunks.append(txt[i:i + chunk_size])
             return


        splits = txt.split(current_separator)
        temp_chunk = ""
        for i, split in enumerate(splits): 
            segment = split 
            if len(temp_chunk) + len(segment) > chunk_size and temp_chunk:
                 _split(temp_chunk, other_separators, iteration_count + 1)
               
                 overlap_text = temp_chunk[max(0, len(temp_chunk) - chunk_overlap):]
                 temp_chunk = overlap_text + segment
            else:
                temp_chunk += segment
        if temp_chunk:
            _split(temp_chunk, other_separators, iteration_count + 1)


    _split(text, separators)

    return [chunk for chunk in final_chunks if chunk.strip()]


def extract_chunks_with_metadata(md_text: str, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, separators=CHUNK_SEPARATORS):
    """
    Extracts chunks from markdown text, keeping original content, cleaning for embedding,
    and preserving heading context and extracting links in metadata.
    """
    if not md_text or not isinstance(md_text, str):
        logger.warning("Invalid markdown text input for chunking.")
        return []

    lines = md_text.splitlines()
    chunks_with_metadata = []
    current_headings = []
   
    current_block_lines = [] 

    logger.debug("Starting document processing for chunking.")
    for line_num, line in enumerate(lines):
        stripped_line = line.rstrip() 

       
        heading_match = re.match(r'^(#{1,6})\s+(.*)', stripped_line)
        if heading_match:
            
            if current_block_lines:
                block_text = "\n".join(current_block_lines)
                logger.debug(f"Processing text block before heading on line {line_num}. Length: {len(block_text)} chars.")
               
                temp_chunks = split_text_recursively(
                    block_text, separators, chunk_size, chunk_overlap
                )
                for chunk_content in temp_chunks:
                    if chunk_content.strip(): #Add non-empty chunks
                        chunks_with_metadata.append((
                            chunk_content,             
                            list(current_headings),    
                            extract_markdown_urls(chunk_content) 
                        ))
                current_block_lines = [] 

            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            current_headings = current_headings[:level-1] if level > 1 else []
            current_headings.append(heading_text)

            logger.debug(f"Line {line_num}: Heading detected: Level {level}, Text: '{heading_text}'. Current hierarchy: {current_headings}")

            
            heading_chunk_content = stripped_line 
            if len(heading_chunk_content) <= chunk_size: 
                 chunks_with_metadata.append((
                    heading_chunk_content,
                    list(current_headings),
                    extract_markdown_urls(heading_chunk_content) 
                 ))
            else:
                 logger.warning(f"Heading on line {line_num} is too long ({len(heading_chunk_content)} chars) to add as a distinct chunk.")

            continue 

        if stripped_line.startswith('[['):
             logger.debug(f"Skipping navigation line: {line_num}: {stripped_line[:50]}...")
             continue 

        if not stripped_line:
            if current_block_lines:
                block_text = "\n".join(current_block_lines)
                logger.debug(f"Processing text block on empty line {line_num}. Length: {len(block_text)} chars.")
                temp_chunks = split_text_recursively(
                    block_text, separators, chunk_size, chunk_overlap
                )
                for chunk_content in temp_chunks:
                    if chunk_content.strip():
                        chunks_with_metadata.append((
                            chunk_content,
                            list(current_headings),
                            extract_markdown_urls(chunk_content)
                        ))
                current_block_lines = [] #Reset buffer

            
            continue 

       
        current_block_lines.append(line) 

    if current_block_lines:
        block_text = "\n".join(current_block_lines)
        logger.debug(f"Processing remaining text block after loop. Length: {len(block_text)} chars.")
        temp_chunks = split_text_recursively(
            block_text, separators, chunk_size, chunk_overlap
        )
        for chunk_content in temp_chunks:
            if chunk_content.strip():
                chunks_with_metadata.append((
                    chunk_content,
                    list(current_headings),
                    extract_markdown_urls(chunk_content)
                ))


    logger.debug(f"Finished chunk extraction pass. Produced {len(chunks_with_metadata)} potential chunks.")

    return chunks_with_metadata


@retry(
    retry=retry_if_exception_type(httpx.RemoteProtocolError),
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=1, min=1, max=10),
)
def retried_insert_chunk(data: dict, table_name: str = "legal_vectors"):
    """
    Attempts to insert a single chunk of data into the specified Supabase table, with retries.
    Args:
        data (dict): The dictionary containing the chunk data (content, embedding, metadata, etc.).
        table_name (str): The name of the Supabase table.
    Returns:
        The response object from the successful execute() call.
    Raises:
        The exception if retries are exhausted.
    """
    if supabase is None:
        raise ConnectionError("Supabase client not initialized for retried insert.")

    logger.debug(f"Attempting Supabase insertion for chunk (first 100 content): '{data['content'][:100]}...'")
    response = supabase.table(table_name).insert(data).execute()
    logger.debug(f"Supabase insertion attempt successful.") #Log success after execute()

    return response


def ingest():
    files = glob.glob(os.path.join(data_dir, '*.md'))
    if not files:
        logger.warning(f"No markdown files found in {data_dir}. Exiting ingestion.")
        return

    logger.info(f"Found {len(files)} markdown files to ingest from {data_dir}.")

    for file_path in tqdm(files, desc="Ingesting markdown files"):
        logger.debug(f"Processing file: {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            continue 

        url_match = re.search(r'https?://[^\s)]+', text)
        source_url = url_match.group(0).split('#')[0] if url_match else None #Get base URL before #
        law_name = os.path.splitext(os.path.basename(file_path))[0]


        chunks_with_details = extract_chunks_with_metadata(
            text,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=CHUNK_SEPARATORS
        )

        if not chunks_with_details:
            logger.warning(f"No valid chunks found in {file_path} after processing.")
            continue 

        logger.debug(f"Extracted {len(chunks_with_details)} chunks from {file_path}.")

        for idx, (original_chunk_content, heading_hierarchy, extracted_urls) in enumerate(chunks_with_details):
            logger.debug(f"Processing chunk {idx+1}/{len(chunks_with_details)}: content='{original_chunk_content[:100]}...', hierarchy={heading_hierarchy}, urls={extracted_urls}")

            if not original_chunk_content or not original_chunk_content.strip():
                logger.warning(f"Empty original chunk content at index {idx} in {file_path}, skipping.")
                continue

            try:
                
                cleaned_content_for_embedding = clean_markdown_formatting(original_chunk_content)

                if not cleaned_content_for_embedding.strip():
                    logger.warning(f"Cleaned chunk content is empty/whitespace only at index {idx} in {file_path}, skipping embedding and storage.")
                    continue

               
                if len(cleaned_content_for_embedding) > CHUNK_SIZE * 1.5: 
                     logger.warning(f"Cleaned chunk content {idx} (file: {file_path}) is large ({len(cleaned_content_for_embedding)} chars), potentially impacting embedding quality.")
                   

                logger.debug(f"Generating embedding for cleaned chunk {idx} (len: {len(cleaned_content_for_embedding)})...")
                embedding = get_embedding(cleaned_content_for_embedding)

                if embedding is None:
                    logger.warning(f"Failed to generate embedding for chunk {idx} in {file_path} (cleaned len: {len(cleaned_content_for_embedding)}), skipping.")
                    continue

                if embedding.shape[-1] != EMBEDDING_DIMENSION:
                     logger.error(f"Embedding dimension mismatch for chunk {idx} in {file_path}! Expected {EMBEDDING_DIMENSION}, got {embedding.shape[-1]}. Skipping.")
                     continue

                embedding_list = embedding.tolist() 


                cleaned_heading_hierarchy = [
                    clean_markdown_formatting(h).strip() for h in heading_hierarchy if h and isinstance(h, str)
                ]
                cleaned_heading_hierarchy = [h for h in cleaned_heading_hierarchy if h]

                section_heading = cleaned_heading_hierarchy[-1] if cleaned_heading_hierarchy else None

                metadata = {
                    "source_file": os.path.basename(file_path),
                    "chunk_index": idx,
                    "law_name": law_name,
                    "section_heading": section_heading,
                    "heading_hierarchy": cleaned_heading_hierarchy,
                    "chunk_urls": extracted_urls, 
                }

               
                data = {
                    "content": original_chunk_content, 
                    "embedding": embedding_list,
                    "metadata": metadata,
                    "source_url": source_url 
                }
                logger.debug(f"Attempting insertion for chunk {idx+1} from {os.path.basename(file_path)}...")
                response = retried_insert_chunk(data) 

                if hasattr(response, 'data') and response.data:
                    inserted_id = response.data[0].get('id', 'N/A')
                    logger.debug(f"Successfully inserted chunk {idx+1} from {file_path} (section: {section_heading}). DB ID: {inserted_id}")
                else:
                    logger.error(f"Failed to insert chunk {idx+1} from {file_path} (section: {section_heading}). Supabase API returned unexpected response data or no data for insert.")
                    logger.debug(f"Full response object on potential insert failure: {response}")
                    logger.debug(f"Failed data attempt (first 100 content): '{data['content'][:100]}...', metadata={data['metadata']}, source_url={data['source_url']}")


            except Exception as e:
                logger.exception(f"An exception occurred during database insertion for chunk {idx+1} from {os.path.basename(file_path)} (section: {section_heading}): {str(e)}")
                logger.debug(f"Failed data attempt (first 100 content): '{data['content'][:100]}...', metadata={data['metadata']}, source_url={data['source_url']}")
                logger.debug(f"Problematic heading hierarchy: {heading_hierarchy}")
                logger.debug(f"Problematic extracted URLs: {extracted_urls}")


        logger.debug(f"Finished processing file: {file_path}")

    logger.info("Ingestion process completed.")

if __name__ == "__main__":
    if not logging.getLogger().handlers:
        
        print("Configuring basic logging for standalone script execution.", file=sys.stderr)
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

            logger = get_logger(__name__, subsystem="ingestion")
            logger.debug("Basic logging configured for standalone script.")
            logger.info(f"Standalone ingestion logs will be written to: {LOG_FILE_PATH}")
        except Exception as e:
            print(f"FATAL ERROR: Failed to configure basic logging for standalone script: {e}", file=sys.stderr)
            sys.exit(1)

    logger.info("Starting ingestion script execution via __main__.") 

    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
             logger.error("Supabase credentials (SUPABASE_URL, SUPABASE_KEY) not loaded from environment variables.")
             print("FATAL ERROR: Supabase credentials not loaded.", file=sys.stderr)
             sys.exit(1)

        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client initialized for ingestion (in __main__).")
    except Exception as e:
        logger.exception("Failed to initialize Supabase client for ingestion (in __main__).")
        print(f"FATAL ERROR: Failed to initialize Supabase client: {e}", file=sys.stderr)
        sys.exit(1)

    ingest()
    logger.info("Ingestion script finished.")

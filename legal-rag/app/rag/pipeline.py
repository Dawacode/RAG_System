from app.rag.retriever import retrieve
from app.rag.generator import call_gemma3, tokenizer as gemma_tokenizer, model as gemma_model
from scripts.ingest_supabase import clean_markdown_formatting, extract_markdown_urls
from app.utils.logger import get_logger
from app.utils.config import RETRIEVAL_TOP_K, RETRIEVAL_THRESHOLD, RETRIEVAL_PROBES 


logger = get_logger(__name__, subsystem="app")



def format_references(records: list[dict] | None) -> str:
    """
    Formats retrieved records into a human-readable reference list,
    including URLs extracted from chunk metadata.
    Args:
        records: A list of dictionaries, where each dictionary represents a retrieved document.
                 Expected to contain 'content', 'metadata', 'source_url', and 'similarity'.
                 Metadata is expected to have 'chunk_urls' (list of strings),
                 'law_name', 'section_heading'.
    Returns:
        A formatted string suitable for appending to the LLM's answer.
    """
    if not records:
        logger.debug("format_references called with no records.")
        return ""

    logger.debug(f"Formatting {len(records)} records into references.")
    refs = []
  
    unique_refs = {}

    for i, rec in enumerate(records):
        rec_id = rec.get("id") 
        key = rec_id if rec_id is not None else f"{rec.get('source_url', '')}_{rec.get('metadata', {}).get('chunk_index', i)}_{i}" 

        if key in unique_refs:
                    logger.debug(f"Skipping duplicate reference for key: {key}")
                    continue
            
        meta = rec.get("metadata", {})
        source_url_doc = rec.get("source_url", '').strip() 
        chunk_urls = meta.get("chunk_urls", [])

        law_name = meta.get("law_name", 'Okänd källa')
        section_heading = meta.get("section_heading", '')

       
        ref_parts = [law_name]
        if section_heading:
            ref_parts.append(section_heading)

        all_urls = []
        for url in chunk_urls:
            if isinstance(url, str) and url.strip():
                cleaned_url = url.strip()
              
                if cleaned_url:
                    all_urls.append(cleaned_url)

      
        if source_url_doc and source_url_doc not in all_urls and (source_url_doc.startswith('http') or source_url_doc.startswith('/')):
             all_urls.insert(0, source_url_doc) 

        unique_urls = []
        for url in all_urls:
            if url not in unique_urls:
                unique_urls.append(url)

        urls_str = ", ".join(unique_urls) if unique_urls else "URL saknas"
        desc = " - ".join(ref_parts) if ref_parts else law_name
        unique_refs[key] = f"{desc} ({urls_str})"

        logger.debug(f"Added unique reference for key {key}: {unique_refs[key]}") 

    formatted_refs_list = []
    for i, (key, ref_desc) in enumerate(unique_refs.items(), 1):
         formatted_refs_list.append(f"[{i}] {ref_desc}")


    formatted_text = "\n".join(formatted_refs_list)
    logger.info(f"Formatted {len(formatted_refs_list)} unique references from {len(records)} retrieved records.")
    return formatted_text


RAG_SYSTEM_PROMPT = """Du är en AI-assistent specialiserad på svensk juridik. Svara på följande juridiska fråga *endast* baserat på informationen i den tillhandahållna kontexten från hämtade dokument. Om svaret inte finns i kontexten, ange det tydligt. Var noggrann.""" 

EXAMPLE_QUERY = "Vad är ett formalavtal?" 
EXAMPLE_REASONING = """1.  *Identifiering av Nyckelbegrepp:* Det centrala begreppet är \"formalavtal\", vilket skiljer sig från konsensualavtal. Ett formalavtal kräver en specifik form för att vara giltigt.
2.  *Förklaring av Relevanta Stadgar/Principer:* Svensk lag innehåller krav på form för vissa avtalstyper, såsom fastighetsköp i Jordabalken eller ingående av äktenskap.
3.  *Logiska Resonemangssteg:* För ett formalavtal är överenskommelse inte tillräckligt för bindande verkan; avtalet måste även uppfylla lagens formkrav. Om formkravet inte är uppfyllt, är avtalet ogiltigt.
4.  *Överväganden av Undantag eller Nyanser:* Många avtal är konsensualavtal (giltiga oavsett form), men formalavtalen är uttryckliga undantag där formen är konstituerande.
5.  *Sammanfattande Slutsats:* Ett formalavtal är ett avtal som enligt lag kräver en viss form (oftast skriftlig) för att vara juridiskt bindande."""
EXAMPLE_ANSWER = "Ett formalavtal är ett avtal som enligt lag kräver en viss form (oftast skriftlig) för att vara juridiskt bindande." 
EXAMPLE_OUTPUT_FORMATTED = f"""<reasoning>
{EXAMPLE_REASONING}
</reasoning>
<answer>
{EXAMPLE_ANSWER}
</answer>"""

def rag_pipeline(query: str) -> dict:
    """
    Executes the RAG pipeline: Retrieve relevant documents and generate an answer.

    Args:
        query: The user's legal question in Swedish.

    Returns:
        A dictionary containing:
        - 'answer': The final formatted answer string with references.
        - 'retrieved_records': List of retrieved documents.
        - 'metrics': Dict with retrieval_time, generation_time, prompt_token_count, generated_token_count.
        Returns a dictionary with an error answer if pipeline fails before generation.
    """
    logger.info(f"Received query: {query}")
    
    results = {
        'answer': "Ett internt fel inträffade under bearbetningen.", 
        'retrieved_records': [],
        'metrics': {
            'retrieval_time': 0.0,
            'generation_time': 0.0,
            'prompt_token_count': 0,
            'generated_token_count': 0,
        }
    }

    try:
        retrieved_records, retrieval_time = retrieve(query, top_k=RETRIEVAL_TOP_K, threshold=RETRIEVAL_THRESHOLD, probes=RETRIEVAL_PROBES)
        results['retrieved_records'] = retrieved_records
        results['metrics']['retrieval_time'] = retrieval_time

        context_text = ""
        records_for_reference = [] 

        if not retrieved_records:
            logger.warning("No relevant documents found for the query.")
            results['answer'] = "Jag kunde inte hitta relevanta juridiska dokument för att besvara din fråga baserat på tillgänglig information."
            return results
        else:
            context_parts = []
            for i, rec in enumerate(retrieved_records):
               
                original_chunk_content = rec.get('content', '')
                cleaned_chunk_content = clean_markdown_formatting(original_chunk_content) 

                if not cleaned_chunk_content.strip():
                    logger.warning(f"Retrieved chunk {i} (ID: {rec.get('id', 'N/A')}) had empty cleaned content after formatting. Skipping.")
                    continue 

                meta = rec.get("metadata", {})
                source_info = f"Källa [{i+1}]: {meta.get('law_name', '')} - {meta.get('section_heading', '') or 'Ingen rubrik'}" 

                context_parts.append(f"--- START DOKUMENT {i+1} ---\n{source_info}\nInnehåll:\n{cleaned_chunk_content}\n--- SLUT DOKUMENT {i+1} ---")

            if not context_parts:
                logger.warning("All retrieved chunks resulted in empty cleaned content. Cannot build context.")
                return "Jag hittade relevanta dokument, men kunde inte bearbeta innehållet för att svara på din fråga."

            context_text = "\n\n".join(context_parts)
            records_for_reference = retrieved_records 


        if gemma_model is None:
            logger.error("Generator model is not loaded. Cannot check max length.")
            max_model_tokens = None
        else:
             if hasattr(gemma_model.config, 'max_position_embeddings'):
                 max_model_tokens = gemma_model.config.max_position_embeddings
             elif hasattr(gemma_model, 'max_seq_length'):
                  max_model_tokens = gemma_model.max_seq_length
             else:
                  logger.warning("Model object or config does not have 'max_position_embeddings' or 'max_seq_length'. Cannot determine model max length.")
                  max_model_tokens = None

        if max_model_tokens is None:
             max_prompt_tokens = 4096
             logger.warning(f"Could not determine model max length, assuming default for prompt length check: {max_prompt_tokens}")
        else:
            max_prompt_tokens = max_model_tokens 

       
        actual_user_instructions = f"""Svara på svenska. Din uppgift är att generera en väl genomtänkt respons på den givna juridiska frågan, baserad *enbart* på informationen i kontexten. Om kontexten inte räcker, ange det tydligt inom svarsdelen. Din respons ska strikt följa det format som specificeras nedan.

Använd *endast* följande kontext för att svara på frågan:
Kontext:
{context_text}

Fråga: {query}

Inkludera en detaljerad kedja-av-tankar (CoT) som steg för steg förklarar hur du kom fram till svaret *utifrån kontexten*. Din förklaring ska inkludera, baserat på kontexten:

1.  *Identifiering av Nyckelbegrepp:* Identifiera och förklara de viktigaste juridiska termerna och principerna som finns i kontexten relaterade till frågan.
2.  *Förklaring av Relevanta Stadgar/Principer:* Beskriv de relevanta juridiska principerna, stadgarna eller lagrum som finns i kontexten och deras rättsliga betydelse för frågan.
3.  *Logiska Resonemangssteg:* Skissera resonemangsprocessen i en klar, logisk följd. Förklena hur de juridiska principerna från kontexten kopplar till slutsatsen.
4.  *Överväganden av Undantag eller Nyanser:* Om kontexten innehåller relevant information, notera eventuella undantag, nyanser eller olika tolkningar som kan påverka svaret.
5.  *Sammanfattande Slutsats:* Avsluta med en kort sammanfattning som knyter ihop resonemanget baserat på kontexten och motiverar det slutliga svaret.

Din respons ska vara strukturerad, tydlig och använda numrerade eller punktlistor om nödvändigt *inom resonemangsdelen*. Se till att din förklaring är omfattande *utifrån kontexten*.

Inkludera ingen ytterligare kommentar före eller efter det specificerade formatet. Fokusera enbart på resonemangsprocessen och svaret baserat på kontexten.

Respond in the following format:
<reasoning>
</reasoning>
<answer>
</answer>
""" 
        messages = [
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": EXAMPLE_QUERY},
            {"role": "model", "content": EXAMPLE_OUTPUT_FORMATTED},

            {"role": "user", "content": actual_user_instructions}, 
        ]

       
        if gemma_tokenizer is None or gemma_model is None: 
            logger.error("Gemma tokenizer or model is not loaded in generator. Cannot format prompt or estimate length.")
            return "Fel: Modellen för att generera svar kunde inte laddas korrekt."

        prompt_string = gemma_tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        logger.debug(f"Formatted prompt string using chat template (start): {prompt_string[:300]}...")
        logger.debug(f"Formatted prompt string length: {len(prompt_string)}")

       
        prompt_tokens = gemma_tokenizer(prompt_string).input_ids
        results['metrics']['prompt_token_count'] = len(prompt_tokens) 

       
        if max_model_tokens is not None and results['metrics']['prompt_token_count'] >= max_model_tokens:
            logger.warning(f"Constructed prompt token count ({results['metrics']['prompt_token_count']}) >= model's max length ({max_model_tokens}). Input will be truncated. Response might be incomplete or formatting may fail.")

      
        raw_response_text, generation_time, gen_input_tokens, generated_token_count = call_gemma3(prompt_string)
        results['metrics']['generation_time'] = generation_time
       
        results['metrics']['generated_token_count'] = generated_token_count


      
        final_answer_text = raw_response_text.strip()

        if retrieved_records: 
             logger.debug("Formatting references to append.")
             formatted_refs = format_references(retrieved_records) 
             if formatted_refs:
                 if not final_answer_text.endswith('\n'):
                     final_answer_text += '\n'
                 final_answer_text += "\nReferenser:\n" + formatted_refs
                 logger.info("Appended formatted references to the final answer.")
             else:
                 logger.warning("Retrieved records provided, but reference formatting yielded empty text.")

        results['answer'] = final_answer_text

    except Exception as e:
       
        logger.exception("An error occurred during text generation or response processing in pipeline.")
       

    return results 

DROP FUNCTION IF EXISTS match_legal_vectors;

CREATE OR REPLACE FUNCTION match_legal_vectors (
  query_embedding vector(384), 
  match_threshold float,       
  match_count int            
)
RETURNS TABLE (
  id UUID,                  
  content text,
  metadata jsonb,
  source_url text,
  similarity float          
)
LANGUAGE sql STABLE
AS $$
  SELECT
    lv.id,
    lv.content,
    lv.metadata,
    lv.source_url,
    1 - (lv.embedding <=> query_embedding) AS similarity 
  FROM
    legal_vectors lv
  WHERE
    (1 - (lv.embedding <=> query_embedding)) > match_threshold
  ORDER BY
    lv.embedding <=> query_embedding ASC
  LIMIT match_count; 
$$;

GRANT EXECUTE ON FUNCTION match_legal_vectors TO authenticated;

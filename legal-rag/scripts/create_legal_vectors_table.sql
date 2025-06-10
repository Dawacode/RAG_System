CREATE EXTENSION IF NOT EXISTS vector;
DROP INDEX IF EXISTS legal_vectors_embedding_idx;
DROP TABLE IF EXISTS legal_vectors;
DROP FUNCTION IF EXISTS match_legal_vectors;


-- Create the table with the new vector dimension (1024)
CREATE TABLE legal_vectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    embedding VECTOR(1024), 
    metadata JSONB,
    source_url TEXT,
    inserted_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now())
);

ALTER TABLE legal_vectors ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow authenticated read" ON legal_vectors FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Allow authenticated insert" ON legal_vectors FOR INSERT WITH CHECK (auth.role() = 'authenticated');

CREATE OR REPLACE FUNCTION match_legal_vectors (
  query_embedding vector(1024), 
  match_threshold float,        
  match_count int,             
  probes int                    
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
  SET LOCAL ivfflat.probes = probes;

  SELECT
    lv.id,
    lv.content,
    lv.metadata,
    lv.source_url,
    1 - (lv.embedding <=> query_embedding) AS similarity -- Calculate cosine similarity (1 - cosine distance)
  FROM
    legal_vectors lv
  WHERE
    (1 - (lv.embedding <=> query_embedding)) > match_threshold
  ORDER BY
    lv.embedding <=> query_embedding ASC
  LIMIT match_count; 
$$;


GRANT EXECUTE ON FUNCTION match_legal_vectors TO authenticated;

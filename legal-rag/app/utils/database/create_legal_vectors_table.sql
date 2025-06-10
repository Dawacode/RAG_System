DROP INDEX IF EXISTS legal_vectors_embedding_idx;
DROP TABLE IF EXISTS legal_vectors;


CREATE EXTENSION IF NOT EXISTS vector;

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
CREATE INDEX legal_vectors_embedding_idx ON legal_vectors USING ivfflat (embedding vector_cosine_ops) WITH (lists = 500);

DROP FUNCTION IF EXISTS match_legal_vectors;

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
  SELECT
    lv.id,
    lv.content,
    lv.metadata,
    lv.source_url,
    1 - (lv.embedding <=> query_embedding) AS similarity 
  FROM
    legal_vectors lv
  WHERE
    ivfflat.probes(lv.embedding, query_embedding, probes) AND (1 - (lv.embedding <=> query_embedding)) > match_threshold
  ORDER BY
    lv.embedding <=> query_embedding ASC 
  LIMIT match_count; 
$$;

CREATE OR REPLACE FUNCTION set_statement_timeout(timeout text)
RETURNS void AS $$
BEGIN
    EXECUTE format('SET statement_timeout = %L', timeout);
END;
$$ LANGUAGE plpgsql VOLATILE; 

GRANT EXECUTE ON FUNCTION match_legal_vectors TO authenticated;
GRANT EXECUTE ON FUNCTION set_statement_timeout TO authenticated;
GRANT SELECT ON TABLE legal_vectors TO authenticated;

GRANT INSERT ON TABLE legal_vectors TO authenticated;

ALTER DATABASE legal_vector SET statement_timeout = '60s'; 
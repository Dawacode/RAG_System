-- Create a GIN index on the tsvector column
CREATE INDEX CONCURRENTLY legal_vectors_content_tsvector_idx
ON legal_vectors
USING GIN(content_tsvector)
WITH (fastupdate = off);
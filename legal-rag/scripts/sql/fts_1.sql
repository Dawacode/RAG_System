ALTER TABLE legal_vectors DROP COLUMN IF EXISTS content_tsvector;
ALTER TABLE legal_vectors
ADD COLUMN content_tsvector TSVECTOR
GENERATED ALWAYS AS (to_tsvector('swedish', content)) STORED;

CREATE OR REPLACE FUNCTION match_legal_keywords (
  query_text TEXT,
  match_count INT
)
RETURNS TABLE (
  id UUID,
  content TEXT,
  metadata JSONB,
  source_url TEXT,
  rank FLOAT
)
LANGUAGE SQL STABLE
AS $$
  SELECT
    lv.id,
    lv.content,
    lv.metadata,
    lv.source_url,
    ts_rank_cd(lv.content_tsvector, websearch_to_tsquery('swedish', query_text), 32) AS rank
  FROM
    legal_vectors lv
  WHERE
    lv.content_tsvector @@ websearch_to_tsquery('swedish', query_text)
  ORDER BY
    rank DESC
  LIMIT match_count;
$$;

-- Grant execution permission to authenticated users
GRANT EXECUTE ON FUNCTION match_legal_keywords TO authenticated;
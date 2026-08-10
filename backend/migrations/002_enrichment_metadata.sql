-- ============================================================================
-- Migración 002 — Metadatos de calidad del enriquecimiento
-- ----------------------------------------------------------------------------
-- Contexto: se reemplaza Supadata por youtube_transcript_api + yt_dlp, que
-- corren en local (IP residencial). A diferencia de Supadata —que hacía
-- fallback a Whisper y devolvía texto puntuado— youtube_transcript_api
-- devuelve los subtítulos tal como están en YouTube:
--
--   · subtítulos MANUALES  (subidos por el creador) → suelen tener puntuación
--   · subtítulos AUTOMÁTICOS (ASR de YouTube)       → SIN puntuación
--
-- Esa diferencia cambia por completo qué señales lingüísticas son calculables,
-- así que hay que guardarla como dato, no descubrirla después.
--
-- Idempotente: se puede correr varias veces sin romper nada.
-- ============================================================================

BEGIN;

ALTER TABLE content_items
    -- ── Procedencia y calidad de la transcripción ───────────────────────────
    ADD COLUMN IF NOT EXISTS transcript_is_generated BOOLEAN,       -- true = ASR automático (sin puntuación)
    ADD COLUMN IF NOT EXISTS transcript_lang         VARCHAR(10),   -- 'es', 'en', 'es-419', …
    ADD COLUMN IF NOT EXISTS transcript_source       VARCHAR(20),   -- 'youtube_manual' | 'youtube_auto' | 'supadata'
    ADD COLUMN IF NOT EXISTS transcript_word_count   INTEGER,       -- precalculado: evita recontar en cada consulta
    ADD COLUMN IF NOT EXISTS transcript_segments     JSONB,         -- segmentos crudos [{text,start,duration}] — permite
                                                                    -- recalcular ritmo, pausas y densidad temporal sin
                                                                    -- volver a pedir nada a YouTube

    -- ── Metadatos que la YouTube Data API no da y yt_dlp sí ─────────────────
    ADD COLUMN IF NOT EXISTS chapters      JSONB,      -- [{title,start_time,end_time}] → eje de estructura
    ADD COLUMN IF NOT EXISTS n_chapters    INTEGER,
    ADD COLUMN IF NOT EXISTS upload_date   DATE,
    ADD COLUMN IF NOT EXISTS channel_id    VARCHAR(50),
    ADD COLUMN IF NOT EXISTS video_language VARCHAR(10),

    -- ── Trazabilidad del proceso de enriquecimiento ─────────────────────────
    ADD COLUMN IF NOT EXISTS enrichment_status VARCHAR(20),   -- 'ok' | 'partial' | 'failed'
    ADD COLUMN IF NOT EXISTS enrichment_error  TEXT,
    ADD COLUMN IF NOT EXISTS enriched_at       TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS enricher_version  VARCHAR(20);

-- Backfill: las 6 transcripciones que ya existen vienen de Supadata (Whisper),
-- que sí puntúa. Marcarlas para no mezclarlas con las nuevas en el análisis.
UPDATE content_items
   SET transcript_source = 'supadata',
       transcript_is_generated = true
 WHERE transcript IS NOT NULL
   AND length(transcript) > 0
   AND transcript_source IS NULL;

-- Word count para las que ya están
UPDATE content_items
   SET transcript_word_count = array_length(regexp_split_to_array(trim(transcript), '\s+'), 1)
 WHERE transcript IS NOT NULL AND length(transcript) > 0
   AND transcript_word_count IS NULL;

CREATE INDEX IF NOT EXISTS idx_content_items_enrichment
    ON content_items(enrichment_status);

COMMIT;

-- ============================================================================
-- Verificación:
--   SELECT enrichment_status, transcript_source, count(*)
--     FROM content_items GROUP BY 1,2 ORDER BY 1,2;
--
--   -- ¿Cuántas transcripciones tienen puntuación utilizable?
--   SELECT transcript_source, transcript_is_generated, count(*),
--          round(avg(transcript_word_count)) AS palabras_medias,
--          count(*) FILTER (WHERE transcript LIKE '%.%') AS con_puntos
--     FROM content_items WHERE transcript IS NOT NULL GROUP BY 1,2;
-- ============================================================================

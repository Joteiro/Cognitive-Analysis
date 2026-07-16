-- ============================================================================
-- Migración 001 — Esquema de 3 capas (medallion: bronze / silver / gold)
-- ----------------------------------------------------------------------------
-- ESTADO: YA APLICADA en Supabase (proyecto "Cognitive") el 2026-07-16.
-- Este archivo documenta el esquema real "as-built" y sirve para reproducir
-- la base desde cero. Refleja exactamente las tablas que existen hoy y que
-- los modelos SQLAlchemy (models.py) esperan.
--
--   raw_events     (bronze) — ingesta cruda e inmutable. Append-only.
--   content_items  (silver) — un ítem de contenido limpio por (source, external_id).
--   content_scores (gold)   — historial de scores. Una fila por corrida del scorer.
--
-- Requiere PostgreSQL. Correr ANTES de desplegar el código que usa estas tablas.
-- ============================================================================

BEGIN;

-- ── 1. NUEVAS TABLAS ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS raw_events (
    id          BIGSERIAL PRIMARY KEY,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source      VARCHAR(20) NOT NULL DEFAULT 'youtube',   -- 'chrome_extension' | ...
    payload     JSONB       NOT NULL                       -- el POST verbatim de la extensión
);

CREATE TABLE IF NOT EXISTS content_items (
    id                    BIGSERIAL PRIMARY KEY,
    source                VARCHAR(20)  NOT NULL DEFAULT 'youtube',  -- plataforma
    external_id           VARCHAR(100) UNIQUE NOT NULL,             -- id nativo (youtube_id, etc.)
    url                   TEXT NOT NULL,
    title                 TEXT NOT NULL,
    channel               TEXT,
    duration_seconds      INTEGER,
    description           TEXT,
    tags                  JSONB,
    category_id           VARCHAR(10),
    category_name         VARCHAR(50),
    view_count            BIGINT,
    like_count            INTEGER,
    comment_count         INTEGER,
    stats_fetched_at      TIMESTAMPTZ,
    transcript            TEXT,
    transcript_fetched_at TIMESTAMPTZ,
    watched_at            TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS content_scores (
    id              BIGSERIAL PRIMARY KEY,
    content_item_id BIGINT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
    scorer_version  VARCHAR(20) NOT NULL DEFAULT '1.0',   -- versión del algoritmo
    score_letter    CHAR(1),
    score_numeric   FLOAT,
    score_labels    JSONB,
    score_details   JSONB,
    scored_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_content_scores_item_id    ON content_scores(content_item_id);
CREATE INDEX IF NOT EXISTS idx_content_items_external_id ON content_items(external_id);


-- ── 2. BACKFILL: videos (esquema viejo) → content_items ─────────────────────

INSERT INTO content_items (
    source, external_id, url, title, channel,
    duration_seconds, description, tags,
    category_id, category_name,
    view_count, like_count, comment_count,
    transcript, watched_at, created_at, updated_at
)
SELECT
    'youtube', youtube_id, url, title, channel,
    duration, description,
    CASE WHEN tags IS NOT NULL AND tags != '' THEN tags::jsonb ELSE NULL END,
    category_id, category_name,
    view_count, like_count, comment_count,
    transcript, watched_at,
    COALESCE(created_at, now()), COALESCE(created_at, now())
FROM videos
ON CONFLICT (external_id) DO NOTHING;


-- ── 3. BACKFILL: scores → content_scores ────────────────────────────────────

INSERT INTO content_scores (
    content_item_id, scorer_version,
    score_letter, score_numeric, score_labels, score_details, scored_at
)
SELECT
    ci.id, '1.0',
    v.score_letter, v.score_numeric,
    CASE WHEN v.score_labels  IS NOT NULL AND v.score_labels  != '' THEN v.score_labels::jsonb  ELSE NULL END,
    CASE WHEN v.score_details IS NOT NULL AND v.score_details != '' THEN v.score_details::jsonb ELSE NULL END,
    COALESCE(v.created_at, now())
FROM videos v
JOIN content_items ci ON ci.external_id = v.youtube_id
WHERE v.score_letter IS NOT NULL;


-- ── 4. BACKFILL: raw_events (reconstruido desde videos) ─────────────────────

INSERT INTO raw_events (received_at, source, payload)
SELECT
    COALESCE(watched_at, created_at, now()),
    'chrome_extension',
    jsonb_build_object(
        'video_id',         youtube_id,
        'title',            title,
        'url',              url,
        'channel',          channel,
        'duration_seconds', duration,
        'tracked_at',       COALESCE(watched_at, created_at)
    )
FROM videos;


-- ── 5. RENOMBRAR TABLA VIEJA (respaldo, no se borra) ────────────────────────

ALTER TABLE videos RENAME TO videos_deprecated;


-- ── 6. SEGURIDAD: activar Row Level Security ────────────────────────────────
-- Sin políticas → bloquea a los roles anon/authenticated (clave pública).
-- El backend usa el rol 'postgres', que ignora RLS, así que sigue funcionando.

ALTER TABLE raw_events     ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_items  ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_scores ENABLE ROW LEVEL SECURITY;

COMMIT;

-- ============================================================================
-- Verificación:
--   SELECT count(*) FROM videos_deprecated;  -- 85 (respaldo original)
--   SELECT count(*) FROM content_items;       -- 85
--   SELECT count(*) FROM content_scores;      -- 82 (los que tenían score)
--
-- Cuando estés tranquilo:  DROP TABLE videos_deprecated;
-- ============================================================================

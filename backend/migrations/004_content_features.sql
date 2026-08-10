-- ============================================================================
-- Migración 004 — Tabla de descriptores (la "etiqueta nutricional")
-- ----------------------------------------------------------------------------
-- Una fila por (video, versión del calculador). Guarda los INDICADORES CRUDOS
-- —todos normalizados por 100 palabras o por minuto— y, aparte, el nivel
-- bajo/medio/alto de cada eje.
--
-- DECISIONES DE DISEÑO, para que se puedan defender:
--
--  1. NADA se mide en total: todo va por 100 palabras o por minuto. Un total
--     mide duración disfrazada, que era el defecto del scorer v1 (la
--     correlación entre su puntuación y el log de la duración era 0,73).
--
--  2. NO hay pesos. El nivel de un eje es la MEDIANA de los tercios de sus
--     indicadores. No hay ningún número arbitrario que justificar.
--
--  3. Los cortes bajo/medio/alto son TERCIOS DEL PROPIO CORPUS, no umbrales
--     absolutos. "Alta densidad" significa "alta respecto de lo que hay en
--     esta muestra", y así hay que decirlo en la interfaz.
--
--  4. No se agrega nada entre ejes. No hay letra, no hay puntuación única.
--     La valoración la pone el usuario según su objetivo, no el sistema.
--
--  5. Cada indicador viene con su flag de disponibilidad. Un dato ausente se
--     muestra como "no disponible", nunca se rellena con un valor neutro.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS content_features (
    id                    BIGSERIAL PRIMARY KEY,
    content_item_id       BIGINT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
    features_version      VARCHAR(20) NOT NULL,
    computed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- ── Contexto / calidad del insumo ───────────────────────────────────────
    n_words               INTEGER,
    duration_seconds      INTEGER,
    lang                  VARCHAR(10),
    transcript_source     VARCHAR(20),
    has_punctuation       BOOLEAN,      -- los subtítulos automáticos NO la tienen
    has_description       BOOLEAN,
    has_tags              BOOLEAN,

    -- ── Eje 1 · Densidad informativa ────────────────────────────────────────
    cifras_100w           REAL,
    ejemplos_1000w        REAL,
    fuentes_1000w         REAL,

    -- ── Eje 2 · Carga cognitiva ─────────────────────────────────────────────
    palabras_por_minuto   REAL,
    mattr                 REAL,         -- diversidad léxica, ventana fija de 200
    palabras_por_frase    REAL,         -- NULL si no hay puntuación real

    -- ── Eje 3 · Optimización para retención ─────────────────────────────────
    enganche_1000w        REAL,         -- suscribite, campanita, patrocinado…
    preguntas_1000w       REAL,         -- NULL si no hay puntuación
    repeticion            REAL,         -- bigramas repetidos en ventana fija

    -- ── Eje 4 · Trazabilidad y estructura ───────────────────────────────────
    n_links               INTEGER,
    n_links_verificables  INTEGER,      -- doi, arxiv, pubmed, .edu, prensa…
    n_links_comerciales   INTEGER,
    n_chapters            INTEGER,
    desc_words            INTEGER,

    -- ── Eje 5 · Correspondencia promesa ↔ contenido ─────────────────────────
    cobertura_promesa     REAL,         -- % del vocabulario de título+tags que
                                        -- aparece realmente en la transcripción

    -- ── Niveles por eje (mediana de los tercios de sus indicadores) ─────────
    nivel_densidad        VARCHAR(6),   -- bajo | medio | alto | NULL
    nivel_carga           VARCHAR(6),
    nivel_retencion       VARCHAR(6),
    nivel_trazabilidad    VARCHAR(6),
    nivel_correspondencia VARCHAR(6),

    UNIQUE (content_item_id, features_version)
);

CREATE INDEX IF NOT EXISTS idx_content_features_item
    ON content_features(content_item_id);
CREATE INDEX IF NOT EXISTS idx_content_features_version
    ON content_features(features_version);

ALTER TABLE content_features ENABLE ROW LEVEL SECURITY;

COMMIT;

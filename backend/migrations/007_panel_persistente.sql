-- 007_panel_persistente.sql          APLICADA el 2026-08-13 sobre Supabase.
--
-- Prepara content_features para guardar el panel.
--
-- POR QUE
-- -------
-- Hasta ahora /panel calculaba los 8 descriptores en cada request y no
-- guardaba nada: content_features tenia 0 filas. El sistema no tenia memoria
-- de lo que media. Para la memoria del TFM hace falta poder decir "de los N
-- videos de mi historial, la distribucion de percentiles fue tal", y no habia
-- tabla que consultar.
--
-- POR QUE COLUMNAS NUEVAS Y NO LAS QUE YA ESTABAN
-- ----------------------------------------------
-- La tabla venia de la epoca del scorer A-E: palabras_por_minuto, mattr,
-- fuentes_1000w, enganche_1000w. Los descriptores vigentes se llaman
-- ritmo_ppm, mattr_200, atribucion_1000w, conectores_1000w — y NO son lo
-- mismo, aunque se parezcan: mattr_200 fija la ventana en 200 tokens
-- justamente porque mattr a secas caia con la duracion.
--
-- Meter valores nuevos en columnas viejas seria repetir el error que este
-- proyecto viene persiguiendo: que el instrumento se cuele en la medida sin
-- que nada avise. Las viejas se conservan con COMMENT de obsoletas.

BEGIN;

-- ── contexto de la medicion ────────────────────────────────────────────────
ALTER TABLE content_features
    -- Contra que escala se midio. Sin esto, una fila de agosto y una de
    -- octubre pueden tener el mismo percentil y no significar lo mismo.
    ADD COLUMN IF NOT EXISTS frame_version varchar(40),

    -- Tres de los ocho descriptores se comparan por formato y no contra el
    -- corpus entero, asi que el percentil no se puede leer sin saber cual.
    ADD COLUMN IF NOT EXISTS formato varchar(40),

    -- El panel completo tal como lo devolvio el endpoint: estado, unidad y
    -- ambito por descriptor. Lo que no entra en columnas.
    ADD COLUMN IF NOT EXISTS panel jsonb,

    -- El gate de la capa 0. Guardar los NO aptos tambien importa: el hallazgo
    -- de que los formatos difieren mas en SI se pueden medir que en COMO
    -- puntuan se sostiene justamente sobre estas filas.
    ADD COLUMN IF NOT EXISTS apto boolean,
    ADD COLUMN IF NOT EXISTS cobertura_transcripcion real,
    ADD COLUMN IF NOT EXISTS motivo_no_apto varchar(60);

-- ── los 8 descriptores vigentes, valor crudo + percentil ───────────────────
-- En columnas y no solo en el jsonb para que la memoria se escriba con SQL
-- normal y no con extraccion de json.
ALTER TABLE content_features
    ADD COLUMN IF NOT EXISTS ritmo_ppm real,
    ADD COLUMN IF NOT EXISTS ritmo_ppm_pct real,
    ADD COLUMN IF NOT EXISTS cifras_100w_pct real,           -- cifras_100w ya existia
    ADD COLUMN IF NOT EXISTS atribucion_1000w real,
    ADD COLUMN IF NOT EXISTS atribucion_1000w_pct real,
    ADD COLUMN IF NOT EXISTS mattr_200 real,
    ADD COLUMN IF NOT EXISTS mattr_200_pct real,
    ADD COLUMN IF NOT EXISTS conectores_1000w real,
    ADD COLUMN IF NOT EXISTS conectores_1000w_pct real,
    ADD COLUMN IF NOT EXISTS enlaces_externos real,
    ADD COLUMN IF NOT EXISTS enlaces_externos_pct real,
    ADD COLUMN IF NOT EXISTS promocional_1000w real,
    ADD COLUMN IF NOT EXISTS promocional_1000w_pct real,
    ADD COLUMN IF NOT EXISTS cobertura_titulo real,
    ADD COLUMN IF NOT EXISTS cobertura_titulo_pct real;

-- Una fila por video, que se pisa al recalcular. Sin esto, cada vez que se
-- abre el mismo video se acumula una fila mas y la tabla deja de servir para
-- contar.
CREATE UNIQUE INDEX IF NOT EXISTS ux_content_features_item
    ON content_features (content_item_id);
CREATE INDEX IF NOT EXISTS ix_content_features_frame
    ON content_features (frame_version);

COMMENT ON COLUMN content_features.panel IS
    'Panel completo devuelto por GET /panel: por descriptor, valor + percentil + estado.';
COMMENT ON COLUMN content_features.frame_version IS
    'Version de escala_referencia.json usada. Los percentiles solo son comparables dentro de la misma.';
COMMENT ON COLUMN content_features.ritmo_ppm_pct IS
    'Percentil 0-100 dentro del corpus indicado por frame_version.';

COMMENT ON COLUMN content_features.nivel_densidad IS
    'OBSOLETO: scorer A-E v1.0, jubilado el 2026-08-13. Se conserva por historia.';
COMMENT ON COLUMN content_features.palabras_por_minuto IS
    'OBSOLETO: vocabulario del scorer A-E v1.0. El descriptor vigente es ritmo_ppm.';
COMMENT ON COLUMN content_features.fuentes_1000w IS
    'OBSOLETO: vocabulario del scorer A-E v1.0. El vigente es atribucion_1000w.';
COMMENT ON COLUMN content_features.mattr IS
    'OBSOLETO: vocabulario del scorer A-E v1.0. El vigente es mattr_200 (ventana fija de 200 tokens).';
COMMENT ON COLUMN content_features.enganche_1000w IS
    'OBSOLETO: vocabulario del scorer A-E v1.0.';

COMMIT;

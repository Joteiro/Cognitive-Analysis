-- 005_reference_corpus.sql
-- Separa el corpus de referencia (videos publicos muestreados) del historial
-- personal de Juan, y guarda la procedencia de cada video muestreado para que
-- el muestreo sea auditable y reproducible.
--
-- Motivo: los cortes bajo/medio/alto se calculaban como tercios del historial
-- personal (94 videos, 41 % de un solo canal, casi todo News & Politics en
-- espanol). Eso no es una escala de referencia, es un espejo del consumo de una
-- persona. El corpus de referencia lo reemplaza.

ALTER TABLE content_items
  ADD COLUMN IF NOT EXISTS corpus                 varchar(20)  NOT NULL DEFAULT 'historial',
  ADD COLUMN IF NOT EXISTS sampling_source        varchar(30),
  ADD COLUMN IF NOT EXISTS sampling_seed          text,
  ADD COLUMN IF NOT EXISTS stratum_format         varchar(30),
  ADD COLUMN IF NOT EXISTS stratum_duration       varchar(20),
  ADD COLUMN IF NOT EXISTS sampled_at             timestamptz,
  ADD COLUMN IF NOT EXISTS sampling_frame_version varchar(20);

COMMENT ON COLUMN content_items.corpus IS
  'historial = visto por el usuario (tiene watched_at). referencia = muestreado de YouTube para construir la escala. Nunca mezclar los dos al calcular percentiles.';
COMMENT ON COLUMN content_items.sampling_source IS
  'chart_canal = canal aparecido en mostPopular AR/ES, video sorteado de su playlist de subidas. busqueda_semilla = search.list con termino frecuente + ventana temporal aleatoria y order=date.';
COMMENT ON COLUMN content_items.sampling_seed IS
  'Termino semilla o celda de chart que produjo el candidato. Permite reproducir el sorteo.';
COMMENT ON COLUMN content_items.stratum_format IS
  'Macroformato asignado desde category_id de YouTube ANTES de enriquecer: informativo, practico_personal, entretenimiento, deporte_gaming.';
COMMENT ON COLUMN content_items.stratum_duration IS
  'corto (2-10 min), medio (10-30 min), largo (30-180 min).';
COMMENT ON COLUMN content_items.sampling_frame_version IS
  'Version del marco muestral. Si cambian los terminos semilla, las categorias o los cortes de duracion, sube la version: los percentiles de marcos distintos no son comparables.';

-- Todo lo que ya estaba es historial personal.
UPDATE content_items SET corpus = 'historial' WHERE corpus IS NULL;

-- El worker de enriquecimiento pide la cola filtrando por estado; este indice
-- evita que el scan crezca cuando el corpus pase de 94 a ~500 filas.
CREATE INDEX IF NOT EXISTS idx_content_items_corpus_estado
  ON content_items (corpus, enrichment_status, next_attempt_at);

CREATE INDEX IF NOT EXISTS idx_content_items_estratos
  ON content_items (corpus, stratum_format, stratum_duration);

-- Vista de control: cuantos videos aptos hay por celda del diseno.
CREATE OR REPLACE VIEW v_corpus_referencia_estratos AS
SELECT
  stratum_format,
  stratum_duration,
  count(*)                                              AS candidatos,
  count(*) FILTER (WHERE enrichment_status = 'ok')      AS enriquecidos,
  count(*) FILTER (WHERE transcript_word_count > 0)     AS con_transcripcion,
  count(DISTINCT channel_id)                            AS canales_distintos
FROM content_items
WHERE corpus = 'referencia'
GROUP BY 1, 2
ORDER BY 1, 2;

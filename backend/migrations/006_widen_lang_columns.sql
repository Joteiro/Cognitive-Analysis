-- 006_widen_lang_columns.sql   (aplicada en Supabase el 2026-08-11)
--
-- Sintoma: al guardar el video e4GCeGYwBLM el enriquecimiento fallo con
--   "value too long for type character varying(10)"
-- despues de haber bajado con exito una transcripcion manual de 9.289 palabras.
--
-- Causa: YouTube no siempre devuelve un codigo de idioma ISO 639 en la pista de
-- subtitulos. Cuando el canal subio subtitulos manuales, el identificador de la
-- pista puede ser algo como 'es-uYU-mmqFLq8' (14 caracteres). El campo
-- transcript_lang era varchar(10), asi que la fila entera se rechazaba y se
-- perdia la transcripcion por el nombre de la pista.
--
-- Se ensancha en vez de truncar: el identificador completo permite volver a
-- pedir exactamente esa pista si hiciera falta. Para agrupar por idioma se usa
-- split_part(transcript_lang, '-', 1).

ALTER TABLE content_items
  ALTER COLUMN transcript_lang TYPE varchar(40),
  ALTER COLUMN video_language  TYPE varchar(40);

COMMENT ON COLUMN content_items.transcript_lang IS
  'Codigo de la pista de subtitulos tal cual lo devuelve YouTube. NO es siempre un ISO 639: las pistas manuales traen identificadores como es-uYU-mmqFLq8. Para agrupar por idioma, usar split_part(transcript_lang, ''-'', 1).';

-- 008_limpiar_content_features.sql        APLICADA el 2026-08-13 sobre Supabase.
--
-- Elimina 20 columnas de la epoca del scorer A-E (jubilado el 2026-08-13).
--
-- POR QUE
-- -------
-- No es prolijidad: es que confunden. Estos pares convivian en la misma tabla:
--
--     palabras_por_minuto   vs   ritmo_ppm
--     mattr                 vs   mattr_200
--     fuentes_1000w         vs   atribucion_1000w
--     cobertura_promesa     vs   cobertura_titulo
--
-- Y NO son sinonimos. mattr_200 fija la ventana en 200 tokens justamente
-- porque mattr a secas caia con la duracion del video — el sesgo que motivo
-- todo el rediseno. Dos columnas de nombre casi igual y significado distinto
-- son el mismo error que este proyecto viene persiguiendo desde el principio:
-- el instrumento colandose en la medida sin que nada avise.
--
-- Los cinco nivel_* son directamente los niveles de la letra A-E.
--
-- POR QUE ES SEGURO
-- -----------------
--   - Estaban en NULL en las 5 filas existentes; la tabla estaba vacia hasta
--     que /panel empezo a escribirla.
--   - Ningun archivo del proyecto las lee ni las escribe (verificado).
--   - Es reversible: cualquiera vuelve con un ADD COLUMN. Y los valores en si
--     se pueden recalcular cuando sea, porque content_items guarda las
--     transcripciones: el panel entero es reproducible.
--
-- La tabla queda en 33 columnas, todas en uso.

BEGIN;

ALTER TABLE content_features
    -- gemelas de nombre viejo de descriptores vigentes
    DROP COLUMN IF EXISTS palabras_por_minuto,   -- ahora ritmo_ppm
    DROP COLUMN IF EXISTS mattr,                 -- ahora mattr_200
    DROP COLUMN IF EXISTS fuentes_1000w,         -- ahora atribucion_1000w
    DROP COLUMN IF EXISTS cobertura_promesa,     -- ahora cobertura_titulo

    -- descriptores que no entraron en el panel de 8
    DROP COLUMN IF EXISTS ejemplos_1000w,
    DROP COLUMN IF EXISTS palabras_por_frase,
    DROP COLUMN IF EXISTS enganche_1000w,
    DROP COLUMN IF EXISTS preguntas_1000w,
    DROP COLUMN IF EXISTS repeticion,

    -- componentes intermedios que nunca se poblaron
    DROP COLUMN IF EXISTS has_punctuation,
    DROP COLUMN IF EXISTS n_links,
    DROP COLUMN IF EXISTS n_links_verificables,
    DROP COLUMN IF EXISTS n_links_comerciales,
    DROP COLUMN IF EXISTS n_chapters,            -- tambien vive en content_items
    DROP COLUMN IF EXISTS desc_words,

    -- niveles de la letra A-E
    DROP COLUMN IF EXISTS nivel_densidad,
    DROP COLUMN IF EXISTS nivel_carga,
    DROP COLUMN IF EXISTS nivel_retencion,
    DROP COLUMN IF EXISTS nivel_trazabilidad,
    DROP COLUMN IF EXISTS nivel_correspondencia;

COMMIT;

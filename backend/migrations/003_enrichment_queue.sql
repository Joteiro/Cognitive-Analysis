-- ============================================================================
-- Migración 003 — `content_items` como cola de trabajo con reintentos
-- ----------------------------------------------------------------------------
-- La 002 dejó `enrichment_status` como estado, pero le faltaban dos piezas
-- para ser una cola de verdad: cuántas veces se intentó y cuándo toca el
-- próximo intento. Sin eso, cada corrida reintenta todo a la vez y machaca
-- a YouTube; con eso, el worker puede procesar tandas chicas y espaciadas.
--
-- Estados posibles de la cola:
--   NULL         → nunca se intentó
--   'ok'         → metadatos + transcripción. Terminado.
--   'partial'    → metadatos sí, transcripción no. Reintentable.
--   'failed'     → nada. Reintentable.
--   'no_subs'    → el video no tiene subtítulos. DEFINITIVO.
--   'geo_blocked'→ bloqueado por región. DEFINITIVO.
--   'unavailable'→ privado, borrado o de pago. DEFINITIVO.
--   'exhausted'  → se agotaron los reintentos. No se toca más sin --force.
-- ============================================================================

BEGIN;

ALTER TABLE content_items
    ADD COLUMN IF NOT EXISTS attempts        INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ;

-- Lo ya resuelto no vuelve a la cola
UPDATE content_items
   SET next_attempt_at = NULL
 WHERE enrichment_status IN ('ok', 'no_subs', 'geo_blocked', 'unavailable');

-- Lo pendiente entra listo para el próximo turno del worker
UPDATE content_items
   SET next_attempt_at = now()
 WHERE (transcript IS NULL OR length(transcript) = 0)
   AND (enrichment_status IS NULL OR enrichment_status IN ('partial', 'failed'))
   AND next_attempt_at IS NULL;

-- Índice pensado para la consulta del worker:
-- "dame lo pendiente cuyo turno ya llegó, lo más atrasado primero"
CREATE INDEX IF NOT EXISTS idx_content_items_queue
    ON content_items(next_attempt_at)
    WHERE next_attempt_at IS NOT NULL;

COMMIT;

-- ============================================================================
-- Para mirar el estado de la cola en cualquier momento:
--
--   SELECT COALESCE(enrichment_status,'(sin intentar)') AS estado,
--          count(*), min(next_attempt_at) AS proximo_turno, max(attempts) AS max_intentos
--     FROM content_items WHERE source='youtube'
--    GROUP BY 1 ORDER BY 2 DESC;
-- ============================================================================

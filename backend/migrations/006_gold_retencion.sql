-- 006_gold_retencion.sql   (aplicada 2026-08-21)
-- Vista de modelado: una fila por (persona, video).
--
-- Es el dataset que consume el analisis de la entrega 4. Se calcula la
-- retencion de las DOS formas acordadas, porque ninguna basta sola:
--   * sobre el subconjunto dificil (los items que la linea de base fallo):
--     interpretacion directa, n mas chico;
--   * sobre todos los items descontando la base: correccion clasica por
--     adivinacion, usa todo el material.
-- Si las dos divergen mucho, la linea de base del modelo no representa bien
-- el conocimiento previo de la persona, y eso tambien es un resultado.

create or replace view gold_retencion as
with base as (
  select
    r.persona_id,
    q.content_item_id,
    count(*)                                          as n_items,
    sum(case when r.acierto then 1 else 0 end)        as aciertos,
    count(*) filter (where q.dificil)                 as n_dificiles,
    sum(case when q.dificil and r.acierto then 1 else 0 end) as aciertos_dificiles,
    avg(case when q.linea_base_acerto then 1.0 else 0.0 end) as tasa_linea_base,
    max(r.respondido_at)                              as respondido_at,
    avg(r.dias_transcurridos)                         as dias_transcurridos
  from quiz_respuestas r
  join quiz_preguntas q on q.id = r.pregunta_id
  where q.utilizable
  group by r.persona_id, q.content_item_id
)
select
  b.persona_id,
  b.content_item_id,
  b.n_items,
  b.aciertos,
  round(b.aciertos::numeric / nullif(b.n_items, 0), 4)                as retencion_bruta,
  b.n_dificiles,
  b.aciertos_dificiles,
  round(b.aciertos_dificiles::numeric / nullif(b.n_dificiles, 0), 4)  as retencion_dificil,
  round(b.tasa_linea_base, 4)                                         as tasa_linea_base,
  -- (acierto_persona - acierto_base) / (1 - acierto_base)
  case when b.tasa_linea_base < 1 then
    round(((b.aciertos::numeric / nullif(b.n_items, 0)) - b.tasa_linea_base)
          / (1 - b.tasa_linea_base), 4)
  end                                                                 as retencion_corregida,
  b.dias_transcurridos,
  b.respondido_at,
  -- controles y descriptores del panel, para el modelado
  ci.duration_seconds,
  ln(greatest(ci.duration_seconds, 1)::numeric)                       as log_duracion,
  ci.watched_at,
  f.formato,
  f.ritmo_ppm_pct, f.cifras_100w_pct, f.atribucion_1000w_pct, f.mattr_200_pct,
  f.conectores_1000w_pct, f.enlaces_externos_pct, f.promocional_1000w_pct,
  f.cobertura_titulo_pct
from base b
join content_items   ci on ci.id = b.content_item_id
join content_features f on f.content_item_id = b.content_item_id;

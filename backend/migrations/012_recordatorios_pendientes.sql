-- 012_recordatorios_pendientes.sql : vista para el recordatorio del diferido.
-- Lista quien tiene mail y todavia no termino, con dias de inactividad y su
-- enlace. Solo participantes CON mail (los que aceptaron el recordatorio).
--   select * from recordatorios_pendientes where dias_inactivo >= 3;
create or replace view recordatorios_pendientes as
with resp as (
  select r.persona_id,
         count(distinct q.content_item_id) as videos_respondidos,
         max(r.respondido_at)              as ultima_respuesta
  from quiz_respuestas r
  join quiz_preguntas q on q.id = r.pregunta_id
  group by r.persona_id
),
vis as (
  select persona_id, max(visto_at) as ultimo_visionado
  from quiz_visionados group by persona_id
),
asig as (
  select persona_id, count(*) as n from participante_asignacion group by persona_id
)
select
  p.persona_id,
  c.email,
  coalesce(a.n, 4)                                                as videos_asignados,
  coalesce(r.videos_respondidos, 0)                              as videos_respondidos,
  greatest(0, coalesce(a.n,4) - coalesce(r.videos_respondidos,0)) as videos_pendientes,
  floor(extract(epoch from now() - greatest(
        p.creado_at,
        coalesce(r.ultima_respuesta, p.creado_at),
        coalesce(v.ultimo_visionado, p.creado_at))) / 86400)::int as dias_inactivo,
  'https://joteiro.github.io/Cognitive-Analysis/quiz_piloto/formularios_web/quiz_web.html?t=' || p.token as enlace
from participantes p
join participante_contacto c on c.token = p.token
left join resp r on r.persona_id = p.persona_id
left join vis  v on v.persona_id = p.persona_id
left join asig a on a.persona_id = p.persona_id
where greatest(0, coalesce(a.n,4) - coalesce(r.videos_respondidos,0)) > 0
order by dias_inactivo desc;

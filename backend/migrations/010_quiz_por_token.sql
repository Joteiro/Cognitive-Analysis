-- 010_quiz_por_token.sql : pagina unica por token (arquitectura dinamica)
-- Una sola pagina hospedada sirve a todos; cada persona entra con ?t=<token>.
-- La pagina pide su quiz al abrir (obtener_quiz) y NO recibe la respuesta
-- correcta: eso recien se revela al enviar (registrar_respuestas la devuelve).

-- Asignacion de videos por persona (nucleo + rotacion). Si una persona no
-- tiene filas aca, obtener_quiz usa el nucleo por defecto.
create table if not exists participante_asignacion (
  id              bigserial primary key,
  persona_id      varchar(40) not null references participantes(persona_id) on delete cascade,
  content_item_id bigint not null references content_items(id) on delete cascade,
  orden           smallint not null default 0,
  unique (persona_id, content_item_id)
);
alter table participante_asignacion enable row level security;

-- Entrega el quiz del token SIN la respuesta correcta ni la cita.
create or replace function obtener_quiz(p_token text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_persona varchar(40);
  v_ids     bigint[];
  v_videos  jsonb;
begin
  select persona_id into v_persona from participantes where token = p_token;
  if v_persona is null then raise exception 'token invalido'; end if;

  select array_agg(content_item_id order by orden, content_item_id) into v_ids
    from participante_asignacion where persona_id = v_persona;
  if v_ids is null then v_ids := array[609,610,94,623]; end if;   -- nucleo por defecto

  select jsonb_agg(t order by t.orden) into v_videos from (
    select ci.id as content_item_id, ci.title as titulo, ci.channel as canal,
           ci.external_id, array_position(v_ids, ci.id) as orden,
           (select jsonb_agg(jsonb_build_object(
                     'id', q.id, 'pregunta', q.pregunta,
                     'opciones', q.opciones, 'dificil', q.dificil) order by q.n_orden)
              from quiz_preguntas q
              where q.content_item_id = ci.id and q.utilizable) as preguntas
    from content_items ci
    where ci.id = any(v_ids)
  ) t;

  return jsonb_build_object('persona', v_persona, 'videos', coalesce(v_videos, '[]'::jsonb));
end $$;

-- registrar_respuestas v2: inserta y DEVUELVE las soluciones (correcta + cita +
-- acierto) para que la pagina las muestre al terminar. El acierto y los dias se
-- siguen calculando en el servidor.
drop function if exists registrar_respuestas(text, jsonb);
create function registrar_respuestas(p_token text, p_respuestas jsonb) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_persona  varchar(40);
  v_item     jsonb;
  v_n        int := 0;
  v_correcta smallint;
  v_content  bigint;
  v_cita     text;
  v_visto    timestamptz;
  v_dias     numeric;
  v_sol      jsonb := '[]'::jsonb;
begin
  select persona_id into v_persona from participantes where token = p_token;
  if v_persona is null then raise exception 'token invalido'; end if;

  for v_item in select * from jsonb_array_elements(p_respuestas) loop
    select correcta, content_item_id, cita into v_correcta, v_content, v_cita
      from quiz_preguntas
      where id = (v_item->>'pregunta_id')::bigint and utilizable;
    if v_correcta is null then continue; end if;

    select visto_at into v_visto from quiz_visionados
      where persona_id = v_persona and content_item_id = v_content;
    v_dias := case when v_visto is not null
                   then round(extract(epoch from (now() - v_visto)) / 86400.0, 2) end;

    insert into quiz_respuestas
      (pregunta_id, persona_id, eleccion, acierto,
       segundos_respuesta, dias_transcurridos, intento)
    values (
      (v_item->>'pregunta_id')::bigint, v_persona,
      (v_item->>'eleccion')::smallint,
      (v_item->>'eleccion')::smallint = v_correcta,
      nullif(v_item->>'segundos', '')::int, v_dias, 1)
    on conflict (pregunta_id, persona_id, intento) do nothing;

    v_sol := v_sol || jsonb_build_object(
      'pregunta_id', (v_item->>'pregunta_id')::bigint,
      'correcta', v_correcta, 'cita', v_cita,
      'tu_eleccion', (v_item->>'eleccion')::smallint,
      'acierto', (v_item->>'eleccion')::smallint = v_correcta);
    v_n := v_n + 1;
  end loop;

  return jsonb_build_object('n', v_n, 'soluciones', v_sol);
end $$;

revoke all on function obtener_quiz(text) from public;
revoke all on function registrar_respuestas(text, jsonb) from public;
grant execute on function obtener_quiz(text) to anon;
grant execute on function registrar_respuestas(text, jsonb) to anon;

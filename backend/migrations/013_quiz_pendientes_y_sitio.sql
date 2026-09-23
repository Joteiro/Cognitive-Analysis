-- 013_quiz_pendientes_y_sitio.sql : el quiz por token pasa a ser una COLA
--
-- Hasta la 012, obtener_quiz devolvia SIEMPRE todos los videos asignados, con
-- todas sus preguntas, aunque la persona ya las hubiera contestado. La pagina
-- lo tapaba con una marca en localStorage ("ya completaste"), que solo vale en
-- ese navegador: en otro dispositivo el quiz reaparecia entero y las
-- respuestas nuevas se perdian en silencio (on conflict do nothing).
--
-- Con el sitio unificado aparece una cola que CRECE: se generan quizzes nuevos
-- desde la web y se suman a la persona. Eso obliga a que el servidor sea quien
-- sabe que falta. Tres cambios en obtener_quiz, ninguno rompe la pagina vieja:
--
--   1. Solo devuelve las preguntas que la persona NO contesto, y solo los
--      videos a los que les queda alguna. Un video sin preguntas utilizables
--      ya no viaja con preguntas = null (la pagina vieja reventaba ahi).
--   2. Devuelve visto_at: si el visionado ya esta registrado en el servidor,
--      la pagina desbloquea las preguntas sin volver a mostrar el video. Para
--      la dueña del historial, el visionado se registra con content_items.
--      watched_at al sumar el video a su cola (backend/app/routes/admin.py):
--      los dias hasta la respuesta salen contra cuando lo vio de verdad.
--   3. Devuelve la hora del servidor (ahora), para decir "hace N dias" sin
--      depender del reloj del navegador.
--
-- Ademas, alta_participante devuelve el enlace nuevo del sitio (quiz.html).
-- El viejo (quiz_piloto/formularios_web/quiz_web.html) sigue funcionando: es
-- una redireccion que conserva ?t=, asi que los enlaces ya enviados no se caen.

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
           v.visto_at,
           pend.preguntas
      from content_items ci
      left join quiz_visionados v
             on v.persona_id = v_persona and v.content_item_id = ci.id
      cross join lateral (
        select jsonb_agg(jsonb_build_object(
                 'id', q.id, 'pregunta', q.pregunta,
                 'opciones', q.opciones, 'dificil', q.dificil) order by q.n_orden) as preguntas
          from quiz_preguntas q
         where q.content_item_id = ci.id and q.utilizable
           and not exists (select 1 from quiz_respuestas r
                            where r.pregunta_id = q.id and r.persona_id = v_persona)
      ) pend
     where ci.id = any(v_ids)
       and pend.preguntas is not null
  ) t;

  return jsonb_build_object('persona', v_persona,
                            'videos', coalesce(v_videos, '[]'::jsonb),
                            'ahora', now());
end $$;

revoke all on function obtener_quiz(text) from public;
grant execute on function obtener_quiz(text) to anon;

-- alta_participante: igual que la 011, con el enlace del sitio.
create or replace function alta_participante(p_persona text, p_email text default null)
returns table(seudonimo text, token text, enlace text)
language plpgsql as $$
declare
  v_token text;
begin
  select pa.token into v_token from participantes pa where pa.persona_id = p_persona;
  if v_token is null then
    v_token := replace(gen_random_uuid()::text, '-', '');
    insert into participantes (persona_id, token, nota)
      values (p_persona, v_token, 'reclutamiento externo');
  end if;

  if p_email is not null and length(trim(p_email)) > 0 then
    insert into participante_contacto (token, email)
      select v_token, trim(p_email)
      where not exists (
        select 1 from participante_contacto c
        where c.token = v_token and c.email = trim(p_email));
  end if;

  return query
    select p_persona,
           v_token,
           'https://joteiro.github.io/Cognitive-Analysis/quiz.html?t=' || v_token;
end $$;

revoke all on function alta_participante(text, text) from public, anon, authenticated;

-- 011_alta_participante.sql : alta self-service de participantes
-- Correr desde el editor SQL de Supabase (rol privilegiado). NO se expone al
-- rol anonimo: crear participantes es una accion de administracion.
--   select * from alta_participante('ana-02', 'ana@correo.com');
--   select * from alta_participante('p03');   -- sin mail
-- Devuelve seudonimo, token y el enlace listo para enviar. Idempotente: si el
-- seudonimo ya existe, devuelve su token actual (no crea uno nuevo).

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
           'https://joteiro.github.io/Cognitive-Analysis/quiz_piloto/formularios_web/quiz_web.html?t=' || v_token;
end $$;

revoke all on function alta_participante(text, text) from public, anon, authenticated;

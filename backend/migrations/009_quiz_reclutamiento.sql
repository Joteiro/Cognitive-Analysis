-- 009_quiz_reclutamiento.sql
-- Reclutamiento externo self-service (protocolo docs/protocolo_reclutamiento.md).
--
-- Aparece la entidad PARTICIPANTE con un token (su enlace personal) y, por
-- primera vez, el visionado con reloj PROPIO de cada persona: hasta ahora los
-- dias se median contra content_items.watched_at (la fecha en que lo vio Juan),
-- que para un externo no significa nada.
--
-- Seguridad: la clave publica es publica de verdad (va incrustada en el HTML).
-- Por eso NADIE escribe directo en las tablas; toda escritura pasa por dos
-- funciones RPC security definer que validan el token, calculan el acierto en
-- el servidor (el cliente no puede falsearlo) y calculan los dias contra el
-- visto_at propio. La clave anon solo puede EJECUTAR esas dos funciones.

-- 1. Participantes ----------------------------------------------------------
create table if not exists participantes (
  persona_id   varchar(40) primary key,
  token        text unique not null,
  nota         text,                       -- referencia interna (no dato sensible)
  creado_at    timestamptz not null default now()
);

-- Contacto SEPARADO de las respuestas y de la identidad seudonima: el correo
-- solo sirve para el recordatorio del diferido y vive aparte a proposito.
create table if not exists participante_contacto (
  id         bigserial primary key,
  token      text not null references participantes(token) on delete cascade,
  email      text not null,
  creado_at  timestamptz not null default now()
);

-- 2. Visionado: cuando ESTA persona vio ESTE video (su propio reloj) ---------
create table if not exists quiz_visionados (
  id                bigserial primary key,
  persona_id        varchar(40) not null references participantes(persona_id) on delete cascade,
  content_item_id   bigint not null references content_items(id) on delete cascade,
  visto_at          timestamptz not null default now(),
  reproduccion_pct  numeric(5,2),          -- % del video efectivamente reproducido
  completo          boolean,               -- llego al final (o al umbral)
  unique (persona_id, content_item_id)
);
create index if not exists ix_quiz_visionados_persona on quiz_visionados(persona_id);

-- 3. RLS: sin policies = deny all para anon. Todo pasa por las funciones. ----
alter table participantes          enable row level security;
alter table participante_contacto  enable row level security;
alter table quiz_visionados        enable row level security;

-- 4. RPC: registrar visionado ------------------------------------------------
create or replace function registrar_visionado(
  p_token text,
  p_content_item_id bigint,
  p_reproduccion_pct numeric default null,
  p_completo boolean default null
) returns timestamptz
language plpgsql security definer set search_path = public as $$
declare
  v_persona varchar(40);
  v_visto   timestamptz;
begin
  select persona_id into v_persona from participantes where token = p_token;
  if v_persona is null then raise exception 'token invalido'; end if;

  insert into quiz_visionados (persona_id, content_item_id, reproduccion_pct, completo)
  values (v_persona, p_content_item_id, p_reproduccion_pct, p_completo)
  on conflict (persona_id, content_item_id) do update
    set reproduccion_pct = greatest(coalesce(quiz_visionados.reproduccion_pct, 0),
                                    coalesce(excluded.reproduccion_pct, 0)),
        completo = coalesce(quiz_visionados.completo, false)
                   or coalesce(excluded.completo, false)
  returning visto_at into v_visto;
  return v_visto;
end $$;

-- 5. RPC: registrar respuestas (acierto y dias se calculan en el servidor) ---
-- p_respuestas: jsonb array de { "pregunta_id": <int>, "eleccion": <0-3>, "segundos": <int|null> }
create or replace function registrar_respuestas(
  p_token text,
  p_respuestas jsonb
) returns integer
language plpgsql security definer set search_path = public as $$
declare
  v_persona  varchar(40);
  v_item     jsonb;
  v_n        int := 0;
  v_correcta smallint;
  v_content  bigint;
  v_visto    timestamptz;
  v_dias     numeric;
begin
  select persona_id into v_persona from participantes where token = p_token;
  if v_persona is null then raise exception 'token invalido'; end if;

  for v_item in select * from jsonb_array_elements(p_respuestas) loop
    -- solo preguntas reales y utilizables; el resto se ignora en silencio
    select correcta, content_item_id into v_correcta, v_content
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
      (v_item->>'pregunta_id')::bigint,
      v_persona,
      (v_item->>'eleccion')::smallint,
      (v_item->>'eleccion')::smallint = v_correcta,
      nullif(v_item->>'segundos', '')::int,
      v_dias,
      1)
    on conflict (pregunta_id, persona_id, intento) do nothing;
    v_n := v_n + 1;
  end loop;
  return v_n;
end $$;

-- 6. Permisos: la clave publica (anon) SOLO ejecuta estas dos funciones ------
revoke all on function registrar_visionado(text, bigint, numeric, boolean) from public;
revoke all on function registrar_respuestas(text, jsonb) from public;
grant execute on function registrar_visionado(text, bigint, numeric, boolean) to anon;
grant execute on function registrar_respuestas(text, jsonb) to anon;

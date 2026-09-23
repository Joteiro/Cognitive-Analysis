-- Subconjunto del esquema real (leido de Supabase el 2026-09-22) para probar sin red.
create table content_items (
  id bigserial primary key, source varchar(20) not null default 'youtube',
  external_id varchar(100) not null unique, url text not null, title text not null,
  channel text, duration_seconds integer, description text, tags jsonb,
  category_id varchar(10), category_name varchar(50), view_count bigint, like_count integer,
  comment_count integer, stats_fetched_at timestamptz, transcript text,
  transcript_fetched_at timestamptz, watched_at timestamptz,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  transcript_is_generated boolean, transcript_lang varchar(40), transcript_source varchar(20),
  transcript_word_count integer, transcript_segments jsonb, chapters jsonb, n_chapters integer,
  upload_date date, channel_id varchar(50), video_language varchar(40),
  enrichment_status varchar(20), enrichment_error text, enriched_at timestamptz,
  enricher_version varchar(20), attempts integer not null default 0,
  next_attempt_at timestamptz, last_attempt_at timestamptz,
  corpus varchar(20) not null default 'historial', sampling_source varchar(30),
  sampling_seed text, stratum_format varchar(30), stratum_duration varchar(20),
  sampled_at timestamptz, sampling_frame_version varchar(20));
create table content_features (
  id bigserial primary key, content_item_id bigint not null references content_items(id) on delete cascade,
  features_version varchar(20) not null, computed_at timestamptz not null default now(),
  n_words integer, duration_seconds integer, lang varchar(10), transcript_source varchar(20),
  has_description boolean, has_tags boolean, cifras_100w real, frame_version varchar(40),
  formato varchar(40), panel jsonb, apto boolean, cobertura_transcripcion real,
  motivo_no_apto varchar(60), etiquetas jsonb,
  unique (content_item_id, features_version));
create table if not exists quiz_preguntas (
  id                    bigserial primary key,
  content_item_id       bigint not null references content_items(id) on delete cascade,

  -- Trazabilidad del instrumento. Sin esto no se puede saber si un cambio de
  -- resultados vino del prompt o del modelo: ya paso una vez con scorer_version.
  version               varchar(20) not null,
  modelo                varchar(80) not null,
  modelo_control        varchar(80),
  n_orden               smallint not null,

  tipo                  varchar(20),
  pregunta              text not null,
  opciones              jsonb not null,
  correcta              smallint not null check (correcta between 0 and 3),
  cita                  text,

  -- Los tres filtros de descarte. Se guardan TAMBIEN las descartadas: son el
  -- registro de validez del instrumento, no basura.
  anclada               boolean,
  motivo_anclaje        text,
  justificada           boolean,
  motivo_justificacion  text,
  equilibrada           boolean,
  motivo_equilibrio     text,
  utilizable            boolean not null default false,
  descarte              text,

  -- Linea de base: que contesto un modelo que NO vio la transcripcion.
  -- No descarta; es el suelo contra el que se lee la retencion humana.
  linea_base_acerto     boolean,
  linea_base_eleccion   smallint,
  linea_base_seguridad  varchar(10),
  dificil               boolean,

  generado_at           timestamptz,
  created_at            timestamptz not null default now(),

  unique (content_item_id, version, n_orden)
);

create index if not exists ix_quiz_preguntas_item on quiz_preguntas(content_item_id);
create index if not exists ix_quiz_preguntas_util on quiz_preguntas(utilizable) where utilizable;

create table if not exists quiz_respuestas (
  id                 bigserial primary key,
  pregunta_id        bigint not null references quiz_preguntas(id) on delete cascade,

  -- Seudonimo, nunca un nombre ni un correo: el historial de visionado ya es
  -- dato sensible y esto lo ata a una persona.
  persona_id         varchar(40) not null,

  eleccion           smallint not null check (eleccion between 0 and 3),
  acierto            boolean not null,
  segundos_respuesta integer,
  dias_transcurridos numeric(8,2),
  intento            smallint not null default 1,
  respondido_at      timestamptz not null default now(),

  unique (pregunta_id, persona_id, intento)
);

create index if not exists ix_quiz_respuestas_persona on quiz_respuestas(persona_id);

alter table quiz_preguntas enable row level security;
alter table quiz_respuestas enable row level security;
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

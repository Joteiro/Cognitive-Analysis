-- 005_quiz_retencion.sql   (aplicada 2026-08-21)
-- Quiz de retencion: la variable dependiente del proyecto.
--
-- Aparece aqui una entidad que el modelo de datos no tenia: la PERSONA. Hasta
-- ahora todo colgaba del video; medir retencion obliga a distinguir quien
-- contesta. Ver docs/entregas/04_analisis_modelado.md, seccion 4.4.

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

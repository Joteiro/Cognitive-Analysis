#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cargar_quiz.py -- lleva el piloto del quiz a Supabase, en los dos sentidos.

  PREGUNTAS:  docs/quiz_piloto/quiz_piloto_<etiqueta>.json  ->  quiz_preguntas
  RESPUESTAS: el .json que descarga el quiz HTML              ->  quiz_respuestas

POR QUE SE CARGAN TAMBIEN LAS PREGUNTAS DESCARTADAS
    Podrian filtrarse y guardar solo las utilizables, pero las descartadas con
    su motivo SON el registro de validez del instrumento: "de 144 generadas, 9
    cayeron por opciones desbalanceadas y 5 porque la cita no justificaba la
    respuesta" es un resultado del trabajo, no basura. La columna `utilizable`
    separa unas de otras, y la vista gold_retencion ya filtra por ella.

USO
    .venv\\Scripts\\python cargar_quiz.py --dry-run
    .venv\\Scripts\\python cargar_quiz.py --etiqueta final
    .venv\\Scripts\\python cargar_quiz.py --respuestas respuestas_juan.json
"""
import argparse
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
DOCS = RAIZ / "docs"
QUIZ = DOCS / "quiz_piloto"
SALIDA = QUIZ / "tests"
RESPUESTAS = QUIZ / "respuestas"

SQL_PREGUNTA = """
insert into quiz_preguntas (
  content_item_id, version, modelo, modelo_control, n_orden, tipo,
  pregunta, opciones, correcta, cita,
  anclada, motivo_anclaje, justificada, motivo_justificacion,
  equilibrada, motivo_equilibrio, utilizable, descarte,
  linea_base_acerto, linea_base_eleccion, linea_base_seguridad, dificil,
  generado_at)
values (%(content_item_id)s, %(version)s, %(modelo)s, %(modelo_control)s,
        %(n_orden)s, %(tipo)s, %(pregunta)s, %(opciones)s, %(correcta)s, %(cita)s,
        %(anclada)s, %(motivo_anclaje)s, %(justificada)s, %(motivo_justificacion)s,
        %(equilibrada)s, %(motivo_equilibrio)s, %(utilizable)s, %(descarte)s,
        %(linea_base_acerto)s, %(linea_base_eleccion)s, %(linea_base_seguridad)s,
        %(dificil)s, %(generado_at)s)
on conflict (content_item_id, version, n_orden) do update set
  pregunta = excluded.pregunta,
  opciones = excluded.opciones,
  correcta = excluded.correcta,
  cita = excluded.cita,
  utilizable = excluded.utilizable,
  descarte = excluded.descarte,
  linea_base_acerto = excluded.linea_base_acerto,
  linea_base_eleccion = excluded.linea_base_eleccion,
  linea_base_seguridad = excluded.linea_base_seguridad,
  dificil = excluded.dificil,
  modelo_control = excluded.modelo_control
"""

SQL_RESPUESTA = """
insert into quiz_respuestas (pregunta_id, persona_id, eleccion, acierto,
                             segundos_respuesta, dias_transcurridos, intento)
values (%(pregunta_id)s, %(persona_id)s, %(eleccion)s, %(acierto)s,
        %(segundos_respuesta)s, %(dias_transcurridos)s, %(intento)s)
on conflict (pregunta_id, persona_id, intento) do update set
  eleccion = excluded.eleccion,
  acierto = excluded.acierto,
  segundos_respuesta = excluded.segundos_respuesta,
  dias_transcurridos = excluded.dias_transcurridos,
  respondido_at = now()
"""


def cargar_preguntas(cur, datos: list) -> tuple:
    filas, saltadas = 0, 0
    for video in datos:
        if video.get("error"):
            saltadas += 1
            continue
        for i, p in enumerate(video["preguntas"]):
            if p.get("correcta") is None:
                # nunca llego a tener respuesta correcta valida (formato roto):
                # no hay nada que guardar mas alla del recuento del informe
                saltadas += 1
                continue
            cur.execute(SQL_PREGUNTA, {
                "content_item_id": video["content_item_id"],
                "version": video["version"],
                "modelo": video["modelo"],
                "modelo_control": video.get("modelo_control"),
                "n_orden": i,
                "tipo": p.get("tipo"),
                "pregunta": p["pregunta"],
                "opciones": json.dumps(p["opciones"], ensure_ascii=False),
                "correcta": p["correcta"],
                "cita": p.get("cita"),
                "anclada": p.get("anclada"),
                "motivo_anclaje": p.get("motivo_anclaje"),
                "justificada": p.get("justificada"),
                "motivo_justificacion": p.get("motivo_justificacion"),
                "equilibrada": p.get("equilibrada"),
                "motivo_equilibrio": p.get("motivo_equilibrio"),
                "utilizable": bool(p.get("sobrevive")),
                "descarte": p.get("descarte"),
                "linea_base_acerto": p.get("linea_base_acerto"),
                "linea_base_eleccion": p.get("control_eleccion"),
                "linea_base_seguridad": p.get("control_seguridad"),
                "dificil": p.get("dificil"),
                "generado_at": video.get("generado_at"),
            })
            filas += 1
    return filas, saltadas


def cargar_respuestas(cur, datos: dict) -> int:
    persona = datos["persona_id"]
    filas = 0
    for r in datos["respuestas"]:
        cur.execute(SQL_RESPUESTA, {
            "pregunta_id": r["pregunta_id"],
            "persona_id": persona,
            "eleccion": r["eleccion"],
            "acierto": r["acierto"],
            "segundos_respuesta": r.get("segundos"),
            "dias_transcurridos": r.get("dias_transcurridos"),
            "intento": r.get("intento", 1),
        })
        filas += 1
    return filas


def main() -> int:
    ap = argparse.ArgumentParser(description="Carga el quiz en Supabase")
    ap.add_argument("--etiqueta", default="final")
    ap.add_argument("--respuestas", default=None, metavar="RUTA",
                    help="cargar un json de respuestas del quiz HTML")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    env = RAIZ / "backend" / ".env"
    try:
        from dotenv import load_dotenv
        load_dotenv(env)
    except ImportError:
        pass
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print(f"No hay DATABASE_URL en {env}")
        return 2

    if args.respuestas:
        ruta = Path(args.respuestas)
        if not ruta.is_absolute():
            # Se busca primero en respuestas/, que es donde deberian estar, y
            # si no en el directorio actual: lo normal es arrastrar el archivo
            # recien descargado desde la carpeta de descargas.
            ruta = RESPUESTAS / ruta if (RESPUESTAS / ruta).exists() else Path(args.respuestas)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        print(f"{len(datos['respuestas'])} respuestas de '{datos['persona_id']}'")
        if args.dry_run:
            ok = sum(1 for r in datos["respuestas"] if r["acierto"])
            print(f"  aciertos: {ok}/{len(datos['respuestas'])} "
                  f"({100 * ok / len(datos['respuestas']):.0f} %)")
            return 0
        import psycopg2
        with psycopg2.connect(dsn) as c, c.cursor() as cur:
            n = cargar_respuestas(cur, datos)
        print(f"{n} respuestas cargadas")
        return 0

    origen = SALIDA / f"quiz_piloto_{args.etiqueta}.json"
    if not origen.exists():
        print(f"No existe {origen}")
        return 2
    datos = json.loads(origen.read_text(encoding="utf-8"))
    total = sum(len(v["preguntas"]) for v in datos if not v.get("error"))
    utiles = sum(1 for v in datos if not v.get("error")
                 for p in v["preguntas"] if p.get("sobrevive"))
    print(f"{origen.name}: {len(datos)} videos, {total} preguntas, {utiles} utilizables")

    if args.dry_run:
        print("  (dry-run: no se escribe nada)")
        return 0

    import psycopg2
    with psycopg2.connect(dsn) as c, c.cursor() as cur:
        filas, saltadas = cargar_preguntas(cur, datos)
        cur.execute("select count(*) from quiz_preguntas")
        n_total = cur.fetchone()[0]
    print(f"{filas} preguntas insertadas o actualizadas ({saltadas} saltadas)")
    print(f"quiz_preguntas tiene ahora {n_total} filas")
    return 0


if __name__ == "__main__":
    sys.exit(main())

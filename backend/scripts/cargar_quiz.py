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


def resolver_respuestas(nombre: str):
    """Encuentra el archivo de respuestas, mire donde mire el usuario.

    El .json baja a la carpeta de Descargas del navegador, y de ahi se mueve (o
    no) a respuestas/. La version anterior fallaba con un traceback crudo si el
    nombre no resolvia. Aca se prueban, en orden: la ruta tal cual, dentro de
    respuestas/, y por ultimo una busqueda por patron en respuestas/. Si no
    aparece, se dice claramente que hay disponible en vez de reventar.
    """
    p = Path(nombre)
    if p.exists():
        return p
    if (RESPUESTAS / p.name).exists():
        return RESPUESTAS / p.name
    # busqueda tolerante: "juan-01" encuentra respuestas_juan-01_*.json
    candidatos = sorted(RESPUESTAS.glob(f"*{p.stem}*.json"))
    if len(candidatos) == 1:
        return candidatos[0]
    if len(candidatos) > 1:
        print(f"'{nombre}' coincide con varios; se especifico cual:")
        for c in candidatos:
            print(f"  {c.name}")
        return None
    print(f"No se encontro '{nombre}'.")
    hay = sorted(RESPUESTAS.glob("respuestas_*.json"))
    if hay:
        print(f"En {RESPUESTAS} hay:")
        for c in hay:
            print(f"  {c.name}")
        print("Pasa uno de esos, o usa --todas para cargar todos.")
    else:
        print(f"La carpeta {RESPUESTAS} esta vacia. Mové ahi el .json que "
              "descargaste del quiz.")
    return None


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
                    help="cargar un json de respuestas del quiz HTML (nombre suelto, "
                         "ruta, o el archivo tal cual salio de Descargas)")
    ap.add_argument("--todas", action="store_true",
                    help="cargar TODOS los respuestas_*.json de la carpeta respuestas/. "
                         "Es idempotente: re-cargar no duplica. La forma segura de no "
                         "olvidarse una tanda.")
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

    if args.todas or args.respuestas:
        # Reunir la lista de archivos a cargar.
        if args.todas:
            archivos = sorted(RESPUESTAS.glob("respuestas_*.json"))
            if not archivos:
                print(f"No hay ningun respuestas_*.json en {RESPUESTAS}")
                return 1
        else:
            archivos = [resolver_respuestas(args.respuestas)]
            if archivos[0] is None:
                return 2   # el mensaje ya se imprimio

        # Cargar cada uno. Idempotente por el ON CONFLICT: re-cargar no duplica.
        total = 0
        datasets = []
        for ruta in archivos:
            try:
                d = json.loads(ruta.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                print(f"  {ruta.name}: NO se pudo leer ({e})")
                continue
            if "respuestas" not in d or "persona_id" not in d:
                print(f"  {ruta.name}: no parece un archivo de respuestas (faltan claves)")
                continue
            ok = sum(1 for r in d["respuestas"] if r["acierto"])
            print(f"  {ruta.name}: {len(d['respuestas'])} respuestas de "
                  f"'{d['persona_id']}' · {ok} aciertos")
            datasets.append(d)
            total += len(d["respuestas"])

        if not datasets:
            print("Nada valido para cargar.")
            return 1
        if args.dry_run:
            print(f"(dry-run: {total} respuestas en {len(datasets)} archivos, no se escribe)")
            return 0

        import psycopg2
        try:
            with psycopg2.connect(dsn, connect_timeout=20) as c, c.cursor() as cur:
                cargadas = sum(cargar_respuestas(cur, d) for d in datasets)
                cur.execute("select count(*) from quiz_respuestas")
                en_base = cur.fetchone()[0]
        except psycopg2.Error as e:
            # El error real de la base, sin el traceback de Python encima.
            print(f"\nERROR de la base: {str(e).strip().splitlines()[0]}")
            return 1
        print(f"\n{cargadas} respuestas cargadas · quiz_respuestas tiene {en_base} filas")
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

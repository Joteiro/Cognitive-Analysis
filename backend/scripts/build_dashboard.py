#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_dashboard.py — arma el dashboard de la dieta cognitiva.

Lee las filas ya medidas de content_features (los percentiles los calculo el
backend con nutriscore_features.py contra escala_referencia.json), les pega la
fecha de visionado y el canal de content_items, y las inyecta en
plantilla_dashboard.html.

El HTML NO mide nada: agrupa, ordena y dibuja percentiles que ya venian
calculados. Es la misma regla que en la extension — cero logica duplicada en
JavaScript, y por lo tanto cero deriva entre lo que mide el estudio y lo que
muestra la pantalla.

Uso:
    .venv\\Scripts\\python build_dashboard.py
    .venv\\Scripts\\python build_dashboard.py --fuente instantanea
    .venv\\Scripts\\python build_dashboard.py --salida ..\\..\\docs

--fuente instantanea usa docs/dashboard_filas.json en vez de la base, para poder
reconstruir el HTML sin conexion (y para que el anexo de la memoria sea
reproducible por quien no tenga las credenciales).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent.parent / "docs"
PLANTILLA = HERE / "plantilla_dashboard.html"

# Los percentiles se guardan en content_features.panel, un jsonb con los 8
# descriptores SIEMPRE en este orden. El orden importa: el HTML los indexa por
# posicion para que cada fila del JSON pese poco.
PANEL_ORDEN = [
    "ritmo_ppm", "cifras_100w", "atribucion_1000w", "mattr_200",
    "conectores_1000w", "enlaces_externos", "promocional_1000w", "cobertura_titulo",
]

FORMATOS = ["informativo", "entretenimiento", "deporte_gaming", "practico_personal"]

# Las fechas de visionado se cortan en la zona del usuario, no en UTC: un video
# de las 23:30 de Paris cae el mismo dia, no el siguiente.
#
# Windows NO trae base de zonas horarias, asi que zoneinfo depende del paquete
# tzdata y sin el revienta al importar. En vez de morir, se cae a la regla de la
# UE aplicada a mano. Vale para 1996 en adelante y da exactamente lo mismo que
# tzdata; si tzdata esta instalado, se usa tzdata y esto no corre.
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Paris")
except Exception:                      # ImportError o ZoneInfoNotFoundError
    TZ = None


def _ultimo_domingo(anio: int, mes: int) -> datetime:
    """El cambio de hora en la UE es a las 01:00 UTC del ultimo domingo."""
    d = datetime(anio, mes, 31, 1, 0, tzinfo=timezone.utc)   # marzo y octubre tienen 31
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


def a_local(dt: datetime) -> datetime:
    """Pasa un instante a hora de Paris, con o sin tzdata."""
    dt = dt.astimezone(timezone.utc)
    if TZ is not None:
        return dt.astimezone(TZ)
    verano = _ultimo_domingo(dt.year, 3) <= dt < _ultimo_domingo(dt.year, 10)
    return dt.astimezone(timezone(timedelta(hours=2 if verano else 1)))

SQL = """
SELECT i.title, i.channel, f.formato, i.watched_at, f.duration_seconds,
       f.n_words, f.panel
  FROM content_features f
  JOIN content_items    i ON i.id = f.content_item_id
 WHERE i.watched_at IS NOT NULL
   AND f.panel IS NOT NULL
 ORDER BY i.watched_at, i.id
"""

try:
    import psycopg
    from psycopg.rows import dict_row
    _PG = "psycopg3"
except ImportError:
    try:
        import psycopg2 as psycopg
        from psycopg2.extras import RealDictCursor
        _PG = "psycopg2"
    except ImportError:
        psycopg = None
        _PG = None

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


# ------------------------------------------------------------------ CARGA

def conectar(dsn: str):
    if psycopg is None:
        raise RuntimeError(
            "No hay driver de PostgreSQL. Estas usando el Python del sistema:\n"
            "    .venv\\Scripts\\python build_dashboard.py")
    if _PG == "psycopg3":
        return psycopg.connect(dsn, row_factory=dict_row)
    return psycopg.connect(dsn)


def cargar_de_base(dsn: str) -> list[list]:
    with conectar(dsn) as conn:
        if _PG == "psycopg3":
            with conn.cursor() as cur:
                cur.execute(SQL)
                crudas = cur.fetchall()
        else:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(SQL)
                crudas = cur.fetchall()
    return [fila_compacta(r) for r in crudas]


def fila_compacta(r: dict) -> list:
    """Una fila del dashboard: [titulo, canal, formato, fecha, min, palabras, p0..p7]."""
    panel = r["panel"]
    if isinstance(panel, str):          # psycopg2 devuelve jsonb como texto si no hay adaptador
        panel = json.loads(panel)
    por_clave = {d["clave"]: d for d in panel}
    faltan = [k for k in PANEL_ORDEN if k not in por_clave]
    if faltan:
        raise ValueError(f"El panel de «{r['title'][:40]}» no trae {faltan}. "
                         "Se aborta: reindexar por posicion con un panel incompleto "
                         "correria los percentiles de descriptor sin avisar.")
    pcts = []
    for k in PANEL_ORDEN:
        v = por_clave[k].get("percentil")
        pcts.append(None if v is None else int(round(float(v))))
    return [
        r["title"] or "(sin titulo)",
        r["channel"] or "(sin canal)",
        r["formato"],
        a_local(r["watched_at"]).strftime("%Y-%m-%d"),
        round((r["duration_seconds"] or 0) / 60.0, 1),
        r["n_words"],
        *pcts,
    ]


SQL_PENDIENTES = """
SELECT count(*) FILTER (WHERE i.transcript IS NOT NULL AND f.id IS NULL) AS sin_panel,
       count(*) FILTER (WHERE i.transcript IS NULL)                      AS sin_transcripcion
  FROM content_items i
  LEFT JOIN content_features f ON f.content_item_id = i.id
 WHERE i.corpus IS DISTINCT FROM 'referencia'
   AND i.watched_at IS NOT NULL
"""


def pendientes(dsn: str) -> tuple[int, int]:
    """Cuantos videos vistos quedaron afuera del dashboard, y por que.

    Sin esto el script dice '79 videos' y da la sensacion de estar completo,
    cuando puede haber decenas esperando un paso anterior. Un numero solo no
    distingue 'no hay nada nuevo' de 'falta correr algo'.
    """
    with conectar(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_PENDIENTES)
            fila = cur.fetchone()
    return (fila["sin_panel"], fila["sin_transcripcion"]) if isinstance(fila, dict) \
        else (fila[0], fila[1])


def cargar_meta(escala: Path) -> dict:
    """Se queda con lo que el HTML necesita declarar, no con las grillas de 101
    percentiles: el navegador no reubica nada, sólo dice contra qué vara se midió."""
    d = json.loads(escala.read_text(encoding="utf-8"))
    out = {"frame_version": d["frame_version"], "corpus": d["corpus"], "descriptores": {}}
    for k, v in d["descriptores"].items():
        ref, e = v["referencia"], {
            "tipo": v["tipo"], "ambito": v["ambito"], "unidad": v["unidad"],
            "p_perm": v["p_permutacion"], "ref": {},
        }
        claves = FORMATOS + ["_todos"] if v["ambito"] == "por_formato" else ["_todos"]
        for f in claves:
            r = ref.get(f) if v["ambito"] == "por_formato" else ref
            if not r:
                continue
            e["ref"][f] = ({"n": r["n"], "n_pres": r["n_presentes"],
                            "p_aus": round(r["p_ausencia"], 4),
                            "med_pres": r["mediana_presentes"]}
                           if v["tipo"] == "presencia"
                           else {"n": r["n"], "p50": r["p50"]})
        out["descriptores"][k] = e
    return out


# ------------------------------------------------------------------ SALIDA

def escribir(filas: list[list], meta: dict, salida: Path) -> Path:
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    for marca in ("__DATOS__", "__META__"):
        if marca not in plantilla:
            raise ValueError(f"La plantilla no tiene el marcador {marca}.")
    datos = "[\n" + ",\n".join(json.dumps(f, ensure_ascii=False) for f in filas) + "\n]"
    html = (plantilla
            .replace("__DATOS__", datos)
            .replace("__META__", json.dumps(meta, ensure_ascii=False, indent=1)))
    destino = salida / "dieta_cognitiva.html"
    destino.write_text(html, encoding="utf-8")
    return destino


def main() -> int:
    p = argparse.ArgumentParser(description="Arma el dashboard de la dieta cognitiva.")
    p.add_argument("--fuente", choices=["base", "instantanea"], default="base",
                   help="de donde salen las filas (por defecto: la base)")
    p.add_argument("--salida", default=str(DOCS), help="carpeta de salida")
    p.add_argument("--escala", default=None, help="ruta de escala_referencia.json")
    args = p.parse_args()

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    escala = Path(args.escala) if args.escala else salida / "escala_referencia.json"
    if not escala.exists():
        print(f"No encuentro {escala}. Corre antes build_reference_scale.py.", file=sys.stderr)
        return 2

    instantanea = salida / "dashboard_filas.json"
    if args.fuente == "base":
        env = HERE.parent / ".env"
        if load_dotenv and env.exists():
            load_dotenv(env)
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            print("Falta DATABASE_URL en backend/.env", file=sys.stderr)
            return 2
        filas = cargar_de_base(dsn)
        # La instantanea se reescribe en cada corrida contra la base: es la copia
        # que permite rearmar el HTML sin credenciales, y va al anexo.
        instantanea.write_text(
            "[\n" + ",\n".join(json.dumps(f, ensure_ascii=False) for f in filas) + "\n]",
            encoding="utf-8")
    else:
        if not instantanea.exists():
            print(f"No encuentro {instantanea}. Corre una vez con --fuente base.",
                  file=sys.stderr)
            return 2
        filas = json.loads(instantanea.read_text(encoding="utf-8"))

    if not filas:
        print("No hay filas medidas con fecha de visionado.", file=sys.stderr)
        return 1

    meta = cargar_meta(escala)
    destino = escribir(filas, meta, salida)

    fechas = sorted(f[3] for f in filas)
    canales = {f[1] for f in filas}
    minutos = sum(f[4] for f in filas)
    print(f"Fuente        : {args.fuente}")
    print(f"Zona horaria  : {'tzdata (Europe/Paris)' if TZ else 'regla UE a mano (sin tzdata)'}")
    print(f"Videos        : {len(filas)}  ({len(canales)} canales, {minutos:.0f} min)")
    print(f"Rango         : {fechas[0]} a {fechas[-1]}")
    print(f"Escala        : {meta['frame_version']}  ({meta['corpus']['n_apto_panel']} aptos)")
    print(f"Generado      : {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print(f"Salida        : {destino}")

    if args.fuente == "base":
        sin_panel, sin_txt = pendientes(dsn)
        if sin_panel or sin_txt:
            print()
            print("Quedaron afuera:")
            if sin_panel:
                print(f"  {sin_panel} con transcripcion pero sin panel  ->  python backfill_panel.py")
            if sin_txt:
                print(f"  {sin_txt} sin transcripcion todavia          ->  python enrich_local.py")
                print("     (baja subtitulos con yt_dlp; no gasta creditos de Supadata, pero va")
                print("      lento a proposito: 10 por hora para no despertar al antibot)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backfill_panel.py — calcula el panel de los videos que ya estan en la base.

QUE HACE
--------
Busca los videos que tienen transcripcion pero todavia no tienen fila en
content_features, y le pide el panel al backend UNO POR UNO. Como /panel
guarda lo que calcula, la fila queda escrita sola.

NO GASTA CREDITOS DE SUPADATA
-----------------------------
Esto es lo importante y conviene entender por que. /panel solo LEE de la base:
usa la transcripcion que ya esta guardada. La unica parte del sistema que
llama a Supadata es el enriquecimiento que dispara POST /videos, y este script
no lo toca. Se puede correr las veces que haga falta sin gastar un credito.

POR QUE PASA POR EL BACKEND Y NO CALCULA ACA
--------------------------------------------
Seria mas rapido importar nutriscore_features y escribir en la base directo.
Y seria un error: habria dos caminos distintos calculando lo mismo, y el dia
que se ajuste una definicion, los videos del historial y los que se miran en
vivo empezarian a medirse distinto sin que nada avise. Un solo camino, aunque
sea mas lento.

USO
    python backfill_panel.py --dry-run          # solo dice cuantos faltan
    python backfill_panel.py                    # historial (por defecto)
    python backfill_panel.py --corpus referencia
    python backfill_panel.py --corpus todos --limite 10

Es seguro cortarlo con Ctrl+C y volver a correrlo: los que ya se hicieron no
se repiten, porque la consulta solo trae los que no tienen fila.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Falta 'requests'. Corre con el Python del venv:\n"
             "   backend\\scripts\\.venv\\Scripts\\python backfill_panel.py")

try:
    import psycopg2
except ImportError:
    sys.exit("Falta 'psycopg2'. Corre con el Python del venv.")

API = os.getenv("API_BASE", "https://cognitive-analysis-gfpg.onrender.com")

SQL = """
SELECT ci.external_id, left(ci.title, 60) AS titulo
  FROM content_items ci
  LEFT JOIN content_features cf ON cf.content_item_id = ci.id
 WHERE coalesce(btrim(ci.transcript), '') <> ''
   AND cf.id IS NULL
   {filtro}
 ORDER BY ci.created_at
"""


def cargar_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        env = Path(__file__).resolve().parent.parent / ".env"
        try:
            from dotenv import load_dotenv
            load_dotenv(env)
        except ImportError:
            pass
        dsn = os.getenv("DATABASE_URL")
    if not dsn:
        sys.exit("No hay DATABASE_URL. Ponela en backend/.env")
    return dsn


def pedir_panel(vid: str, timeout: int) -> tuple[str, str]:
    """Devuelve (resultado, detalle). Nunca lanza."""
    try:
        r = requests.get(f"{API}/panel/{vid}", timeout=timeout)
    except Exception as e:
        return "error_red", str(e)[:80]
    if r.status_code != 200:
        return f"http_{r.status_code}", r.text[:80]
    try:
        d = r.json()
    except ValueError:
        return "no_json", r.text[:80]

    if d.get("apto") is True:
        # 'recalculado' viene en false cuando la respuesta salio del cache. Si
        # aparece en un backfill es senal de que la fila ya existia.
        return ("ok" if d.get("recalculado") else "ya_estaba"), d.get("formato") or ""
    if d.get("apto") is False:
        return "no_apto", d.get("motivo") or ""
    return "procesando", d.get("mensaje") or ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="historial",
                    choices=["historial", "referencia", "todos"])
    ap.add_argument("--limite", type=int, default=0,
                    help="procesar solo los primeros N (0 = todos)")
    ap.add_argument("--pausa", type=float, default=1.0,
                    help="segundos entre pedidos (default 1)")
    ap.add_argument("--dry-run", action="store_true",
                    help="solo contar, no pedir nada")
    args = ap.parse_args()

    filtro = ("" if args.corpus == "todos"
              else f"AND ci.corpus = '{args.corpus}'")

    with psycopg2.connect(cargar_dsn(), connect_timeout=20) as cn:
        with cn.cursor() as cur:
            cur.execute(SQL.format(filtro=filtro))
            pendientes = cur.fetchall()

    if args.limite:
        pendientes = pendientes[:args.limite]

    print("=" * 66)
    print(f"corpus   {args.corpus}")
    print(f"api      {API}")
    print(f"faltan   {len(pendientes)} videos con transcripcion y sin panel")
    print("=" * 66)

    if not pendientes:
        print("No hay nada que hacer.")
        return 0
    if args.dry_run:
        for vid, tit in pendientes[:15]:
            print(f"   {vid}  {tit}")
        if len(pendientes) > 15:
            print(f"   ... y {len(pendientes) - 15} mas")
        print("\nSin --dry-run, se piden todos. No gasta creditos de Supadata.")
        return 0

    # El primer pedido puede tardar ~1 minuto: despierta el servicio dormido
    # de Render. Los siguientes son rapidos.
    print("El primer pedido puede tardar un minuto (despierta el servidor).\n")

    cuenta: dict[str, int] = {}
    for i, (vid, tit) in enumerate(pendientes, 1):
        res, det = pedir_panel(vid, timeout=120 if i == 1 else 60)
        cuenta[res] = cuenta.get(res, 0) + 1
        marca = {"ok": "OK  ", "ya_estaba": "=   ", "no_apto": "--  "}.get(res, "!!  ")
        print(f"{marca}[{i}/{len(pendientes)}] {vid}  {tit[:42]:<42} {res} {det[:28]}")
        if i < len(pendientes):
            time.sleep(args.pausa)

    print("\n" + "=" * 66)
    for k in sorted(cuenta):
        print(f"   {k:<14} {cuenta[k]}")
    print("=" * 66)
    print("\nQue significa cada uno:")
    print("  ok         se calculo y se guardo la fila")
    print("  no_apto    el video no tiene suficiente habla para medirlo.")
    print("             Tambien se guarda: que un video no se pueda medir es")
    print("             un dato, no un hueco.")
    print("  procesando la fila existe pero le falta algo; se puede reintentar")
    print("  http_/!!   fallo la peticion. Volver a correr el script: los que")
    print("             ya se hicieron no se repiten.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnostico_deploy.py — por que Render no esta sirviendo el codigo nuevo.

EL PROBLEMA QUE RESUELVE
------------------------
Render, cuando un build falla, NO te deja sin servicio: sigue sirviendo el
deploy anterior que si funcionaba. Es lo correcto en produccion y es una
trampa en desarrollo, porque la API responde 200 a todo y parece que anda,
mientras corre codigo de hace tres dias.

Sintoma comprobado el 2026-08-13:
  - /openapi.json no lista /panel
  - /panel/<id> devuelve 404
  - content_scores fila 99, escrita hoy 15:18, scorer_version 1.0
    (el scorer que se supone jubilado)

Este script contesta tres preguntas sin adivinar:
  1. Que hay en tu carpeta local (los archivos nuevos, estan?)
  2. Que hay commiteado y pusheado (git lo sabe)
  3. Que esta vivo en Render (se le pregunta a la API)

Y de paso vuelca fetch_video_metadata, que necesito para el parche de
channel_id / video_language.

NO imprime contrasenas ni el contenido de .env.

USO
    python diagnostico_deploy.py
    python diagnostico_deploy.py --repo C:\\ruta\\al\\repo
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

API_BASE = os.getenv("API_BASE", "https://cognitive-analysis-gfpg.onrender.com")

# Cada archivo con una "huella": un texto que SOLO existe en la version nueva.
# Buscar la huella es mas confiable que mirar la fecha del archivo, que cambia
# por cualquier motivo.
HUELLAS = {
    "backend/app/transcript_api.py": [
        ("fetch_transcript_detallado", "devuelve metadatos, no solo texto"),
        ('mode": "native"',            "prohibe el fallback a Whisper"),
        ("IDIOMAS",                    "pide espanol primero"),
    ],
    "backend/app/routes/videop.py": [
        ("run_enrichment",             "el scorer de letras esta jubilado"),
        ("transcript_word_count",      "persiste los metadatos del transcript"),
    ],
    "backend/app/routes/panel.py": [
        ("router = APIRouter",         "el endpoint existe"),
        ("aviso_idioma",               "avisa si el texto no esta en espanol"),
    ],
    "backend/app/main.py": [
        ("panel",                      "main.py monta el router del panel"),
    ],
    "backend/app/escala_referencia.json": [
        ("frame_version",              "la escala viaja con el deploy"),
    ],
    "requirements.txt": [
        ("pandas",                     "pandas (lo necesita nutriscore_features)"),
        ("numpy",                      "numpy"),
    ],
    "cognitive-analysis-ext/content.js": [
        ("/panel/",                    "la extension pide el panel"),
    ],
}

VERDE, ROJO, GRIS = "OK   ", "FALTA", "  -  "


def sh(cmd: list[str], cwd: Path) -> str:
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True,
                           text=True, timeout=30, encoding="utf-8",
                           errors="replace")
        return (r.stdout or r.stderr or "").strip()
    except Exception as e:
        return f"(no se pudo: {e})"


def titulo(t: str) -> None:
    print()
    print("=" * 72)
    print(t)
    print("=" * 72)


# ─────────────────────────────────────────────────────── 1. archivos locales

def revisar_archivos(repo: Path) -> dict:
    titulo("1. QUE HAY EN TU CARPETA")
    estado = {}
    for rel, marcas in HUELLAS.items():
        p = repo / rel
        if not p.exists():
            print(f"{ROJO}  {rel}  -> el archivo no existe")
            estado[rel] = "ausente"
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        h = hashlib.sha1(txt.encode("utf-8", "replace")).hexdigest()[:8]
        faltan = [d for m, d in marcas if m not in txt]
        if faltan:
            print(f"{ROJO}  {rel}  [{h}]  -> version VIEJA")
            for d in faltan:
                print(f"           le falta: {d}")
            estado[rel] = "viejo"
        else:
            print(f"{VERDE}  {rel}  [{h}]")
            estado[rel] = "nuevo"
    return estado


# ────────────────────────────────────────────────────────────────── 2. git

def revisar_git(repo: Path) -> None:
    titulo("2. QUE ESTA COMMITEADO Y PUSHEADO")
    if not (repo / ".git").exists():
        print("No hay repositorio git en esta carpeta.")
        print("Entonces Render no puede estar tomando el codigo de aca.")
        return

    print("Ultimo commit local:")
    print("  " + sh(["git", "log", "-1", "--format=%h  %ad  %s",
                     "--date=format:%Y-%m-%d %H:%M"], repo))

    rama = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)
    print(f"Rama: {rama}")

    sucio = sh(["git", "status", "--porcelain"], repo)
    if sucio:
        print("\nCAMBIOS SIN COMMITEAR  <-- si aparecen los archivos del panel,")
        print("                           el codigo nuevo nunca salio de tu maquina:")
        for linea in sucio.splitlines():
            print("  " + linea)
    else:
        print("\nNo hay cambios sin commitear.")

    sin_push = sh(["git", "log", f"origin/{rama}..HEAD",
                   "--format=%h %s"], repo)
    if sin_push and "no se pudo" not in sin_push and "unknown revision" not in sin_push:
        print("\nCOMMITS SIN PUSHEAR  <-- estan en tu maquina, no en GitHub,")
        print("                         asi que Render no los vio:")
        for linea in sin_push.splitlines():
            print("  " + linea)
    elif "unknown revision" in sin_push:
        print("\nNo hay rama remota configurada (origin/%s no existe)." % rama)
    else:
        print("\nTodo lo commiteado esta pusheado.")


# ─────────────────────────────────────────────────────────────── 3. Render

def revisar_render() -> None:
    titulo(f"3. QUE ESTA VIVO EN RENDER  ({API_BASE})")
    try:
        import requests
    except ImportError:
        print("requests no esta en este Python. Corre con el del venv:")
        print("   backend\\scripts\\.venv\\Scripts\\python diagnostico_deploy.py")
        return

    # El primer request puede tardar ~50 s: el plan gratuito duerme el servicio.
    try:
        r = requests.get(f"{API_BASE}/openapi.json", timeout=90)
    except Exception as e:
        print(f"No se pudo llegar a la API: {e}")
        return

    if r.status_code != 200:
        print(f"/openapi.json devolvio {r.status_code}. El servicio esta caido.")
        return

    rutas = sorted((r.json().get("paths") or {}).keys())
    print("Rutas que la API dice tener:")
    for ruta in rutas:
        print("   " + ruta)

    tiene_panel = any(x.startswith("/panel") for x in rutas)
    tiene_score = any("score" in x for x in rutas)

    print()
    if tiene_panel:
        print(f"{VERDE}  /panel existe -> el codigo nuevo ESTA desplegado")
    else:
        print(f"{ROJO}  /panel NO existe -> Render corre codigo viejo")
    if tiene_score:
        print(f"{GRIS}  /videos/by-youtube/.../score sigue montado")
        print("        (no molesta: la extension ya no lo usa)")


# ───────────────────────────────────────────────── 4. volcado de youtube_api

def volcar_youtube_api(repo: Path) -> None:
    titulo("4. fetch_video_metadata (pegame esto entero)")
    p = repo / "backend" / "app" / "youtube_api.py"
    if not p.exists():
        print(f"No encuentro {p}")
        return
    txt = p.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^def fetch_video_metadata.*?(?=^def |\Z)", txt,
                  re.S | re.M)
    print(m.group(0).rstrip() if m else txt[:3000])


# ────────────────────────────────────────────────────────────── veredicto

def veredicto(estado: dict) -> None:
    titulo("VEREDICTO")
    viejos = [k for k, v in estado.items() if v in ("viejo", "ausente")]
    if viejos:
        print("Los archivos nuevos NO estan en tu carpeta (o estan a medias):")
        for v in viejos:
            print("   " + v)
        print("\n-> El codigo nuevo nunca llego a tu maquina. Te los vuelvo a pasar.")
    else:
        print("Los archivos nuevos SI estan en tu carpeta.")
        print("-> Mira arriba git y Render para saber donde se corto la cadena:")
        print("   sin commitear  -> falta 'git add . && git commit && git push'")
        print("   sin pushear    -> falta 'git push'")
        print("   pusheado pero /panel no existe -> el BUILD de Render fallo.")
        print("      Render -> tu servicio -> Logs -> el ultimo deploy en rojo.")
        print("      Buscar 'ModuleNotFoundError' o 'Error' cerca del final.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=None,
                    help="raiz del repo (por defecto, se busca sola)")
    args = ap.parse_args()

    if args.repo:
        repo = Path(args.repo).resolve()
    else:
        # subir hasta encontrar la carpeta que tiene backend/
        repo = Path(__file__).resolve().parent
        for _ in range(4):
            if (repo / "backend").is_dir():
                break
            repo = repo.parent

    print(f"repo   {repo}")
    print(f"ahora  {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")

    if not (repo / "backend").is_dir():
        print("\nNo encuentro la carpeta 'backend'. Pasa la ruta con --repo")
        return 2

    estado = revisar_archivos(repo)
    revisar_git(repo)
    revisar_render()
    volcar_youtube_api(repo)
    veredicto(estado)
    return 0


if __name__ == "__main__":
    sys.exit(main())

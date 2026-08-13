#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
calibrar_supadata.py  v1.0
Mide cuanto se corren los 8 descriptores al cambiar de instrumento de
transcripcion: subtitulos propios de YouTube (con los que se construyo la
escala) contra Supadata (con los que funcionaria el panel).

POR QUE ESTO VA ANTES QUE EL PANEL
----------------------------------
La escala de referencia se calculo sobre 382 transcripciones `youtube_auto` y
13 `youtube_manual`. Cero Supadata. Y Supadata no devuelve el subtitulo crudo:
las 6 que hay en la base tienen puntuacion cada 16,4 palabras, las 6 sin
excepcion, cuando el ASR de YouTube da 635. Eso es texto post-procesado.
Medir con un instrumento y comparar contra una escala graduada con otro es
pesar en gramos y leer una tabla en onzas. Puede dar igual o puede no dar
igual: eso es lo que mide este script.

COMO LO MIDE
------------
Comparacion PAREADA: el mismo video, los mismos metadatos, cambiando solo el
texto de la transcripcion. Todo lo que se mueva es el instrumento, porque no
hay nada mas que pueda haberse movido.

LA CIFRA QUE DECIDE
-------------------
No es la correlacion. Es **cuantos videos cambian de tramo de percentil** al
medirlos con el otro instrumento. Si un video pasa de p60 a p58, no importa.
Si pasa de p60 a p85, la escala no se puede reutilizar y hay que recalibrarla
con transcripciones de Supadata.

SEGURIDAD
---------
Este script NO escribe en content_items. Las transcripciones de Supadata se
guardan en un archivo aparte. Pisar las `youtube_auto` del corpus destruiria
la escala y no habria vuelta atras.

USO
---
    .venv\\Scripts\\python calibrar_supadata.py --n 20
    .venv\\Scripts\\python calibrar_supadata.py --cache     # sin gastar creditos

Necesita SUPADATA_API_KEY en backend/.env (en Render ya esta, pero este script
corre local).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent.parent / "docs"
sys.path.insert(0, str(HERE))

import nutriscore_features as nf                    # noqa: E402
import build_reference_scale as brs                 # noqa: E402

CACHE = HERE / "calibracion_supadata_cache.json"
SUPADATA_URL = "https://api.supadata.ai/v1/transcript"
VERSION = "1.0"


# ------------------------------------------------------------------ SUPADATA

def pedir_supadata(video_id: str, api_key: str, timeout: int = 60) -> dict:
    """Devuelve {'texto': str|None, 'estado': str}. No lanza: un fallo en un
    video no debe tumbar la corrida entera."""
    try:
        # mode=native: prohibe el fallback a Whisper.
        # Sin esto, un video cuyos subtitulos nativos Supadata no logra bajar se
        # transcribe con Whisper, que cobra POR MINUTO DE AUDIO. El 2026-08-12
        # una sola llamada asi consumio 134 creditos de golpe y agoto el plan,
        # y encima era un video que SI tiene subtitulos en la base: Supadata se
        # choco con el mismo bloqueo de timedtext que nosotros y cayo al plan
        # caro sin avisar. Un 202 es la senal de que eso paso.
        r = requests.get(
            SUPADATA_URL,
            params={"url": f"https://www.youtube.com/watch?v={video_id}",
                    "text": "true", "mode": "native"},
            headers={"x-api-key": api_key},
            timeout=timeout,
        )
    except Exception as e:
        return {"texto": None, "estado": f"excepcion: {e}"}

    if r.status_code == 429:
        # Cuota del plan agotada. Se marca aparte para que el bucle corte en vez
        # de seguir pegandole a una puerta cerrada trece veces mas.
        return {"texto": None, "estado": "cuota_agotada", "cortar": True}
    if r.status_code == 202:
        # Whisper arrancado pese al mode=native. Se CORTA la corrida entera: no
        # se sabe cuanto va a costar ese job y el de al lado puede costar igual.
        return {"texto": None, "cortar": True,
                "estado": "202: Supadata arranco Whisper (cobra por minuto). "
                          "Corrida abortada para no quemar creditos."}
    if r.status_code != 200:
        return {"texto": None, "estado": f"HTTP {r.status_code}: {r.text[:120]}"}
    try:
        d = r.json()
    except ValueError:
        return {"texto": None, "estado": "respuesta no JSON"}

    c = d.get("content")
    if isinstance(c, str):
        t = c
    elif isinstance(c, list):
        t = " ".join(s.get("text", "") for s in c if isinstance(s, dict))
    else:
        return {"texto": None, "estado": "job asincrono o formato desconocido"}
    t = " ".join(t.split()).strip()
    # `lang` dice el idioma; algunos planes devuelven tambien de donde salio
    return {"texto": t or None, "estado": "ok" if t else "vacio",
            "lang": d.get("lang"), "meta": {k: v for k, v in d.items()
                                            if k not in ("content",)}}


# ------------------------------------------------------------------ MUESTRA

def elegir_videos(dsn: str, n: int, semilla: int) -> pd.DataFrame:
    """Videos del corpus con transcripcion de YouTube y aptos, repartidos por
    macroformato para que la calibracion no quede sesgada a un solo tipo."""
    df = brs.cargar(dsn, "referencia")
    df = df[(df["transcript_word_count"].fillna(0) > 0)
            & (df["transcript_source"].isin(["youtube_auto", "youtube_manual"]))]
    F = brs.calcular(df)
    aptos = set(F.loc[F["v_apto_panel"] == 1, "external_id"])
    df = df[df["external_id"].isin(aptos)]

    por_celda = max(1, n // 4)
    partes = []
    for fmt in brs.FORMATOS:
        sub = df[df["stratum_format"] == fmt]
        if len(sub):
            partes.append(sub.sample(min(por_celda, len(sub)), random_state=semilla))
    return pd.concat(partes).reset_index(drop=True) if partes else df.head(0)


# ------------------------------------------------------------------ COMPARAR

def descriptores_de(fila: dict, transcripcion: str) -> dict:
    """Calcula los 8 descriptores de una fila cambiandole SOLO el texto."""
    r = dict(fila)
    r["transcript"] = transcripcion or ""
    r["transcript_word_count"] = len((transcripcion or "").split())
    df = pd.DataFrame([r])
    for c in brs.JSONB:
        if c in df.columns:
            df[c] = df[c].apply(lambda v: v if isinstance(v, str) or v is None
                                else json.dumps(v, ensure_ascii=False))
    out = brs.calcular(df).iloc[0].to_dict()
    return out


def comparar(pares: list[dict], escala: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """pares = [{'external_id','yt':{...},'sd':{...},'formato':...}, ...]"""
    with warnings.catch_warnings(), np.errstate(invalid="ignore", divide="ignore"):
        warnings.simplefilter("ignore")   # columnas constantes al correlacionar
        return _comparar(pares, escala)


def _comparar(pares: list[dict], escala: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    filas = []
    for p in pares:
        base = {"external_id": p["external_id"], "titulo": p["titulo"],
                "formato": p["formato"],
                "palabras_yt": p["yt"].get("transcript_word_count")
                               or p["yt"].get("v_tiene_transcripcion"),
                "palabras_sd": p["palabras_sd"],
                "apto_yt": p["yt"]["v_apto_panel"], "apto_sd": p["sd"]["v_apto_panel"]}
        for k in brs.PANEL:
            vy, vs = p["yt"].get(k), p["sd"].get(k)
            base[f"{k}__yt"] = vy
            base[f"{k}__sd"] = vs
            cfg, ref = brs._ref_de(escala, k, p["formato"])
            grid = (ref or {}).get("grid") or (ref or {}).get("grid_presentes")
            base[f"{k}__pct_yt"] = brs.percentil_desde_grid(vy, grid) if grid else np.nan
            base[f"{k}__pct_sd"] = brs.percentil_desde_grid(vs, grid) if grid else np.nan
        filas.append(base)
    D = pd.DataFrame(filas)

    res = []
    for k in brs.PANEL:
        y = pd.to_numeric(D[f"{k}__yt"], errors="coerce")
        s = pd.to_numeric(D[f"{k}__sd"], errors="coerce")
        py = pd.to_numeric(D[f"{k}__pct_yt"], errors="coerce")
        ps = pd.to_numeric(D[f"{k}__pct_sd"], errors="coerce")
        ok = y.notna() & s.notna()
        if ok.sum() < 3:
            res.append({"descriptor": k, "n": int(ok.sum())})
            continue
        # cambio relativo mediano; se evita dividir por cero
        rel = ((s[ok] - y[ok]) / y[ok].replace(0, np.nan)).abs().median()
        dpct = (ps - py).abs()
        # Los dos tramos tienen que existir para poder decir que cambio. Si
        # alguno es nulo no es un cambio, es un dato que falta, y contarlo como
        # cambio inflaria el veredicto justo en la cifra que decide todo.
        tramo = lambda v: pd.cut(v, [-0.1, 33, 67, 100], labels=["b", "m", "a"])
        ty, ts_ = tramo(py), tramo(ps)
        comparables = ty.notna() & ts_.notna()
        cambio_tramo = (ty != ts_) & comparables
        res.append({
            "descriptor": k,
            "n": int(ok.sum()),
            "corr_pearson": round(float(y[ok].corr(s[ok])), 3),
            # Spearman a mano: es Pearson sobre los rangos. pandas lo delega en
            # scipy, que no esta en el entorno y no vale 30 MB de dependencia
            # por una linea.
            "corr_spearman": round(float(y[ok].rank().corr(s[ok].rank())), 3),
            "cambio_relativo_mediano": (round(float(rel), 3) if pd.notna(rel) else None),
            "desplaz_percentil_mediano": (round(float(dpct.median()), 1)
                                          if dpct.notna().any() else None),
            "desplaz_percentil_p90": (round(float(dpct.quantile(.9)), 1)
                                      if dpct.notna().any() else None),
            "n_comparables": int(comparables.sum()),
            "pct_cambian_de_tramo": (round(100 * float(cambio_tramo.sum())
                                           / int(comparables.sum()), 0)
                                     if comparables.sum() else None),
        })
    return D, pd.DataFrame(res)


def informe(D: pd.DataFrame, R: pd.DataFrame, meta: dict) -> str:
    L, A = [], None
    A = L.append
    A("# Calibracion: subtitulos de YouTube contra Supadata\n")
    A(f"**Generado:** {meta['generado']} · **n = {meta['n']}** videos del corpus "
      "de referencia, pareados (mismo video, mismos metadatos, sola diferencia "
      "el texto de la transcripcion).\n")
    A("La escala se construyo con subtitulos propios de YouTube. Si el panel va "
      "a funcionar con Supadata, hay que saber cuanto corre eso las mediciones.\n")

    A("\n## Volumen de texto\n")
    A(f"- Palabras con YouTube: mediana **{meta['pal_yt']:.0f}**")
    A(f"- Palabras con Supadata: mediana **{meta['pal_sd']:.0f}** "
      f"({meta['dif_pal']:+.1f} % respecto de YouTube)")
    A(f"- Videos que dejan de ser aptos al cambiar de fuente: "
      f"**{meta['pierden_aptitud']}** de {meta['n']}\n")

    A("\n## Desplazamiento por descriptor\n")
    A("| descriptor | n | corr Pearson | corr Spearman | cambio rel. mediano | "
      "desplaz. percentil (mediana / p90) | % que cambian de tramo |")
    A("|---|---|---|---|---|---|---|")
    for _, r in R.iterrows():
        if pd.isna(r.get("corr_pearson")):
            A(f"| {r['descriptor']} | {r['n']} | — | — | — | — | — |")
            continue
        marca = " ⚠️" if (r["pct_cambian_de_tramo"] or 0) >= 25 else ""
        A(f"| {r['descriptor']} | {r['n']} | {r['corr_pearson']} | "
          f"{r['corr_spearman']} | {r['cambio_relativo_mediano']} | "
          f"{r['desplaz_percentil_mediano']} / {r['desplaz_percentil_p90']} | "
          f"{r['pct_cambian_de_tramo']:.0f}%{marca} |")

    A("\n**La columna que decide es la ultima.** La correlacion puede ser alta y "
      "aun asi el panel mentir: si Supadata mide sistematicamente 20 % mas alto, "
      "la correlacion da 0,99 y todos los videos suben de tramo igual. Lo que "
      "importa es cuantos videos quedarian en un cajon distinto.\n")

    peor = R["pct_cambian_de_tramo"].max() if "pct_cambian_de_tramo" in R else None
    if peor is None or pd.isna(peor):
        A("\n> Sin datos suficientes para concluir.\n")
    elif peor < 15:
        A(f"\n> **Veredicto: la escala se puede reutilizar.** El descriptor mas "
          f"afectado cambia de tramo en el {peor:.0f} % de los videos. Alcanza "
          "con declarar el cambio de instrumento como limitacion.\n")
    elif peor < 30:
        A(f"\n> **Veredicto: zona gris.** El peor descriptor cambia de tramo en el "
          f"{peor:.0f} % de los videos. Opciones: usar la escala igual declarando "
          "el sesgo por descriptor, o dejar fuera del panel los mas afectados.\n")
    else:
        A(f"\n> **Veredicto: la escala NO se puede reutilizar tal cual.** El peor "
          f"descriptor cambia de tramo en el {peor:.0f} % de los videos. Hay que "
          "recalibrar con transcripciones de Supadata (rehacer el corpus con esa "
          "fuente) o volver al plan del panel sobre videos ya enriquecidos.\n")

    A("\n## Puntuacion: la huella del instrumento\n")
    A(f"- Palabras por signo con YouTube: **{meta['sig_yt']:.0f}**")
    A(f"- Palabras por signo con Supadata: **{meta['sig_sd']:.1f}**\n")
    A("Si el segundo numero es mucho menor, Supadata esta insertando puntuacion "
      "que el hablante no dijo. No afecta a los 8 del panel (ninguno depende de "
      "puntuacion) pero confirma que es post-procesado, e invalida cualquier "
      "indicador futuro basado en frases.\n")
    return "\n".join(L)


# ------------------------------------------------------------------ MAIN

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n", type=int, default=20, help="videos a calibrar (default 20)")
    p.add_argument("--cache", action="store_true",
                   help="reusa las transcripciones ya pedidas (0 creditos)")
    p.add_argument("--seed", type=int, default=20260812)
    p.add_argument("--pausa", type=float, default=1.0,
                   help="segundos entre llamadas a Supadata")
    args = p.parse_args()

    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    env = HERE.parent / ".env"
    try:
        from dotenv import load_dotenv
        if env.exists():
            load_dotenv(env)
    except ImportError:
        pass

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("Falta DATABASE_URL en backend/.env", file=sys.stderr)
        return 2

    print("=" * 66)
    print(f"CALIBRACION YouTube vs Supadata   v{VERSION}")
    print("=" * 66)

    escala_path = DOCS / "escala_referencia.json"
    if not escala_path.exists():
        print("Falta docs/escala_referencia.json. Corre build_reference_scale.py primero.",
              file=sys.stderr)
        return 2
    escala = json.loads(escala_path.read_text(encoding="utf-8"))

    muestra = elegir_videos(dsn, args.n, args.seed)
    if muestra.empty:
        print("No hay videos aptos para calibrar.", file=sys.stderr)
        return 1
    print(f"{len(muestra)} videos elegidos, repartidos por macroformato")

    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    api_key = os.getenv("SUPADATA_API_KEY")
    if not args.cache and not api_key:
        print("Falta SUPADATA_API_KEY en backend/.env. En Render esta configurada, "
              "pero este script corre local: copiala ahi.", file=sys.stderr)
        return 2

    pares, fallos = [], []
    for i, (_, fila) in enumerate(muestra.iterrows(), 1):
        vid = fila["external_id"]
        if vid in cache:
            sd = cache[vid]
            origen = "cache"
        elif args.cache:
            fallos.append((vid, "no esta en cache y se pidio --cache"))
            continue
        else:
            sd = pedir_supadata(vid, api_key)
            cache[vid] = sd
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            origen = "api"
            time.sleep(args.pausa)

        if not sd.get("texto"):
            print(f"  [{i}/{len(muestra)}] {vid} — sin texto ({sd.get('estado')})")
            fallos.append((vid, sd.get("estado")))
            if sd.get("cortar"):
                # Cuota agotada o Whisper arrancado: seguir es tirar plata o
                # pegarle a una puerta cerrada. Se corta y se analiza lo que hay.
                print("\n  >> CORTE: " + str(sd.get("estado")))
                print("  >> Se analiza con los pares conseguidos hasta aca.")
                break
            continue

        base = fila.to_dict()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dy = descriptores_de(base, base.get("transcript") or "")
            ds = descriptores_de(base, sd["texto"])
        pares.append({
            "external_id": vid, "titulo": (base.get("title") or "")[:60],
            "formato": base.get("stratum_format"),
            "yt": dy, "sd": ds,
            "palabras_yt": len((base.get("transcript") or "").split()),
            "palabras_sd": len(sd["texto"].split()),
        })
        print(f"  [{i}/{len(muestra)}] {vid} ({origen}) "
              f"yt={pares[-1]['palabras_yt']}w  sd={pares[-1]['palabras_sd']}w")

    if len(pares) < 3:
        print(f"\nSolo {len(pares)} pares utiles. Insuficiente para concluir.",
              file=sys.stderr)
        for v, e in fallos:
            print(f"  {v}: {e}", file=sys.stderr)
        return 1

    D, R = comparar(pares, escala)

    py = np.median([p["palabras_yt"] for p in pares])
    ps = np.median([p["palabras_sd"] for p in pares])
    sig = lambda t: (len(t.split()) / max(1, sum(t.count(c) for c in ".?!")))
    meta = {
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n": len(pares), "pal_yt": py, "pal_sd": ps,
        "dif_pal": 100 * (ps - py) / max(py, 1),
        "pierden_aptitud": int(sum(1 for p in pares
                                   if p["yt"]["v_apto_panel"] == 1
                                   and p["sd"]["v_apto_panel"] == 0)),
        "sig_yt": np.median([sig(muestra.set_index("external_id")
                                 .loc[p["external_id"], "transcript"] or "")
                             for p in pares]),
        "sig_sd": np.median([sig(cache[p["external_id"]]["texto"]) for p in pares]),
    }

    DOCS.mkdir(parents=True, exist_ok=True)
    D.to_csv(DOCS / "calibracion_supadata.csv", index=False)
    R.to_csv(DOCS / "calibracion_supadata_resumen.csv", index=False)
    (DOCS / "calibracion_supadata.md").write_text(informe(D, R, meta), encoding="utf-8")

    print("\n" + R.to_string(index=False))
    peor = R["pct_cambian_de_tramo"].max()
    print(f"\nPeor descriptor: {peor:.0f} % de los videos cambian de tramo.")
    print(f"Palabras: YouTube {py:.0f} vs Supadata {ps:.0f} "
          f"({meta['dif_pal']:+.1f} %)")
    if fallos:
        print(f"\n{len(fallos)} videos sin texto de Supadata:")
        for v, e in fallos[:8]:
            print(f"  {v}: {e}")
    print(f"\nInforme -> {DOCS / 'calibracion_supadata.md'}")
    print("NOTA: no se toco content_items. Las transcripciones de Supadata "
          f"quedaron en {CACHE.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

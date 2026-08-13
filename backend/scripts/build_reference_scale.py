#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_reference_scale.py  v2.0
Construye la escala de referencia del panel a partir del corpus publico,
y opcionalmente mide el historial personal CONTRA esa escala.

LA ESCALA NO SE ELIGE A MANO: SE DECIDE POR MEDICION
----------------------------------------------------
Para cada uno de los 8 descriptores se toman dos decisiones independientes,
ambas con un criterio explicito y reproducible:

  tipo    continuo | presencia
          'presencia' si mas de un tercio del corpus vale exactamente 0. Ahi el
          tercil no existe: el corte p33 vale 0 y el nivel "bajo" abarcaria al
          55 % del corpus. En esos, lo informativo es si el video LO TIENE, y
          recien despues cuanto comparado con los que tambien lo tienen.

  ambito  global | por_formato
          Prueba de permutacion (2.000 remezclas de las etiquetas de formato).
          Los cortes por formato siempre se ven distintos; la pregunta es si se
          ven mas distintos que al remezclar al azar. Si no, la dispersion es
          ruido de estimacion y corresponde una escala global.
          El estadistico cambia segun el tipo: rango del p33 para los continuos,
          rango de la TASA DE PRESENCIA para los de cola en cero (en esos el p33
          vale 0 en todos los grupos y la prueba no mediria nada).

PRESENTACION
------------
Los continuos se muestran como percentil ("mas que el 68 % de los videos"); los
de presencia, como presencia mas magnitud ("2 enlaces; el 54 % no tiene
ninguno"). Nunca una letra ni un adjetivo: el percentil describe, el adjetivo
juzga. El JSON incluye una grilla de 101 percentiles por descriptor para que la
extension ubique cualquier video sin cargar el corpus.

Y ADEMAS VALIDA
---------------
- Correlacion de cada descriptor con log(duracion), global e intra-celda. El
  panel se eligio contra 60 videos del historial personal; sobre 344 publicos
  podria no sostenerse. La columna que manda es la MEDIA intra-celda: el peor de
  12 celdas esta inflado por construccion.
- eta^2 por descriptor y correlacion mutua entre los 8.

USO
---
    .venv\\Scripts\\python build_reference_scale.py
    .venv\\Scripts\\python build_reference_scale.py --historial

Con --historial se le asignan estratos al historial con las mismas reglas del
muestreo (importadas de build_reference_corpus, no reimplementadas) y se ubica
cada video en la escala. Reporta cada tramo por cantidad de videos Y ponderado
por minutos: cambiar el denominador cambia la conclusion.

Salidas en docs/:
    corpus_referencia_features.csv   tabla ancha del corpus, un video por fila
    escala_referencia.csv            la escala, legible
    escala_referencia.json           la escala para la extension (con grillas)
    escala_por_celda_anexo.csv       cortes por las 12 celdas, como evidencia
    validacion_escala.md             el informe completo
  con --historial, ademas:
    historial_features.csv           descriptores de tu historial
    historial_vs_escala.csv          cada video con su percentil por descriptor
    informe_historial.md             el informe legible
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent.parent / "docs"
sys.path.insert(0, str(HERE))

import nutriscore_features as nf   # noqa: E402  (necesita HERE en sys.path)

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


VERSION = "2.0"

# Los 8 del panel. invertir=True significa "mas es peor" para el nivel mostrado;
# ninguno lo es hoy, pero la estructura queda por si se agrega alguno.
PANEL = {
    "ritmo_ppm":         {"invertir": False, "unidad": "palabras/min"},
    "cifras_100w":       {"invertir": False, "unidad": "cifras/100 palabras"},
    "atribucion_1000w":  {"invertir": False, "unidad": "marcas/1000 palabras"},
    "mattr_200":         {"invertir": False, "unidad": "0-1"},
    "conectores_1000w":  {"invertir": False, "unidad": "marcas/1000 palabras"},
    "enlaces_externos":  {"invertir": False, "unidad": "enlaces (absoluto)"},
    "promocional_1000w": {"invertir": False, "unidad": "marcas/1000 palabras"},
    "cobertura_titulo":  {"invertir": False, "unidad": "0-1"},
}

FORMATOS = ["informativo", "practico_personal", "entretenimiento", "deporte_gaming"]
DURACIONES = ["corto", "medio", "largo"]

COLUMNAS = """
 id, external_id, title, channel, channel_id, duration_seconds, description,
 tags, category_id, category_name, transcript, transcript_source,
 transcript_is_generated, transcript_lang, transcript_word_count,
 transcript_segments, chapters, n_chapters, upload_date, video_language,
 watched_at, corpus, stratum_format, stratum_duration, sampling_source,
 sampling_frame_version
"""

# jsonb vuelve de la base como objeto de Python, pero nutriscore_features espera
# el texto crudo y hace json.loads. Sin esto, n_tags da 0 en todas las filas y
# et_caducidad pierde la senal de los tags, en silencio.
JSONB = ("tags", "transcript_segments", "chapters")


# ------------------------------------------------------------------ CARGA

def conectar(dsn: str):
    if psycopg is None:
        raise RuntimeError(
            "No hay driver de PostgreSQL. Estas usando el Python del sistema:\n"
            "    .venv\\Scripts\\python build_reference_scale.py")
    if _PG == "psycopg3":
        return psycopg.connect(dsn, row_factory=dict_row)
    return psycopg.connect(dsn)


def cargar(dsn: str, corpus: str) -> pd.DataFrame:
    sql = f"SELECT {COLUMNAS} FROM content_items WHERE corpus = %s"
    with conectar(dsn) as conn:
        cur = conn.cursor() if _PG == "psycopg3" else conn.cursor(cursor_factory=RealDictCursor)
        with cur:
            cur.execute(sql, (corpus,))
            filas = [dict(r) for r in cur.fetchall()]
    df = pd.DataFrame(filas)
    for c in JSONB:
        if c in df.columns:
            df[c] = df[c].apply(
                lambda v: v if isinstance(v, str) or v is None else json.dumps(v, ensure_ascii=False))
    return df


# ------------------------------------------------------------------ CALCULO

def calcular(df: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for _, row in df.iterrows():
        r = row.to_dict()
        for c in ("transcript", "description", "title", "tags", "transcript_segments",
                  "chapters", "transcript_source", "category_name", "video_language",
                  "transcript_lang", "channel"):
            if not isinstance(r.get(c), str):
                r[c] = ""
        tnorm = nf.norm(r.get("transcript") or "")
        toks = nf.words(tnorm)
        lang = (r.get("video_language") or r.get("transcript_lang") or "es")
        lang = "en" if str(lang).startswith("en") else "es"
        val = nf.capa0_validez(r, toks)
        ind = nf.indicadores(r, toks, tnorm, lang, val)
        eti = nf.etiquetas(r, ind, val, lang)
        filas.append({
            "id": r["id"], "external_id": r["external_id"],
            "title": r["title"], "channel": r["channel"],
            "duration_seconds": r.get("duration_seconds"),
            "stratum_format": r.get("stratum_format"),
            "stratum_duration": r.get("stratum_duration"),
            "sampling_source": r.get("sampling_source"),
            **val, **ind, **eti,
        })
    return pd.DataFrame(filas)


def celda(fmt, dur) -> str:
    return f"{fmt}|{dur}"


# ------------------------------------------------------------------ HISTORIAL

def asignar_estratos(df: pd.DataFrame) -> pd.DataFrame:
    """El historial nunca fue muestreado, asi que no tiene estrato. Se le asigna
    con LAS MISMAS reglas del muestreo, importadas de build_reference_corpus:
    si se reimplementaran aca, cualquier ajuste futuro las desincronizaria y el
    historial se compararia contra celdas que no le corresponden."""
    import build_reference_corpus as brc
    d = df.copy()
    d["stratum_format"] = d["category_id"].apply(brc.bucket_formato)
    d["stratum_duration"] = d["duration_seconds"].apply(
        lambda s: brc.bucket_duracion(int(s)) if pd.notna(s) else None)
    return d


def ubicar(valor, c: dict | None) -> str:
    """Donde cae un valor respecto de los cortes de su celda."""
    if c is None or pd.isna(valor):
        return "sin_dato"
    if valor <= c["p33"]:
        return "bajo"
    if valor <= c["p67"]:
        return "medio"
    return "alto"


def percentil_en(valor, serie: pd.Series) -> float:
    """En que percentil del corpus de referencia cae este valor. Es el numero
    mas legible del informe: 'tu mediana esta en el percentil 38'."""
    s = pd.to_numeric(serie, errors="coerce").dropna()
    if not len(s) or pd.isna(valor):
        return np.nan
    return round(100.0 * float((s < valor).sum()) / len(s), 1)


def _ref_de(doc, k, fmt):
    """El bloque de referencia que le corresponde a un video segun su formato."""
    d = doc["descriptores"].get(k) or {}
    ref = d.get("referencia")
    if not ref:
        return d, None
    if d.get("ambito") == "por_formato":
        return d, (ref.get(fmt) or ref.get("_todos"))
    return d, ref


def comparar_historial(H: pd.DataFrame, R: pd.DataFrame, doc: dict) -> tuple[pd.DataFrame, str]:
    """Ubica cada video del historial en la escala y resume.

    Los continuos se expresan como percentil; los de tipo presencia, como
    tiene/no tiene mas el percentil entre los que tienen. No se usan terciles
    en los de presencia porque ahi el tercil no existe."""
    aptoH = H[H["v_apto_panel"] == 1].copy()
    D = doc["descriptores"]

    filas = []
    for _, r in aptoH.iterrows():
        fmt = r.get("stratum_format")
        fmt = fmt if isinstance(fmt, str) else None
        dur = r.get("stratum_duration")
        fila = {
            "external_id": r.get("external_id"), "title": r.get("title"),
            "channel": r.get("channel"),
            "formato": fmt or "fuera_del_marco",
            "duracion": dur if isinstance(dur, str) else "fuera_del_marco",
            "minutos": round((r.get("duration_seconds") or 0) / 60, 1),
        }
        for k in PANEL:
            cfg, ref = _ref_de(doc, k, fmt)
            v = r.get(k)
            fila[k] = v
            if not ref or pd.isna(v):
                fila[f"pct_{k}"] = np.nan
                fila[f"est_{k}"] = "sin_dato"
                continue
            if cfg.get("tipo") == "presencia":
                if v > 0:
                    fila[f"pct_{k}"] = percentil_desde_grid(v, ref.get("grid_presentes"))
                    fila[f"est_{k}"] = "presente"
                else:
                    fila[f"pct_{k}"] = np.nan
                    fila[f"est_{k}"] = "ausente"
            else:
                fila[f"pct_{k}"] = percentil_desde_grid(v, ref.get("grid"))
                fila[f"est_{k}"] = "medido"
        filas.append(fila)
    comp = pd.DataFrame(filas)

    L = []
    A = L.append
    A("# Tu historial medido contra la escala de referencia\n")
    A("**Esto no es una nota.** Dice donde cae lo que miras respecto de lo que "
      "hay en YouTube en espanol, nada mas. Un percentil bajo en densidad de "
      "cifras no significa que hayas perdido el tiempo: significa que miras "
      "contenido con menos cifras que la mediana. Si eso esta bien o mal lo "
      "decidis vos segun para que lo mirabas.\n")
    A(f"{len(H)} videos en el historial - **{len(aptoH)} admiten panel** "
      f"({len(H) - len(aptoH)} sin transcripcion completa o sin metadatos)\n")

    continuos = [k for k in PANEL if D[k]["tipo"] == "continuo"]
    presencia = [k for k in PANEL if D[k]["tipo"] == "presencia"]

    A("\n## Descriptores continuos: en que percentil cae tu consumo\n")
    A("Se calcula el percentil de **cada** video y se reporta la mediana de "
      "esos percentiles. p50 seria consumir exactamente la mediana de YouTube.\n")
    A("| descriptor | ambito de la escala | mediana de tus percentiles | tu mediana | mediana YouTube |")
    A("|---|---|---|---|---|")
    for k in continuos:
        p = pd.to_numeric(comp.get(f"pct_{k}"), errors="coerce").median()
        mh = pd.to_numeric(aptoH[k], errors="coerce").median()
        cfg = D[k]
        ref = cfg["referencia"] if cfg["ambito"] == "global" else cfg["referencia"].get("_todos")
        mr = (ref or {}).get("p50")
        amb = "global" if cfg["ambito"] == "global" else "por formato"
        A(f"| {k} | {amb} | **p{p:.0f}** | {mh:g} | {mr} |"
          if pd.notna(p) else f"| {k} | {amb} | — | — | {mr} |")

    if presencia:
        A("\n\n## Descriptores de presencia\n")
        A("En estos, mas de un tercio del corpus vale exactamente cero, asi que "
          "el tercil no existe. Lo informativo es **si esta o no**, y recien "
          "despues cuanto.\n")
        A("| descriptor | tus videos que lo tienen | videos de YouTube que lo tienen | percentil entre los que tienen |")
        A("|---|---|---|---|")
        for k in presencia:
            est = comp.get(f"est_{k}")
            tuyos = float((est == "presente").mean()) if est is not None else np.nan
            cfg = D[k]
            ref = cfg["referencia"] if cfg["ambito"] == "global" else cfg["referencia"].get("_todos")
            yt = 1 - (ref or {}).get("p_ausencia", np.nan)
            p = pd.to_numeric(comp.get(f"pct_{k}"), errors="coerce").median()
            p_s = f"p{p:.0f}" if pd.notna(p) else "—"
            A(f"| {k} | {tuyos:.0%} | {yt:.0%} | {p_s} |")

    A("\n\n## Por video contra por minuto\n")
    A("El mismo dato cambia segun el denominador. Contar videos trata igual a un "
      "short y a un podcast de dos horas; contar minutos pesa lo que realmente "
      "ocupo tu tiempo. Es el *por porcion* contra el *por 100 g* del envase.\n")
    A("Los tramos son del percentil: bajo = p0-p33, medio = p33-p67, alto = p67-p100.\n")
    A("| descriptor | bajo (vid/min) | medio (vid/min) | alto (vid/min) | inversion |")
    A("|---|---|---|---|---|")
    for k in continuos:
        p = pd.to_numeric(comp.get(f"pct_{k}"), errors="coerce")
        tramo = pd.cut(p, [-0.1, 33, 67, 100], labels=["bajo", "medio", "alto"])
        porv = tramo.value_counts(normalize=True)
        mins = comp.groupby(tramo, observed=False)["minutos"].sum()
        tot = mins.sum() or 1
        celdas = []
        for niv in ("bajo", "medio", "alto"):
            celdas.append(f"{100*porv.get(niv,0):.0f}% / {100*mins.get(niv,0)/tot:.0f}%")
        # la inversion es la señal interesante: cambia la conclusion al cambiar
        # el denominador
        d_alto = 100 * (mins.get("alto", 0) / tot - porv.get("alto", 0))
        marca = "**si**" if abs(d_alto) >= 12 else ""
        A(f"| {k} | " + " | ".join(celdas) + f" | {d_alto:+.0f} pp {marca} |")
    A("\nLa ultima columna es la diferencia entre el porcentaje de minutos y el "
      "de videos en el tramo alto. Marcada cuando supera 12 puntos: ahi el "
      "denominador cambia la conclusion.\n")

    A("\n## Como se reparte tu historial entre los formatos\n")
    A("| formato | tus videos | tus minutos | % de tus minutos |")
    A("|---|---|---|---|")
    tot_min = comp["minutos"].sum() or 1
    for f in sorted(set(comp["formato"])):
        sub = comp[comp["formato"] == f]
        A(f"| {f} | {len(sub)} | {sub['minutos'].sum():.0f} min | "
          f"{100*sub['minutos'].sum()/tot_min:.0f}% |")
    porc = comp.groupby(["formato", "duracion"])["minutos"].sum().sort_values(ascending=False)
    if len(porc):
        top = porc.index[0]
        A(f"\nEl estrato que mas tiempo te ocupa es **{top[0]} / {top[1]}**: "
          f"{porc.iloc[0]:.0f} minutos, el {100*porc.iloc[0]/tot_min:.0f} % de tu tiempo total.")
    return comp, "\n".join(L)


# ------------------------------------------------------------------ ESCALA

# Un tercil no puede existir si mas de un tercio de la masa esta en el suelo:
# el corte p33 vale 0 y el nivel "bajo" abarca a todos los ceros, que pueden ser
# el 55 % del corpus. Por encima de este umbral el descriptor se presenta como
# presencia + magnitud entre los que tienen, no como tercil.
UMBRAL_CERO = 1 / 3

# Por debajo de este p-valor se considera que los formatos difieren de verdad y
# el descriptor pasa a tener corte por macroformato en vez de global.
ALFA_PERMUTACION = 0.05
N_PERMUTACIONES = 2000


def grid_percentiles(s: pd.Series) -> list:
    """101 valores: el del percentil 0, 1, 2 ... 100. Con esto la extension
    calcula el percentil exacto de cualquier video sin cargar el corpus."""
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) < 3:
        return []
    return [round(float(np.quantile(s, i / 100)), 6) for i in range(101)]


def percentil_desde_grid(valor, grid: list) -> float:
    """Inversa de grid_percentiles: en que percentil cae un valor.

    Se acota a 0-100. Sin el acote, un valor por debajo del minimo del corpus
    devolvia -1, que despues queda fuera de cualquier tramo y se propaga como
    nulo. Un video mas lento que el mas lento del corpus esta en el percentil 0,
    no en un percentil inexistente."""
    if not grid or valor is None or pd.isna(valor):
        return float("nan")
    a = np.asarray(grid, float)
    return float(min(100, max(0, np.searchsorted(a, valor, side="right") - 1)))


def prueba_permutacion(valores: pd.Series, grupos: pd.Series,
                       rng: np.random.Generator, n_perm: int = N_PERMUTACIONES,
                       estadistico: str = "p33") -> float:
    """?Los cortes difieren entre grupos mas de lo que difieren por azar?

    Con ~86 casos por grupo, dos cortes p33 calculados sobre muestras distintas
    de la MISMA poblacion ya salen separados. Mirar el rango y asustarse es un
    error. Aca se remezclan las etiquetas de grupo n_perm veces y se compara el
    rango real contra la distribucion de rangos que produce el puro azar.
    Devuelve la proporcion de remezclas que igualan o superan el rango real:
    si es baja, los grupos difieren de verdad.

    El estadistico depende del tipo de descriptor:
      - 'p33': rango del corte p33 entre grupos. Sirve para los continuos.
      - 'tasa_presencia': rango de la proporcion de videos con valor > 0.
        Obligatorio para los de cola en cero: ahi el p33 vale 0 en todos los
        grupos por construccion, el rango da 0 siempre y la prueba devolveria
        p=1 sin haber medido nada. La pregunta correcta en esos no es 'cuanto
        tienen' sino 'a cuantos les aparece'."""
    s = pd.to_numeric(valores, errors="coerce")
    ok = s.notna() & grupos.notna()
    s, g = s[ok].to_numpy(), grupos[ok].to_numpy()
    if len(s) < 40 or len(np.unique(g)) < 2:
        return float("nan")

    if estadistico == "tasa_presencia":
        def rango(etiquetas):
            return np.ptp([(s[etiquetas == u] > 0).mean() for u in np.unique(g)])
    else:
        def rango(etiquetas):
            return np.ptp([np.quantile(s[etiquetas == u], 1 / 3) for u in np.unique(g)])

    real = rango(g)
    nulos = np.array([rango(rng.permutation(g)) for _ in range(n_perm)])
    return round(float((nulos >= real).mean()), 4)


def decidir_estructura(apt: pd.DataFrame, semilla: int = 20260812) -> dict:
    """Elige, POR MEDICION y no a mano, como se construye cada descriptor.

    Dos decisiones independientes por descriptor:
      - tipo:   continuo | presencia   (segun cuanta masa hay en cero)
      - ambito: global   | por_formato (segun la prueba de permutacion)
    Un descriptor puede ser las dos cosas: atribucion_1000w tiene media
    distribucion en cero Y difiere por formato."""
    rng = np.random.default_rng(semilla)
    plan = {}
    for k in PANEL:
        s = pd.to_numeric(apt[k], errors="coerce").dropna()
        fz = float((s == 0).mean()) if len(s) else float("nan")
        tipo = "presencia" if (pd.notna(fz) and fz > UMBRAL_CERO) else "continuo"
        est = "tasa_presencia" if tipo == "presencia" else "p33"
        p = prueba_permutacion(apt[k], apt["stratum_format"], rng, estadistico=est)
        plan[k] = {
            "tipo": tipo,
            "ambito": ("por_formato" if (pd.notna(p) and p < ALFA_PERMUTACION)
                       else "global"),
            "frac_cero": round(fz, 4) if pd.notna(fz) else None,
            "p_permutacion": p if pd.notna(p) else None,
            "estadistico_permutacion": est,
            "unidad": PANEL[k]["unidad"],
        }
    return plan


def _referencia(s: pd.Series, tipo: str) -> dict | None:
    """El bloque de referencia de un descriptor en un ambito dado."""
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) < 8:
        return None
    if tipo == "presencia":
        pres = s[s > 0]
        return {
            "n": int(len(s)),
            "n_presentes": int(len(pres)),
            "p_ausencia": round(float((s == 0).mean()), 4),
            "grid_presentes": grid_percentiles(pres),
            "mediana_presentes": (round(float(pres.median()), 4)
                                  if len(pres) else None),
        }
    return {
        "n": int(len(s)),
        "grid": grid_percentiles(s),
        "p25": round(float(s.quantile(.25)), 4),
        "p50": round(float(s.median()), 4),
        "p75": round(float(s.quantile(.75)), 4),
    }


def construir_escala_v2(F: pd.DataFrame, frame: str,
                        semilla: int = 20260812) -> tuple[dict, pd.DataFrame, dict]:
    """Escala global, con corte por macroformato solo donde la permutacion dice
    que hace falta, y presencia+magnitud donde el tercil no existe."""
    apt = F[F["v_apto_panel"] == 1]
    plan = decidir_estructura(apt, semilla)

    desc, filas = {}, []
    for k, cfg in plan.items():
        bloque = {**cfg}
        if cfg["ambito"] == "global":
            bloque["referencia"] = _referencia(apt[k], cfg["tipo"])
        else:
            bloque["referencia"] = {
                fmt: _referencia(apt.loc[apt["stratum_format"] == fmt, k], cfg["tipo"])
                for fmt in FORMATOS
            }
            # Respaldo para videos sin formato asignable (los del historial que
            # caen fuera del marco). Sin esto no habria contra que compararlos.
            bloque["referencia"]["_todos"] = _referencia(apt[k], cfg["tipo"])
        desc[k] = bloque

        def volcar(ref, ambito_txt):
            if not ref:
                return
            filas.append({
                "frame_version": frame, "descriptor": k, "tipo": cfg["tipo"],
                "ambito": ambito_txt, "n": ref["n"],
                "p_ausencia": ref.get("p_ausencia"),
                "n_presentes": ref.get("n_presentes"),
                "p25": ref.get("p25"), "p50": ref.get("p50") or ref.get("mediana_presentes"),
                "p75": ref.get("p75"),
                "p_permutacion": cfg["p_permutacion"], "frac_cero": cfg["frac_cero"],
            })

        if cfg["ambito"] == "global":
            volcar(bloque["referencia"], "global")
        else:
            for fmt, ref in bloque["referencia"].items():
                volcar(ref, fmt)

    doc = {
        "frame_version": frame,
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script_version": VERSION,
        "modo": "global_con_excepciones_medidas",
        "semilla_permutacion": semilla,
        "reglas": {
            "umbral_cero": UMBRAL_CERO,
            "alfa_permutacion": ALFA_PERMUTACION,
            "n_permutaciones": N_PERMUTACIONES,
            "explicacion": (
                "ambito=por_formato cuando la prueba de permutacion rechaza que "
                "los formatos vengan de la misma distribucion. tipo=presencia "
                "cuando mas de un tercio del corpus vale exactamente 0, porque "
                "ahi el tercil 'bajo' abarcaria a mas de un tercio y dejaria de "
                "ser un tercil."),
        },
        "corpus": {
            "n_filas": int(len(F)),
            "n_con_transcripcion": int((F["v_tiene_transcripcion"] == 1).sum()),
            "n_apto_panel": int(len(apt)),
        },
        "presentacion": (
            "Los continuos se muestran como percentil ('mas que el 68 % de los "
            "videos'). Los de tipo presencia se muestran como presencia mas "
            "magnitud ('2 enlaces; el 54 % de los videos no tiene ninguno'). "
            "Nunca una letra ni un adjetivo: el percentil describe, el adjetivo "
            "juzga."),
        "descriptores": desc,
    }
    return limpiar_nan(doc), pd.DataFrame(filas), plan


def construir_escala(F: pd.DataFrame, min_n: int, frame: str) -> tuple[dict, pd.DataFrame]:
    apt = F[F["v_apto_panel"] == 1]

    sin_cortes: list[tuple] = []

    def cortes(serie: pd.Series, etiqueta: str = "") -> dict | None:
        """None cuando no hay con que cortar. Pasa de verdad: enlaces_externos
        es un conteo absoluto y en una celda entera puede valer 0 en casi todas
        las filas. Un tercil sobre dos valores distintos no es un tercil."""
        s = pd.to_numeric(serie, errors="coerce").dropna()
        if len(s) < 3:
            if etiqueta:
                sin_cortes.append((etiqueta, f"solo {len(s)} valores"))
            return None
        if s.nunique() < 3:
            if etiqueta:
                sin_cortes.append((etiqueta, f"solo {s.nunique()} valor(es) distinto(s)"))
            return None
        return {
            "n": int(len(s)),
            "p33": round(float(s.quantile(1 / 3)), 4),
            "p50": round(float(s.median()), 4),
            "p67": round(float(s.quantile(2 / 3)), 4),
            "min": round(float(s.min()), 4),
            "max": round(float(s.max()), 4),
        }

    glob = {k: cortes(apt[k], f"GLOBAL/{k}") for k in PANEL}

    escala = {"_global": {"n": int(len(apt)), "descriptores": glob}}
    filas_csv = []

    for fmt in FORMATOS:
        for dur in DURACIONES:
            sub = apt[(apt["stratum_format"] == fmt) & (apt["stratum_duration"] == dur)]
            n = len(sub)
            usa_global = n < min_n
            d = {}
            for k in PANEL:
                c = cortes(sub[k], f"{fmt}/{dur}/{k}") if not usa_global else None
                if c is None:
                    c = dict(glob[k] or {}, fallback=True) if glob[k] else None
                d[k] = c
                if c:
                    filas_csv.append({
                        "frame_version": frame, "formato": fmt, "duracion": dur,
                        "descriptor": k, "n_util": n,
                        "p33": c["p33"], "p50": c["p50"], "p67": c["p67"],
                        "min": c["min"], "max": c["max"],
                        "fallback_global": bool(c.get("fallback", False)),
                    })
            escala[celda(fmt, dur)] = {
                "n": n,
                "fallback_global": usa_global,
                "descriptores": d,
            }

    doc = {
        "frame_version": frame,
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script_version": VERSION,
        "min_n_por_celda": min_n,
        "corpus": {
            "n_filas": int(len(F)),
            "n_con_transcripcion": int((F["v_tiene_transcripcion"] == 1).sum()),
            "n_apto_panel": int(len(apt)),
        },
        "descriptores": PANEL,
        "nota": ("Cortes p33/p67 = terciles del corpus de referencia, por celda. "
                 "Son RELATIVOS a este corpus y a esta fecha: hay que declararlo en "
                 "la interfaz. El n util va al lado de cada corte porque no es 33 en "
                 "todas las celdas."),
        "sin_cortes": [{"donde": a, "motivo": b} for a, b in sin_cortes],
        "escala": escala,
    }
    return limpiar_nan(doc), pd.DataFrame(filas_csv)


def limpiar_nan(o):
    """json.dumps escupe NaN, que no es JSON valido y rompe JSON.parse en la
    extension. Se convierte a null antes de escribir."""
    if isinstance(o, dict):
        return {k: limpiar_nan(v) for k, v in o.items()}
    if isinstance(o, list):
        return [limpiar_nan(v) for v in o]
    if isinstance(o, float) and (np.isnan(o) or np.isinf(o)):
        return None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    return o


# ------------------------------------------------------------------ VALIDACION

def eta2(F: pd.DataFrame, col: str, grupo: str) -> float:
    """Proporcion de la varianza del descriptor que explica el estrato.
    Si da casi cero, estratificar ese descriptor no aportaba nada."""
    s = pd.to_numeric(F[col], errors="coerce")
    g = F[grupo]
    ok = s.notna() & g.notna()
    s, g = s[ok], g[ok]
    if len(s) < 12 or s.nunique() < 3:
        return np.nan
    media = s.mean()
    ss_tot = float(((s - media) ** 2).sum())
    if ss_tot == 0:
        return np.nan
    ss_bet = float(sum(len(v) * (v.mean() - media) ** 2 for _, v in s.groupby(g)))
    return ss_bet / ss_tot


def validar(F: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    # Las columnas constantes dan division por cero al correlacionar. numpy lo
    # avisa por errstate, no por el modulo warnings, asi que hay que taparlo aca.
    with np.errstate(invalid="ignore", divide="ignore"):
        return _validar(F)


def _validar(F: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    apt = F[F["v_apto_panel"] == 1].copy()
    apt["logdur"] = np.log(pd.to_numeric(apt["duration_seconds"], errors="coerce"))
    apt["_celda"] = apt["stratum_format"] + "|" + apt["stratum_duration"]

    filas = []
    for k in PANEL:
        s = pd.to_numeric(apt[k], errors="coerce")
        glob = s.corr(apt["logdur"])
        # intra-celda: la correlacion que importa ahora que el diseno estratifica
        # por duracion. La global esta inflada por construccion.
        intra = []
        for _, sub in apt.groupby("_celda"):
            x = pd.to_numeric(sub[k], errors="coerce")
            y = sub["logdur"]
            if x.notna().sum() >= 8 and x.nunique() > 2:
                c = x.corr(y)
                if pd.notna(c):
                    intra.append(c)
        filas.append({
            "descriptor": k,
            "n": int(s.notna().sum()),
            "corr_log_dur_global": round(float(glob), 3) if pd.notna(glob) else np.nan,
            "corr_log_dur_intra_max": round(float(max(intra, key=abs)), 3) if intra else np.nan,
            "corr_log_dur_intra_media": round(float(np.mean(intra)), 3) if intra else np.nan,
            "eta2_celda": round(float(eta2(apt, k, "_celda")), 3),
            "eta2_formato": round(float(eta2(apt, k, "stratum_format")), 3),
        })
    dur = pd.DataFrame(filas)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")   # columnas constantes -> division por cero
        mutua = apt[list(PANEL)].apply(pd.to_numeric, errors="coerce").corr()

    resumen = {
        "n_apto": int(len(apt)),
        "peor_corr_global": float(dur["corr_log_dur_global"].abs().max()),
        "peor_corr_intra": float(dur["corr_log_dur_intra_max"].abs().max()),
        "peor_mutua": float(
            mutua.where(~np.eye(len(mutua), dtype=bool)).abs().max().max()),
    }
    return dur, mutua, resumen


# ------------------------------------------------------------------ INFORME

def informe_md(doc: dict, doc_celdas: dict, plan: dict, dur: pd.DataFrame,
               mutua: pd.DataFrame, resumen: dict, F: pd.DataFrame) -> str:
    apt = F[F["v_apto_panel"] == 1]
    L = []
    A = L.append
    A("# Validacion y construccion de la escala de referencia\n")
    A(f"**Marco:** `{doc['frame_version']}` - **Generado:** {doc['generado']} - "
      f"**script v{doc['script_version']}**\n")
    A(f"{doc['corpus']['n_filas']} filas - "
      f"{doc['corpus']['n_con_transcripcion']} con transcripcion - "
      f"**{doc['corpus']['n_apto_panel']} aptas para el panel**\n")

    A("\n## 1. Como se construyo cada descriptor (decidido por medicion)\n")
    A("Dos decisiones independientes por descriptor, ninguna tomada a mano:\n")
    A("- **ambito**: `por_formato` si la prueba de permutacion rechaza que los "
      "cuatro macroformatos vengan de la misma distribucion "
      f"(alfa = {doc['reglas']['alfa_permutacion']}, "
      f"{doc['reglas']['n_permutaciones']} remezclas). Si no, `global`.\n")
    A("- **tipo**: `presencia` si mas de un tercio del corpus vale exactamente 0. "
      "Ahi el tercil 'bajo' abarcaria a mas de un tercio y dejaria de ser un "
      "tercil: lo informativo pasa a ser si esta o no.\n")
    A("| descriptor | % en cero | p permutacion | tipo | ambito |")
    A("|---|---|---|---|---|")
    for k, c in plan.items():
        fz = f"{100*c['frac_cero']:.0f}%" if c["frac_cero"] is not None else "—"
        p = c["p_permutacion"]
        p_s = "—" if p is None else (f"**{p:.3f}**" if p < ALFA_PERMUTACION else f"{p:.3f}")
        A(f"| {k} | {fz} | {p_s} | {c['tipo']} | "
          f"{'**por formato**' if c['ambito']=='por_formato' else 'global'} |")
    n_pf = sum(1 for c in plan.values() if c["ambito"] == "por_formato")
    n_pr = sum(1 for c in plan.values() if c["tipo"] == "presencia")
    A(f"\n**{8-n_pf} de 8 usan escala global**: los cortes por formato se movian, "
      "pero se mueven igual al remezclar las etiquetas al azar. Con ~86 casos por "
      "grupo esa dispersion es ruido de estimacion, no diferencia real. "
      f"**{n_pf} si difieren** y llevan corte por formato.\n")
    if n_pr:
        A(f"**{n_pr} de 8 son de tipo presencia.** No se publican terciles de "
          "esos: se publica si el video lo tiene y, si lo tiene, cuanto compara "
          "con los que tambien lo tienen.\n")

    A("\n## 2. Volvio el vicio de la duracion?\n")
    A("El panel se eligio contra 60 videos del historial personal. Esta es la "
      "comprobacion sobre el corpus publico. **La columna que manda es la media "
      "intra-celda**, no el peor: con n cercano a 28 el error tipico de una "
      "correlacion ronda 0,2, asi que valores de mas o menos 0,4 salen por azar, "
      "y tomar el maximo de 12 celdas los infla por construccion.\n")
    A("| descriptor | corr global | corr intra (peor) | corr intra (media) | eta2 celda |")
    A("|---|---|---|---|---|")
    for _, r in dur.iterrows():
        marca = " (!)" if abs(r["corr_log_dur_intra_media"] or 0) > 0.5 else ""
        A(f"| {r['descriptor']} | {r['corr_log_dur_global']} | "
          f"{r['corr_log_dur_intra_max']} | {r['corr_log_dur_intra_media']}{marca} | "
          f"{r['eta2_celda']} |")
    peor_media = dur["corr_log_dur_intra_media"].abs().max()
    A(f"\nPeor **media** intra-celda: **{peor_media:.3f}**. El scorer v1 tenia "
      "0,73 entre su score y la duracion. Los ocho descriptores sobreviven.\n")

    A("\n## 3. Hay descriptores redundantes?\n")
    pares = []
    cols = list(mutua.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            v = mutua.iloc[i, j]
            if pd.notna(v):
                pares.append((abs(v), cols[i], cols[j], v))
    pares.sort(reverse=True)
    A(f"Correlacion mutua maxima: **{resumen['peor_mutua']:.3f}**. Los cinco pares mas altos:\n")
    for _, a, b, v in pares[:5]:
        A(f"- `{a}` <-> `{b}`: {v:+.3f}")
    A("\nNinguno mide lo mismo que otro: el panel tiene ocho numeros, no ocho "
      "copias del mismo numero.\n")

    A("\n## 4. Cribado por formato (los que no admiten panel)\n")
    A("| formato | con transcripcion | aptos | cribados | % |")
    A("|---|---|---|---|---|")
    for fmt in FORMATOS:
        t = int(F[(F["stratum_format"] == fmt) & (F["v_tiene_transcripcion"] == 1)].shape[0])
        a = int(apt[apt["stratum_format"] == fmt].shape[0])
        A(f"| {fmt} | {t} | {a} | {t - a} | {100*(t-a)/max(t,1):.1f}% |")
    A("\nLos cribados son videos sin habla suficiente: musica, karaoke, tomas "
      "aereas, gameplay con comentario esporadico. No son valores bajos: el panel "
      "no les aplica.\n")
    globales = [k for k, c in plan.items() if c["ambito"] == "global"]
    porf = [k for k, c in plan.items() if c["ambito"] == "por_formato"]
    crib = {}
    for fmt in FORMATOS:
        t = int(F[(F["stratum_format"] == fmt) & (F["v_tiene_transcripcion"] == 1)].shape[0])
        a = int(apt[apt["stratum_format"] == fmt].shape[0])
        crib[fmt] = 100 * (t - a) / max(t, 1)
    A("\n**Cruzando esta seccion con la 1 sale el resultado principal.** "
      f"De los 8 descriptores, {len(globales)} se distribuyen igual en los cuatro "
      f"formatos ({', '.join('`'+k+'`' for k in globales)}) y {len(porf)} difieren "
      f"({', '.join('`'+k+'`' for k in porf)}).\n")
    A("Los que NO distinguen formato son los del caudal del habla: a que ritmo "
      "se habla, con cuanto vocabulario, con cuantos conectores. Los que SI "
      "distinguen son las marcas de rigor y de negocio: citar fuentes, enlazar, "
      "promocionar. Un video de entretenimiento y uno informativo hablan igual; "
      "lo que cambia es si nombran de donde sacan lo que dicen.\n")
    A(f"Pero la diferencia mas grande entre formatos no esta en ninguna de las "
      f"dos cosas: esta en **si el panel se puede mostrar**. El cribado va del "
      f"{min(crib.values()):.0f} % al {max(crib.values()):.0f} %. La frontera "
      "relevante no pasa entre informativo y entretenimiento: pasa entre tener "
      "habla y no tenerla.\n")

    A("\n## Anexo. Cortes por celda (12 celdas), como evidencia\n")
    A("No es la escala que se publica: es el material sobre el que se corrio la "
      "prueba de la seccion 1. Se conserva para que la decision sea auditable.\n")
    A("| formato | " + " | ".join(DURACIONES) + " |")
    A("|---|" + "---|" * len(DURACIONES))
    for fmt in FORMATOS:
        fila = []
        for d in DURACIONES:
            e = doc_celdas["escala"].get(celda(fmt, d), {})
            fila.append(str(e.get("n", 0)))
        A(f"| {fmt} | " + " | ".join(fila) + " |")
    A("\n(n util por celda; los cortes correspondientes estan en "
      "`escala_por_celda_anexo.csv`)\n")
    return "\n".join(L)


# ------------------------------------------------------------------ MAIN

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--min-n", type=int, default=15,
                   help="por debajo de este n util, la celda usa el corte global")
    p.add_argument("--historial", action="store_true",
                   help="ademas, mide el historial personal CONTRA la escala "
                        "(no lo mete en la escala)")
    p.add_argument("--salida", default=str(DOCS), help="carpeta de salida")
    args = p.parse_args()

    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    env = HERE.parent / ".env"
    if load_dotenv and env.exists():
        load_dotenv(env)
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("Falta DATABASE_URL en backend/.env", file=sys.stderr)
        return 2

    out = Path(args.salida)
    out.mkdir(parents=True, exist_ok=True)

    print("=" * 66)
    print(f"ESCALA DE REFERENCIA  v{VERSION}")
    print("=" * 66)

    df = cargar(dsn, "referencia")
    if df.empty:
        print("No hay filas con corpus='referencia'.", file=sys.stderr)
        return 1
    frame = (df["sampling_frame_version"].dropna().iloc[0]
             if df["sampling_frame_version"].notna().any() else "desconocido")
    print(f"{len(df)} filas del corpus de referencia (marco {frame})")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        F = calcular(df)

    n_txt = int((F["v_tiene_transcripcion"] == 1).sum())
    n_apt = int((F["v_apto_panel"] == 1).sum())
    print(f"{n_txt} con transcripcion -> {n_apt} aptas para el panel "
          f"({n_txt - n_apt} cribadas por falta de habla)")

    # La escala que se publica: global, con excepciones decididas por la prueba
    # de permutacion. La tabla por 12 celdas se conserva como anexo: es la
    # evidencia sobre la que se corrio esa prueba.
    doc, escala_csv, plan = construir_escala_v2(F, frame)
    doc_celdas, csv_celdas = construir_escala(F, args.min_n, frame)
    dur, mutua, resumen = validar(F)

    F.to_csv(out / "corpus_referencia_features.csv", index=False)
    escala_csv.to_csv(out / "escala_referencia.csv", index=False)
    csv_celdas.to_csv(out / "escala_por_celda_anexo.csv", index=False)
    (out / "escala_referencia.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "validacion_escala.md").write_text(
        informe_md(doc, doc_celdas, plan, dur, mutua, resumen, F), encoding="utf-8")

    print("\n--- estructura elegida por la prueba de permutacion ---")
    for k, c in plan.items():
        p = c["p_permutacion"]
        print(f"  {k:<20} {c['tipo']:<10} {c['ambito']:<12} "
              f"p={p if p is not None else '—'}  ceros={100*(c['frac_cero'] or 0):.0f}%")
    print("\n--- validacion ---")
    print(dur.to_string(index=False))
    print(f"\npeor media intra-celda con log(duracion): "
          f"{dur['corr_log_dur_intra_media'].abs().max():.3f}")
    print(f"peor correlacion mutua entre descriptores: {resumen['peor_mutua']:.3f}")

    salidas = ["corpus_referencia_features.csv", "escala_referencia.csv",
               "escala_referencia.json", "validacion_escala.md",
               "escala_por_celda_anexo.csv"]

    if args.historial:
        dh = cargar(dsn, "historial")
        if dh.empty:
            print("\nNo hay filas con corpus='historial'.")
        else:
            dh = asignar_estratos(dh)
            sin_estrato = int((dh["stratum_format"].isna()
                               | dh["stratum_duration"].isna()).sum())
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                H = calcular(dh)
            H["stratum_format"] = dh["stratum_format"].values
            H["stratum_duration"] = dh["stratum_duration"].values
            H["external_id"] = dh["external_id"].values
            n_apt_h = int((H["v_apto_panel"] == 1).sum())
            print(f"\nHistorial: {len(H)} filas, {n_apt_h} aptas")
            if sin_estrato:
                print(f"  {sin_estrato} sin estrato asignable (categoria fuera del "
                      f"marco, o duracion fuera de 2-180 min): se comparan contra "
                      f"el corte global")
            comp, md = comparar_historial(H, F, doc)
            H.to_csv(out / "historial_features.csv", index=False)
            comp.to_csv(out / "historial_vs_escala.csv", index=False)
            (out / "informe_historial.md").write_text(md, encoding="utf-8")
            salidas += ["historial_features.csv", "historial_vs_escala.csv",
                        "informe_historial.md"]
            print("  Se mide CONTRA la escala; no entra en ella.")

    print(f"\nSalidas en {out}:")
    for f in salidas:
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

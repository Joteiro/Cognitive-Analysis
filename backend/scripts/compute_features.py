#!/usr/bin/env python3
"""
compute_features.py — El calculador de ejes. (v1.0)

Lee lo que YA está en la base (transcripción, segmentos, descripción, tags,
capítulos) y calcula la "etiqueta nutricional" de cada video: indicadores
crudos normalizados + nivel bajo/medio/alto por eje.

NO TOCA YOUTUBE. Ni una petición. Podés correrlo cincuenta veces mientras
afinás las definiciones sin arriesgar un solo bloqueo.

CINCO EJES, SIN PESOS Y SIN LETRA
---------------------------------
  1. Densidad informativa   cifras, ejemplos concretos, menciones de fuentes
  2. Carga cognitiva        ritmo de habla, diversidad léxica, longitud de frase
  3. Optimización retención llamadas a la acción, preguntas, repetición
  4. Trazabilidad           enlaces verificables, capítulos, descripción
  5. Correspondencia        ¿el video habla de lo que promete el título?

TRES REGLAS QUE SOSTIENEN TODO
------------------------------
  · Todo se normaliza por 100 palabras o por minuto. Nunca totales: un total
    mide duración disfrazada.
  · Los cortes bajo/medio/alto son TERCIOS DEL CORPUS, no umbrales inventados.
    La etiqueta dice "alto respecto de esta muestra", y así hay que mostrarlo.
  · El nivel de un eje es la MEDIANA de los tercios de sus indicadores. Cero
    pesos arbitrarios, cero agregación entre ejes, cero letra final.

USO
---
    python compute_features.py                 # calcula y guarda
    python compute_features.py --dry-run       # sólo muestra la tabla
    python compute_features.py --csv salida.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

FEATURES_VERSION = "1.0"

# Con menos de 30 videos los tercios son poco más que una anécdota.
MIN_CORPUS_FOR_TERTILES = 30

MATTR_WINDOW = 200      # ventana fija: hace la diversidad léxica insensible
REPEAT_WINDOW = 500     # a la longitud del texto, que es el vicio del TTR clásico

log = logging.getLogger("features")


# ─── DICCIONARIOS POR IDIOMA ──────────────────────────────────────────────────

MARKERS = {
    "es": {
        "ejemplos": r"\bpor ejemplo\b|\bpongamos\b|\bsupongamos\b|\bimagin[aá]\w*\b|"
                    r"\bes decir\b|\bo sea\b|\bun caso\b|\bcomo cuando\b|\bpensemos en\b",
        "fuentes": r"\bseg[uú]n\b|\bun estudio\b|\buna investigaci[oó]n\b|\bel informe\b|"
                   r"\bpublicad[oa]\b|\bde acuerdo con\b|\bdatos de\b|\bel paper\b|"
                   r"\bla universidad\b|\blos investigadores\b|\bla revista\b|"
                   r"\bel artículo\b|\bla encuesta\b",
        "enganche": r"\bsuscr[ií]b\w*\b|\bcampanita\b|\bdale like\b|\bd[ée]jame? un comentario\b|"
                    r"\bcoment[aá] abajo\b|\benlace en la descripci[oó]n\b|"
                    r"\blink en la descripci[oó]n\b|\bpatrocina\w*\b|\bc[oó]digo de descuento\b|"
                    r"\bantes de empezar\b|\bqued[aá]te hasta el final\b|\bno te vayas\b",
    },
    "en": {
        "ejemplos": r"\bfor example\b|\bfor instance\b|\blet's say\b|\bsuppose\b|"
                    r"\bimagine\b|\bthat is\b|\bsuch as\b|\bthink about\b",
        "fuentes": r"\baccording to\b|\ba study\b|\bresearch(ers)?\b|\bthe report\b|"
                   r"\bpublished\b|\bdata from\b|\bthe paper\b|\bthe university\b|"
                   r"\bthe journal\b|\bthe survey\b|\bevidence\b",
        "enganche": r"\bsubscribe\b|\bhit the bell\b|\blike (this|the) video\b|"
                    r"\bcomment below\b|\blink in the description\b|\bsponsor\w*\b|"
                    r"\bdiscount code\b|\bstick around\b|\bbefore we (start|begin)\b|"
                    r"\bdon'?t forget to\b",
    },
}

STOPWORDS = {
    "es": set("""el la los las un una unos unas de del al a ante bajo con contra desde durante en
        entre hacia hasta para por segun sin sobre tras y o u ni que se su sus lo le les me te nos
        es son era eran ser estar esta este esto estos estas mas muy como cuando donde quien cual
        porque pero si no ya hay ha han he hemos fue fueron todo toda todos todas otro otra""".split()),
    "en": set("""the a an of to in on at by for with from and or but if not is are was were be been
        being this that these those it its as we you they he she i our your their there here what
        which who whom how when where why all any some more most very can will just""".split()),
}

LINKS_VERIFICABLES = re.compile(
    r"doi\.org|arxiv\.org|pubmed|ncbi\.nlm\.nih\.gov|nature\.com|science\.org|"
    r"sciencedirect|springer|jstor|researchgate|scholar\.google|\.edu\b|\.gov\b|"
    r"wikipedia\.org|who\.int|europa\.eu|ine\.es|ourworldindata|nationalgeographic|"
    r"bbc\.|reuters\.|apnews\.|elpais\.|nytimes\.|theguardian\.", re.I)

LINKS_COMERCIALES = re.compile(
    r"amzn\.to|amazon\.[a-z.]+/.*tag=|patreon\.com|ko-fi|buymeacoffee|shopify|"
    r"bit\.ly|linktr\.ee|/ref=|utm_|nordvpn|surfshark|skillshare|brilliant\.org|"
    r"hostinger|squarespace|honey|audible", re.I)

URL_RE = re.compile(r"https?://\S+")
WORD_RE = re.compile(r"\b[\wáéíóúüñÁÉÍÓÚÜÑ']+\b", re.UNICODE)
NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*%?")


# ─── MÉTRICAS ─────────────────────────────────────────────────────────────────

def pick_lang(*candidates) -> str:
    for c in candidates:
        if c and str(c).split("-")[0].lower() in MARKERS:
            return str(c).split("-")[0].lower()
    return "es"


def rate(pattern: str, text: str, n_words: int, per: int) -> float | None:
    if not n_words:
        return None
    hits = len(re.findall(pattern, text, flags=re.IGNORECASE))
    return round(hits * per / n_words, 3)


def mattr(words: list[str], window: int = MATTR_WINDOW) -> float | None:
    """
    Moving-Average Type-Token Ratio. El TTR clásico baja mecánicamente con la
    longitud del texto —por eso el `lexical_richness` del scorer viejo medía,
    en el fondo, duración—. Promediar sobre ventanas fijas lo arregla.
    """
    if len(words) < 50:
        return None
    if len(words) < window:
        return round(len(set(words)) / len(words), 3)
    ratios = [len(set(words[i:i + window])) / window
              for i in range(0, len(words) - window + 1, max(1, window // 4))]
    return round(statistics.fmean(ratios), 3)


def repeticion(words: list[str], window: int = REPEAT_WINDOW) -> float | None:
    """Proporción de bigramas que se repiten, medida en ventanas de tamaño fijo."""
    if len(words) < 100:
        return None
    step = max(1, window // 2)
    vals = []
    for i in range(0, max(1, len(words) - window + 1), step):
        chunk = words[i:i + window]
        if len(chunk) < 50:
            continue
        bigrams = [f"{chunk[j]}_{chunk[j+1]}" for j in range(len(chunk) - 1)]
        c = Counter(bigrams)
        repetidos = sum(v for v in c.values() if v > 1)
        vals.append(repetidos / len(bigrams))
    return round(statistics.fmean(vals), 3) if vals else None


def cobertura_promesa(title: str, tags, transcript_words: set, lang: str) -> float | None:
    """
    ¿El video habla de lo que promete? Mide qué porción del vocabulario con
    contenido del título y los tags aparece de verdad en la transcripción.
    Es la versión medible del clickbait: no "¿usa palabras exageradas?" sino
    "¿cumple lo que anuncia?" — y es lo más fácil de verificar por un humano.
    """
    if not transcript_words:
        return None
    promesa = WORD_RE.findall((title or "").lower())
    if isinstance(tags, list):
        for t in tags:
            promesa += WORD_RE.findall(str(t).lower())
    sw = STOPWORDS.get(lang, set())
    promesa = {w for w in promesa if len(w) > 3 and w not in sw and not w.isdigit()}
    if not promesa:
        return None
    return round(len(promesa & transcript_words) / len(promesa), 3)


def compute_one(row: dict) -> dict:
    tx = row.get("transcript") or ""
    words = [w.lower() for w in WORD_RE.findall(tx)]
    n = len(words)
    lang = pick_lang(row.get("transcript_lang"), row.get("video_language"))
    mk = MARKERS[lang]

    n_periods = tx.count(".")
    # Los subtítulos automáticos vienen sin puntuación. Si hay menos de un punto
    # cada 60 palabras, asumimos que no la hay y no inventamos la métrica.
    has_punct = bool(n and n_periods and (n / n_periods) < 60)

    desc = row.get("description") or ""
    urls = URL_RE.findall(desc)
    dur = row.get("duration_seconds")

    tset = set(words)
    tags = row.get("tags")
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = []

    return {
        "content_item_id": row["id"],
        "features_version": FEATURES_VERSION,
        "n_words": n,
        "duration_seconds": dur,
        "lang": lang,
        "transcript_source": row.get("transcript_source"),
        "has_punctuation": has_punct,
        "has_description": bool(desc and len(desc) > 20),
        "has_tags": bool(tags),

        "cifras_100w": (round(len(NUMBER_RE.findall(tx)) * 100 / n, 3) if n else None),
        "ejemplos_1000w": rate(mk["ejemplos"], tx, n, 1000),
        "fuentes_1000w": rate(mk["fuentes"], tx, n, 1000),

        "palabras_por_minuto": (round(n / (dur / 60.0), 1) if (n and dur) else None),
        "mattr": mattr(words),
        "palabras_por_frase": (round(n / n_periods, 1) if has_punct else None),

        "enganche_1000w": rate(mk["enganche"], tx, n, 1000),
        "preguntas_1000w": (round(tx.count("?") * 1000 / n, 3) if (has_punct and n) else None),
        "repeticion": repeticion(words),

        "n_links": len(urls),
        "n_links_verificables": sum(1 for u in urls if LINKS_VERIFICABLES.search(u)),
        "n_links_comerciales": sum(1 for u in urls if LINKS_COMERCIALES.search(u)),
        "n_chapters": row.get("n_chapters"),
        "desc_words": len(desc.split()) if desc else 0,

        "cobertura_promesa": cobertura_promesa(row.get("title"), tags, tset, lang),
    }


# ─── TERCIOS Y NIVELES ────────────────────────────────────────────────────────

# Cada eje y sus indicadores. `False` = valores altos van al tercio "bajo"
# (ej. mucha repetición NO es "alta diversidad"). No hay pesos: el nivel del
# eje es la mediana de los tercios de sus indicadores.
EJES = {
    "nivel_densidad":        [("cifras_100w", True), ("ejemplos_1000w", True),
                              ("fuentes_1000w", True)],
    "nivel_carga":           [("palabras_por_minuto", True), ("mattr", True),
                              ("palabras_por_frase", True)],
    "nivel_retencion":       [("enganche_1000w", True), ("preguntas_1000w", True),
                              ("repeticion", True)],
    "nivel_trazabilidad":    [("n_links_verificables", True), ("n_chapters", True),
                              ("desc_words", True)],
    "nivel_correspondencia": [("cobertura_promesa", True)],
}

NIVELES = ["bajo", "medio", "alto"]


def tertile_cuts(values: list[float]) -> tuple[float, float] | None:
    vals = sorted(v for v in values if v is not None)
    if len(vals) < 6:
        return None
    return (statistics.quantiles(vals, n=3)[0], statistics.quantiles(vals, n=3)[1])


def to_tertile(v, cuts, ascending: bool) -> int | None:
    if v is None or cuts is None:
        return None
    lo, hi = cuts
    idx = 0 if v <= lo else (1 if v <= hi else 2)
    return idx if ascending else 2 - idx


def assign_levels(rows: list[dict]) -> None:
    indicadores = {ind for ejes in EJES.values() for ind, _ in ejes}
    cuts = {ind: tertile_cuts([r.get(ind) for r in rows]) for ind in indicadores}

    for ind, c in cuts.items():
        if c is None:
            log.warning("  '%s': datos insuficientes, no se calculan tercios", ind)
        else:
            log.info("  %-22s cortes en %.3f y %.3f", ind, c[0], c[1])

    for r in rows:
        for eje, indics in EJES.items():
            ts = [to_tertile(r.get(ind), cuts[ind], asc) for ind, asc in indics]
            ts = [t for t in ts if t is not None]
            r[eje] = NIVELES[round(statistics.median(ts))] if ts else None


# ─── PERSISTENCIA ─────────────────────────────────────────────────────────────

COLUMNS = ["content_item_id", "features_version", "n_words", "duration_seconds",
           "lang", "transcript_source", "has_punctuation", "has_description",
           "has_tags", "cifras_100w", "ejemplos_1000w", "fuentes_1000w",
           "palabras_por_minuto", "mattr", "palabras_por_frase", "enganche_1000w",
           "preguntas_1000w", "repeticion", "n_links", "n_links_verificables",
           "n_links_comerciales", "n_chapters", "desc_words", "cobertura_promesa",
           "nivel_densidad", "nivel_carga", "nivel_retencion", "nivel_trazabilidad",
           "nivel_correspondencia"]

UPSERT = f"""
INSERT INTO content_features ({", ".join(COLUMNS)}, computed_at)
VALUES ({", ".join("%(" + c + ")s" for c in COLUMNS)}, %(computed_at)s)
ON CONFLICT (content_item_id, features_version) DO UPDATE SET
    {", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS if c not in
               ("content_item_id", "features_version"))},
    computed_at = EXCLUDED.computed_at;
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Calculador de ejes descriptivos")
    ap.add_argument("--dry-run", action="store_true", help="no escribe en la base")
    ap.add_argument("--csv", default=None, help="volcar también a un CSV")
    ap.add_argument("--env", default=None)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    env_path = Path(args.env) if args.env else Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        log.error("No encuentro DATABASE_URL en %s", env_path)
        return 1

    conn = psycopg2.connect(dsn)
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT id, external_id, title, transcript, transcript_lang,
                   transcript_source, video_language, description, tags,
                   n_chapters, duration_seconds
              FROM content_items
             WHERE source='youtube' AND transcript IS NOT NULL
               AND length(transcript) > 0
             ORDER BY id""")
        items = [dict(r) for r in cur.fetchall()]

    if not items:
        log.error("No hay ninguna transcripción en la base todavía.")
        return 1

    log.info("Calculando ejes sobre %d videos con transcripción…\n", len(items))
    rows = [compute_one(r) for r in items]

    log.info("Cortes de los tercios (calculados sobre este corpus):")
    assign_levels(rows)

    if len(items) < MIN_CORPUS_FOR_TERTILES:
        log.warning("\n⚠  Sólo %d videos. Los tercios son PROVISIONALES: con este "
                    "tamaño\n   mueven mucho al agregar datos. Volvé a correr esto "
                    "cuando termine\n   la cola de enriquecimiento.", len(items))

    # ── Tabla en pantalla ──
    log.info("\n%-30s %5s %6s %6s %6s %6s  %s", "VIDEO", "PAL", "P/MIN",
             "MATTR", "CIFRA", "FUENT", "DENS/CARGA/RETEN/TRAZ/CORR")
    for it, r in zip(items, rows):
        def f(v, w=6, d=2):
            return f"{v:{w}.{d}f}" if isinstance(v, (int, float)) else " " * (w - 1) + "—"
        niveles = "/".join((r[e] or "—")[:4] for e in EJES)
        log.info("%-30s %5d %s %s %s %s  %s",
                 (it["title"] or "")[:30], r["n_words"],
                 f(r["palabras_por_minuto"], 6, 0), f(r["mattr"]),
                 f(r["cifras_100w"]), f(r["fuentes_1000w"]), niveles)

    # ── Chequeo de sanidad: ¿algún eje sigue midiendo duración? ──
    log.info("\nCorrelación de cada indicador con la duración (ideal: cerca de 0):")
    durs = [r["duration_seconds"] for r in rows]
    for ind in ["cifras_100w", "ejemplos_1000w", "fuentes_1000w",
                "palabras_por_minuto", "mattr", "repeticion", "cobertura_promesa"]:
        pares = [(d, r[ind]) for d, r in zip(durs, rows)
                 if d is not None and r[ind] is not None]
        if len(pares) >= 5:
            xs, ys = zip(*pares)
            try:
                c = statistics.correlation(xs, ys)
                alarma = "  ← ojo, mide duración" if abs(c) > 0.6 else ""
                log.info("  %-22s r = %+.2f  (n=%d)%s", ind, c, len(pares), alarma)
            except statistics.StatisticsError:
                pass

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["external_id"] + COLUMNS)
            w.writeheader()
            for it, r in zip(items, rows):
                w.writerow({"external_id": it["external_id"], **r})
        log.info("\nCSV: %s", args.csv)

    if not args.dry_run:
        now = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(UPSERT, {**r, "computed_at": now})
        conn.commit()
        log.info("\nGuardadas %d filas en content_features (versión %s).",
                 len(rows), FEATURES_VERSION)
    else:
        log.info("\n(dry-run: no se escribió nada)")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

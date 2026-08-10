#!/usr/bin/env python3
"""
enrich_local.py — Enriquecimiento de contenidos SIN Supadata.  (v3.0)

`content_items` funciona como cola de trabajo. Cada video tiene un estado, un
contador de intentos y una hora de próximo turno. El worker agarra una tanda
chica de lo que está pendiente y vencido, la procesa, y se apaga.

POR QUÉ TANDAS CHICAS Y NO UNA CORRIDA LARGA
--------------------------------------------
YouTube no publica cuota; tiene un antibot que mira volumen y regularidad.
Diez peticiones en una hora no lo despiertan. Setenta seguidas, sí. Así que
en vez de una corrida heroica que termina bloqueada, se programa una tanda
por hora y a la mañana está todo. Es más lento en el reloj y muchísimo más
rápido en la práctica, porque no hay que empezar de nuevo.

POR QUÉ EN LOCAL Y NO EN LA NUBE
--------------------------------
YouTube bloquea las IPs de datacenter (Render, AWS, GCP…). Una cola en la
nube no arregla eso: sólo ordena los fallos. Corre en tu máquina.

ESTADOS
-------
    NULL          nunca se intentó
    ok            metadatos + transcripción — terminado
    partial       metadatos sí, transcripción no — reintentable
    failed        nada — reintentable
    no_subs       el video no tiene subtítulos — DEFINITIVO
    geo_blocked   bloqueado por región — DEFINITIVO
    unavailable   privado, borrado o de pago — DEFINITIVO
    exhausted     se agotaron los reintentos — no se toca sin --force

USO
---
    pip install -r requirements-enrich.txt

    python enrich_local.py --max 10                   # una tanda (modo worker)
    python enrich_local.py --status                   # ver la cola, sin tocar red
    python enrich_local.py --only-missing-transcript  # corrida larga clásica
    python enrich_local.py --proxy http://user:pass@host:port
    python enrich_local.py --force --ids abc123

En modo worker (--max), ante un bloqueo NO espera: reprograma lo pendiente
para dentro de una hora y sale con código 0, para que la tarea programada
lo reintente sola en el próximo turno.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

ENRICHER_VERSION = "3.0"

PREFERRED_LANGS = ["es", "es-419", "es-ES", "en", "en-US", "en-GB"]

# Espera antes del siguiente intento, según cuántos lleva: 15 min, 1 h, 4 h, 24 h.
# Al quinto fallo el video pasa a 'exhausted' y deja de molestar.
BACKOFF_MINUTES = [15, 60, 240, 1440]

# Sólo para el modo corrida larga (sin --max). El worker no espera: sale.
COOLDOWNS = [1800, 5400]

# Cuando el worker se topa con un bloqueo, reprograma lo pendiente. Si la IP
# sigue castigada corrida tras corrida, no tiene sentido insistir cada hora:
# la espera se va estirando sola hasta un día. Cuando algo sale bien, vuelve a
# cero. Así una IP en penalización deja de recibir golpes y se recupera antes.
BLOCK_BACKOFF_HOURS = [1, 3, 6, 12, 24]
STATE_FILE = Path(__file__).resolve().parent / ".enrich_state.json"


def read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"consecutive_blocks": 0}


def write_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state))
    except Exception:
        pass

CATEGORY_NAME_TO_ID = {
    "Film & Animation": "1", "Autos & Vehicles": "2", "Music": "10",
    "Pets & Animals": "15", "Sports": "17", "Travel & Events": "19",
    "Gaming": "20", "People & Blogs": "22", "Comedy": "23",
    "Entertainment": "24", "News & Politics": "25", "Howto & Style": "26",
    "Education": "27", "Science & Technology": "28",
    "Nonprofits & Activism": "29",
}

NOISE_PATTERNS = re.compile(r"\[[^\]]{0,40}\]|\([^)]{0,40}\)|♪[^♪]*♪", re.IGNORECASE)

BLOCK_HINTS = ("ipblocked", "requestblocked", "too many requests",
               "sign in to confirm", "http error 429", "blocked")
COOKIE_HINTS = ("cookie database", "dpapi", "failed to decrypt",
                "could not copy", "cookies from browser")

# Fallos PERMANENTES: reintentarlos gasta peticiones que no te sobran.
NO_SUBS_HINTS = ("transcriptsdisabled", "notranscriptfound",
                 "subtitles are disabled", "no tiene subtítulos",
                 "sin subtítulos disponibles")
GEO_HINTS = ("not made this video available in your country",
             "not available in your country", "blocked it in your country",
             "geo restricted", "geo-restricted")
GONE_HINTS = ("video unavailable", "private video", "has been removed",
              "account associated with this video has been terminated",
              "members-only", "this live event will begin")

PERMANENT_STATES = ("ok", "no_subs", "geo_blocked", "unavailable", "exhausted")

log = logging.getLogger("enrich")


class Blocked(Exception):
    """YouTube nos cortó el paso. Temporal, pero no se arregla insistiendo."""


class CookieProblem(Exception):
    """No se pudieron leer las cookies del navegador. Fatal, no reintentable."""


def _matches(err_or_text, hints) -> bool:
    txt = (f"{type(err_or_text).__name__} {err_or_text}"
           if isinstance(err_or_text, BaseException) else str(err_or_text)).lower()
    return any(h in txt for h in hints)


def looks_blocked(e) -> bool:
    return _matches(e, BLOCK_HINTS)


def looks_like_cookies(e) -> bool:
    return _matches(e, COOKIE_HINTS)


def classify_permanent(errors: list[str]) -> str | None:
    blob = " ".join(errors)
    if _matches(blob, GEO_HINTS):
        return "geo_blocked"
    if _matches(blob, GONE_HINTS):
        return "unavailable"
    if _matches(blob, NO_SUBS_HINTS):
        return "no_subs"
    return None


# ─── SUBTÍTULOS DESDE EL info DE yt_dlp ───────────────────────────────────────

def _pick_track(info: dict):
    """
    Prioriza subtítulos MANUALES sobre AUTOMÁTICOS: los manuales traen
    puntuación real, los del ASR de YouTube no, y de eso depende qué señales
    lingüísticas podés medir después.
    """
    manual = info.get("subtitles") or {}
    autos = info.get("automatic_captions") or {}
    own = (info.get("language") or "").split("-")[0]
    order = PREFERRED_LANGS + ([own] if own else [])

    for pool, is_generated in ((manual, False), (autos, True)):
        for lang in order:
            if pool.get(lang):
                return pool[lang], lang, is_generated
        bases = {l.split("-")[0] for l in order}
        for lang, tracks in pool.items():
            if tracks and lang.split("-")[0] in bases:
                return tracks, lang, is_generated
        for lang, tracks in pool.items():
            if tracks:
                return tracks, lang, is_generated
    return None, None, None


def _parse_json3(raw: str) -> list[dict]:
    out = []
    for ev in json.loads(raw).get("events") or []:
        text = "".join(s.get("utf8", "") for s in (ev.get("segs") or [])).strip()
        if not text:
            continue
        out.append({"text": text,
                    "start": round(ev.get("tStartMs", 0) / 1000.0, 2),
                    "duration": round(ev.get("dDurationMs", 0) / 1000.0, 2)})
    return out


def _parse_vtt(raw: str) -> list[dict]:
    out, start, dur, buf = [], None, None, []

    def to_s(ts: str) -> float:
        p = [float(x) for x in ts.replace(",", ".").split(":")]
        while len(p) < 3:
            p.insert(0, 0.0)
        return p[0] * 3600 + p[1] * 60 + p[2]

    for line in raw.splitlines():
        line = line.strip()
        if "-->" in line:
            if buf and start is not None:
                out.append({"text": " ".join(buf), "start": start, "duration": dur})
            a, b = [p.strip().split(" ")[0] for p in line.split("-->")[:2]]
            start, dur, buf = round(to_s(a), 2), round(to_s(b) - to_s(a), 2), []
        elif line and not line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            clean = re.sub(r"<[^>]+>", "", line)
            if clean and (not buf or clean != buf[-1]):
                buf.append(clean)
    if buf and start is not None:
        out.append({"text": " ".join(buf), "start": start, "duration": dur})
    return out


def _assemble(segments, lang, is_generated) -> dict | None:
    text = re.sub(r"\s+", " ",
                  NOISE_PATTERNS.sub(" ", " ".join(s["text"] for s in segments))).strip()
    if not text:
        return None
    return {"text": text, "segments": segments, "lang": lang,
            "is_generated": is_generated,
            "source": "youtube_auto" if is_generated else "youtube_manual"}


def transcript_from_info(ydl, info: dict) -> dict | None:
    tracks, lang, is_generated = _pick_track(info)
    if not tracks:
        return None
    by_ext = {t.get("ext"): t for t in tracks if t.get("url")}
    for ext in ("json3", "srv3", "vtt", "srv1"):
        track = by_ext.get(ext)
        if not track:
            continue
        try:
            raw = ydl.urlopen(track["url"]).read().decode("utf-8", "replace")
        except Exception as e:
            if looks_blocked(e):
                raise Blocked(str(e)) from e
            continue
        try:
            segs = _parse_json3(raw) if ext in ("json3", "srv3") else _parse_vtt(raw)
        except Exception:
            continue
        if segs and (tr := _assemble(segs, lang, is_generated)):
            return tr
    return None


def transcript_fallback(video_id: str, proxy: str | None) -> dict:
    from youtube_transcript_api import YouTubeTranscriptApi
    kwargs = {}
    if proxy:
        try:
            from youtube_transcript_api.proxies import GenericProxyConfig
            kwargs["proxy_config"] = GenericProxyConfig(http_url=proxy, https_url=proxy)
        except Exception:
            pass

    tlist = YouTubeTranscriptApi(**kwargs).list(video_id)
    chosen = is_generated = None
    try:
        chosen, is_generated = tlist.find_manually_created_transcript(PREFERRED_LANGS), False
    except Exception:
        try:
            chosen, is_generated = tlist.find_generated_transcript(PREFERRED_LANGS), True
        except Exception:
            for t in tlist:
                chosen, is_generated = t, bool(getattr(t, "is_generated", True))
                break
    if chosen is None:
        raise RuntimeError("sin subtítulos disponibles")

    segs = [{"text": getattr(s, "text", ""),
             "start": round(float(getattr(s, "start", 0.0)), 2),
             "duration": round(float(getattr(s, "duration", 0.0)), 2)}
            for s in chosen.fetch()]
    tr = _assemble(segs, getattr(chosen, "language_code", None), is_generated)
    if tr is None:
        raise RuntimeError("transcripción vacía")
    return tr


# ─── EXTRACCIÓN ───────────────────────────────────────────────────────────────

def build_ydl(cookies_browser=None, cookies_file=None, proxy=None):
    import yt_dlp
    opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "noplaylist": True,
        "retries": 2, "socket_timeout": 30,
        "writesubtitles": False, "writeautomaticsub": False,
        "subtitleslangs": PREFERRED_LANGS,

        # No necesitamos NINGÚN formato de video: sólo la ficha y los subtítulos.
        # Sin esto, yt_dlp intenta elegir un formato descargable y aborta con
        # "Requested format is not available" en directos, videos con DRM o
        # cuando falta un motor de JavaScript — perdiendo también los subtítulos,
        # que sí estaban disponibles.
        "ignore_no_formats_error": True,
        "allow_unplayable_formats": True,
        "format": "bestaudio/worst/best",
    }
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
    if cookies_file:
        opts["cookiefile"] = cookies_file
    if proxy:
        opts["proxy"] = proxy
    return yt_dlp.YoutubeDL(opts)


def extract(ydl, video_id: str, use_fallback: bool, proxy: str | None):
    errors: list[str] = []
    try:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}",
                                download=False)
    except Exception as e:
        if looks_like_cookies(e):
            raise CookieProblem(str(e)) from e
        if looks_blocked(e):
            raise Blocked(str(e)) from e
        return {}, None, [f"{type(e).__name__}: {e}"]

    cats = info.get("categories") or []
    cat_name = cats[0] if cats else None
    chapters = [{"title": c.get("title"), "start_time": c.get("start_time"),
                 "end_time": c.get("end_time")} for c in (info.get("chapters") or [])]
    ud = info.get("upload_date")

    meta = {
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "channel_id": info.get("channel_id"),
        "duration_seconds": info.get("duration"),
        "description": info.get("description"),
        "tags": info.get("tags") or [],
        "category_name": cat_name,
        "category_id": CATEGORY_NAME_TO_ID.get(cat_name or ""),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "chapters": chapters,
        "n_chapters": len(chapters),
        "upload_date": f"{ud[:4]}-{ud[4:6]}-{ud[6:]}" if ud and len(ud) == 8 else None,
        "video_language": info.get("language"),
    }

    tr = None
    try:
        tr = transcript_from_info(ydl, info)
    except Blocked:
        raise
    except Exception as e:
        errors.append(f"subs_ytdlp: {type(e).__name__}: {e}")

    if tr is None and use_fallback:
        try:
            tr = transcript_fallback(video_id, proxy)
        except Exception as e:
            if looks_blocked(e):
                raise Blocked(str(e)) from e
            errors.append(f"subs_api: {type(e).__name__}: {e}")

    if tr is None and not errors:
        errors.append("subs: el video no tiene subtítulos publicados")
    return meta, tr, errors


# ─── COLA ─────────────────────────────────────────────────────────────────────

UPDATE_SQL = """
UPDATE content_items SET
    title = COALESCE(%(title)s, title),
    channel = COALESCE(%(channel)s, channel),
    channel_id = COALESCE(%(channel_id)s, channel_id),
    duration_seconds = COALESCE(%(duration_seconds)s, duration_seconds),
    description = COALESCE(%(description)s, description),
    tags = COALESCE(%(tags)s::jsonb, tags),
    category_id = COALESCE(%(category_id)s, category_id),
    category_name = COALESCE(%(category_name)s, category_name),
    view_count = COALESCE(%(view_count)s, view_count),
    like_count = COALESCE(%(like_count)s, like_count),
    comment_count = COALESCE(%(comment_count)s, comment_count),
    chapters = COALESCE(%(chapters)s::jsonb, chapters),
    n_chapters = COALESCE(%(n_chapters)s, n_chapters),
    upload_date = COALESCE(%(upload_date)s, upload_date),
    video_language = COALESCE(%(video_language)s, video_language),
    stats_fetched_at = CASE WHEN %(had_meta)s THEN %(now)s ELSE stats_fetched_at END,
    transcript = COALESCE(%(transcript)s, transcript),
    transcript_segments = COALESCE(%(transcript_segments)s::jsonb, transcript_segments),
    transcript_lang = COALESCE(%(transcript_lang)s, transcript_lang),
    transcript_is_generated = COALESCE(%(transcript_is_generated)s, transcript_is_generated),
    transcript_source = COALESCE(%(transcript_source)s, transcript_source),
    transcript_word_count = COALESCE(%(transcript_word_count)s, transcript_word_count),
    transcript_fetched_at = CASE WHEN %(transcript)s IS NOT NULL THEN %(now)s
                                 ELSE transcript_fetched_at END,
    enrichment_status = %(enrichment_status)s,
    enrichment_error = %(enrichment_error)s,
    enriched_at = %(now)s,
    enricher_version = %(enricher_version)s,
    attempts = %(attempts)s,
    last_attempt_at = %(now)s,
    next_attempt_at = %(next_attempt_at)s,
    updated_at = %(now)s
WHERE id = %(id)s;
"""

RESCHEDULE_SQL = """
UPDATE content_items
   SET next_attempt_at = greatest(COALESCE(next_attempt_at, now()), now() + %s::interval),
       last_attempt_at = now()
 WHERE id = ANY(%s);
"""


def select_batch(conn, args):
    cols = "id, external_id, title, COALESCE(attempts,0) AS attempts"
    if args.force:
        where = "TRUE"
    else:
        base = ("(transcript IS NULL OR length(transcript) = 0)"
                if args.only_missing_transcript or args.max else
                """(transcript IS NULL OR length(transcript) = 0
                    OR description IS NULL OR enrichment_status IS NULL)""")
        where = (f"{base} AND (enrichment_status IS NULL OR enrichment_status NOT IN "
                 f"{PERMANENT_STATES})")
        if args.max:  # modo worker: respetar el turno de cada uno
            where += " AND (next_attempt_at IS NULL OR next_attempt_at <= now())"

    params: list = []
    sql = f"SELECT {cols} FROM content_items WHERE source='youtube' AND ({where})"
    if args.ids:
        sql += " AND external_id = ANY(%s)"
        params.append(args.ids)
    sql += " ORDER BY next_attempt_at NULLS FIRST, created_at ASC"
    if args.max or args.limit:
        sql += f" LIMIT {int(args.max or args.limit)}"

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def print_status(conn) -> None:
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT COALESCE(enrichment_status,'(sin intentar)') AS estado,
                   count(*) AS n, max(attempts) AS max_intentos,
                   min(next_attempt_at) AS proximo_turno
              FROM content_items WHERE source='youtube'
             GROUP BY 1 ORDER BY 2 DESC""")
        rows = cur.fetchall()
    log.info("%-16s %5s %9s  %s", "ESTADO", "N", "INTENTOS", "PRÓXIMO TURNO")
    for r in rows:
        turno = r["proximo_turno"].strftime("%d/%m %H:%M") if r["proximo_turno"] else "—"
        log.info("%-16s %5d %9s  %s", r["estado"], r["n"], r["max_intentos"] or 0, turno)


def save(conn, row, meta, tr, errors, status) -> None:
    attempts = int(row["attempts"]) + (0 if status == "ok" else 1)
    if status in PERMANENT_STATES:
        next_at = None
    elif attempts > len(BACKOFF_MINUTES):
        status, next_at = "exhausted", None
    else:
        next_at = datetime.now(timezone.utc) + timedelta(
            minutes=BACKOFF_MINUTES[attempts - 1])

    payload = {
        "id": row["id"], "now": datetime.now(timezone.utc),
        "enrichment_status": status,
        "enrichment_error": (" | ".join(errors))[:2000] or None,
        "enricher_version": ENRICHER_VERSION,
        "attempts": attempts, "next_attempt_at": next_at,
        "had_meta": bool(meta),
        "transcript": tr["text"] if tr else None,
        "transcript_segments": json.dumps(tr["segments"]) if tr else None,
        "transcript_lang": tr["lang"] if tr else None,
        "transcript_is_generated": tr["is_generated"] if tr else None,
        "transcript_source": tr["source"] if tr else None,
        "transcript_word_count": len(tr["text"].split()) if tr else None,
        **{k: (meta or {}).get(k) for k in (
            "title", "channel", "channel_id", "duration_seconds", "description",
            "category_id", "category_name", "view_count", "like_count",
            "comment_count", "n_chapters", "upload_date", "video_language")},
        "tags": json.dumps(meta.get("tags") or []) if meta else None,
        "chapters": json.dumps(meta.get("chapters") or []) if meta else None,
    }
    with conn.cursor() as cur:
        cur.execute(UPDATE_SQL, payload)
    conn.commit()


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Worker de enriquecimiento local")
    ap.add_argument("--max", type=int, default=None,
                    help="modo worker: procesa N y sale (recomendado: 10)")
    ap.add_argument("--status", action="store_true", help="ver la cola y salir")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only-missing-transcript", action="store_true")
    ap.add_argument("--ids", nargs="*", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep-min", type=float, default=15.0)
    ap.add_argument("--sleep-max", type=float, default=35.0)
    ap.add_argument("--batch", type=int, default=0, help="0 = sin tandas internas")
    ap.add_argument("--batch-pause", type=float, default=900.0)
    ap.add_argument("--proxy", default=None, help="http://user:pass@host:puerto")
    ap.add_argument("--cookies-from-browser", default=None,
                    help="firefox | edge | brave (chrome NO anda en Windows)")
    ap.add_argument("--cookies-file", default=None)
    ap.add_argument("--no-fallback", action="store_true")
    ap.add_argument("--env", default=None)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-7s %(message)s",
                        datefmt="%d/%m %H:%M:%S")

    env_path = Path(args.env) if args.env else Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        log.error("No encuentro DATABASE_URL. Revisá %s", env_path)
        return 1

    conn = psycopg2.connect(dsn)
    conn.autocommit = False

    if args.status:
        print_status(conn)
        conn.close()
        return 0

    items = select_batch(conn, args)
    worker = bool(args.max)
    log.info("Tanda de %d video(s)%s", len(items), " [worker]" if worker else "")
    if not items:
        log.info("Nada pendiente con turno vencido. Nada que hacer.")
        conn.close()
        return 0

    ydl = build_ydl(args.cookies_from_browser, args.cookies_file, args.proxy)
    stats: dict[str, int] = {}
    report: list[dict] = []
    cooldown_idx = 0
    i = 0

    try:
        while i < len(items):
            row = items[i]
            vid = row["external_id"]
            log.info("[%d/%d] %s — %s", i + 1, len(items), vid, (row["title"] or "")[:48])

            try:
                meta, tr, errors = extract(ydl, vid, not args.no_fallback, args.proxy)
            except Blocked as e:
                if worker:
                    st = read_state()
                    n_blocks = int(st.get("consecutive_blocks", 0)) + 1
                    horas = BLOCK_BACKOFF_HOURS[min(n_blocks - 1,
                                                    len(BLOCK_BACKOFF_HOURS) - 1)]
                    write_state({"consecutive_blocks": n_blocks})

                    pendientes = [r["id"] for r in items[i:]]
                    with conn.cursor() as cur:
                        cur.execute(RESCHEDULE_SQL, (f"{horas} hours", pendientes))
                    conn.commit()
                    log.warning("Bloqueado por YouTube (bloqueo consecutivo nº%d).", n_blocks)
                    log.warning("Reprogramo %d video(s) para dentro de %d h y salgo.",
                                len(pendientes), horas)
                    if n_blocks >= 3:
                        log.warning("Tu IP lleva %d corridas bloqueada. Sólo la levanta "
                                    "el tiempo:", n_blocks)
                        log.warning("no corras nada a mano — cada intento extra la alarga.")
                    break
                if cooldown_idx >= len(COOLDOWNS):
                    log.error("Bloqueo persistente: tu IP está en penalización.")
                    log.error("Sólo lo levanta el tiempo. Volvé mañana y relanzá.")
                    break
                wait = COOLDOWNS[cooldown_idx]
                cooldown_idx += 1
                log.warning("Bloqueado. Enfriando %d min (%d/%d): %s",
                            wait // 60, cooldown_idx, len(COOLDOWNS), str(e)[:70])
                time.sleep(wait)
                continue
            except CookieProblem as e:
                log.error("No puedo leer las cookies de '%s': %s",
                          args.cookies_from_browser, str(e)[:120])
                log.error("Corré sin --cookies-from-browser, o usá firefox, o "
                          "exportá un cookies.txt y pasalo con --cookies-file.")
                break

            perm = None if tr else classify_permanent(errors)
            if meta and tr:
                status, cooldown_idx = "ok", 0
                if read_state().get("consecutive_blocks"):
                    write_state({"consecutive_blocks": 0})  # la IP se recuperó
            elif perm:
                status = perm
            elif meta or tr:
                status = "partial"
            else:
                status = "failed"
            stats[status] = stats.get(status, 0) + 1

            if tr:
                log.info("    ✓ %s / %s / %d palabras / %d capítulos",
                         tr["source"], tr["lang"], len(tr["text"].split()),
                         (meta or {}).get("n_chapters") or 0)
            elif perm:
                log.info("    — %s (definitivo, no se reintenta)", perm)
            else:
                log.warning("    ✗ %s", (errors or ["?"])[0][:85])

            report.append({"external_id": vid, "status": status,
                           "transcript_source": tr["source"] if tr else None,
                           "lang": tr["lang"] if tr else None,
                           "words": len(tr["text"].split()) if tr else 0,
                           "n_chapters": (meta or {}).get("n_chapters"),
                           "error": " | ".join(errors) or None})

            if not args.dry_run:
                try:
                    save(conn, row, meta, tr, errors, status)
                except Exception as e:
                    conn.rollback()
                    log.error("    guardado ✗ %s", e)

            i += 1
            if i < len(items):
                if args.batch and i % args.batch == 0:
                    log.info("Pausa de tanda: %.0f min…", args.batch_pause / 60)
                    time.sleep(args.batch_pause)
                else:
                    time.sleep(random.uniform(args.sleep_min, args.sleep_max))

    except KeyboardInterrupt:
        log.warning("Interrumpido. Lo procesado está guardado.")
    finally:
        if report:
            out = Path(__file__).resolve().parent / "enrichment_report.csv"
            nuevo = not out.exists()
            with out.open("a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(report[0].keys()))
                if nuevo:
                    w.writeheader()
                w.writerows(report)
        log.info("Resumen: %s", "  ".join(f"{k}={v}" for k, v in stats.items()) or "—")
        try:
            print_status(conn)
        except Exception:
            pass
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())

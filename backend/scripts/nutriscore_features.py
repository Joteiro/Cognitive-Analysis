#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nutriscore_features.py  -  v2.0 (borrador para compute_features.py)

Calcula, para cada fila de content_items:
  - CAPA 0: validez del dato (qué se puede y qué no se puede medir en esa fila)
  - CAPA 1: los 7 descriptores del panel visible ("etiqueta nutricional")
  - CAPA 2: la tabla ancha de indicadores para el estudio
  - ETIQUETAS: categóricas, 100% deterministas (reglas auditables, sin LLM)
  - DIETA: sólo para el dashboard, a partir de watched_at

No usa view_count / like_count / comment_count por decisión de diseño:
miden al canal y al algoritmo, no al contenido.

Todo indicador va normalizado por 100 palabras o por minuto. Nunca en total.
"""

import re
import json
import math
import unicodedata
import numpy as np
import pandas as pd

# ---------------------------------------------------------------- utilidades

def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")

def norm(s) -> str:
    """minúsculas sin acentos, para matchear léxicos"""
    if not isinstance(s, str):
        return ""
    return strip_accents(s.lower())

WORD_RE = re.compile(r"[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9']+")

def words(text: str):
    return WORD_RE.findall(text or "")

def count_phrases(text_norm: str, phrases) -> int:
    """cuenta ocurrencias de un léxico cerrado, con límite de palabra"""
    n = 0
    for p in phrases:
        n += len(re.findall(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", text_norm))
    return n

# ---------------------------------------------------------------- léxicos ES/EN
# Cerrados y versionados a propósito: cada número del panel tiene que poder
# reproducirse a mano contando en la transcripción.

LEX = {
    "conectores": {  # relación lógica explícita entre ideas
        "es": ["porque", "por lo tanto", "por eso", "sin embargo", "no obstante",
               "en cambio", "ademas", "por ejemplo", "es decir", "en consecuencia",
               "aunque", "mientras que", "de hecho", "asi que", "dado que",
               "debido a", "gracias a", "a pesar de", "en realidad", "o sea"],
        "en": ["because", "therefore", "however", "nevertheless", "instead",
               "for example", "that is", "as a result", "although", "while",
               "in fact", "so that", "due to", "thanks to", "despite", "actually"],
    },
    "atribucion": {  # marca de fuente dentro del habla
        "es": ["segun", "de acuerdo con", "un estudio", "una investigacion",
               "los datos", "la fuente", "las fuentes", "informo", "publico",
               "revelo", "el informe", "la encuesta", "el paper", "los expertos",
               "el investigador", "la investigadora", "la universidad", "citando"],
        "en": ["according to", "a study", "research shows", "the data", "the source",
               "reported", "published", "revealed", "the report", "the survey",
               "the paper", "experts", "researchers", "the university"],
    },
    "matizadores": {  # hedges: marcan incertidumbre declarada
        "es": ["quiza", "quizas", "tal vez", "puede que", "probablemente",
               "parece que", "aproximadamente", "en torno a", "mas o menos",
               "en general", "suele", "podria", "no esta claro", "se estima"],
        "en": ["maybe", "perhaps", "probably", "it seems", "approximately",
               "around", "roughly", "generally", "might", "unclear", "estimated"],
    },
    "absolutos": {  # afirmación sin matiz
        "es": ["siempre", "nunca", "jamas", "todos", "nadie", "nada", "obviamente",
               "claramente", "sin duda", "absolutamente", "definitivamente",
               "el mejor", "el peor", "increible", "brutal", "tremendo"],
        "en": ["always", "never", "everyone", "nobody", "obviously", "clearly",
               "no doubt", "absolutely", "definitely", "the best", "the worst",
               "incredible", "insane", "crazy"],
    },
    # OJO: sin ordinales sueltos ("primero", "segundo"). En el corpus de fútbol
    # "el segundo" = el segundo gol y "primer tiempo" dispararon el indicador:
    # los highlights encabezaban el ranking de "estructura". Sólo multipalabra.
    "estructura": {  # metadiscurso: el hablante señala el mapa del contenido
        "es": ["en primer lugar", "en segundo lugar", "en tercer lugar", "por ultimo",
               "para terminar", "en resumen", "resumiendo", "vamos a ver",
               "empecemos por", "por otro lado", "a continuacion", "el siguiente punto",
               "recapitulando", "para cerrar", "en conclusion", "antes que nada",
               "el primer punto", "lo primero que", "lo ultimo que", "para empezar"],
        "en": ["first of all", "secondly", "thirdly", "finally", "to sum up",
               "in summary", "let's see", "let's start", "on the other hand",
               "next up", "the next point", "to recap", "in conclusion",
               "the first point", "the first thing", "to begin with"],
    },
    "cta": {  # llamadas a la acción / optimización de canal
        "es": ["suscrib", "suscribete", "campanita", "dale like", "dejame un like",
               "un like", "comenta", "comentarios", "activa las notificaciones",
               "link en la descripcion", "enlace en la descripcion", "hazte miembro",
               "miembro del canal", "patreon", "apoya el canal", "compartilo",
               "compartelo", "no te olvides de", "sigueme en"],
        "en": ["subscribe", "hit the bell", "like this video", "leave a like",
               "comment below", "turn on notifications", "link in the description",
               "become a member", "channel member", "patreon", "support the channel",
               "share this", "don't forget to", "follow me on"],
    },
    "patrocinio": {
        "es": ["patrocina", "patrocinado", "este video es posible gracias a",
               "codigo de descuento", "cupon", "publicidad", "anunciante",
               "usa mi codigo", "link de afiliado", "gracias a nuestro"],
        "en": ["sponsor", "sponsored by", "this video is brought to you by",
               "discount code", "coupon", "promo code", "affiliate link",
               "use my code", "thanks to our"],
    },
    "muletillas": {
        "es": ["este", "eh", "em", "o sea", "digamos", "viste", "bueno", "nada",
               "tipo", "obvio", "che"],
        "en": ["um", "uh", "like", "you know", "i mean", "basically", "right"],
    },
    "anticipacion": {  # ganchos de retención: promete algo para después
        "es": ["mas adelante", "al final del video", "ya te voy a contar",
               "espera", "esperen", "quedate hasta el final", "en un momento",
               "ahora vas a ver", "lo mejor viene", "no te vayas"],
        "en": ["later in this video", "at the end of the video", "stay till the end",
               "in a moment", "wait for it", "you'll see", "don't go anywhere"],
    },
}

STOP = {
    "es": set("""de la que el en y a los del se las por un para con no una su al lo como mas
                pero sus le ya o este si porque esta entre cuando muy sin sobre tambien me hasta
                donde quien desde todo nos durante todos uno les ni contra otros ese eso ante
                ellos e esto mi antes algunos que unos yo otro otras otra el tanto esa estos
                mucho quienes nada muchos cual poco ella estar estas algunas algo nosotros mi
                mis tu te ti tus ellas nosotras vosotros vosotras os mio mia mios mias tuyo
                tuya tuyos tuyas suyo suya suyos suyas nuestro nuestra nuestros nuestras
                vuestro vuestra vuestros vuestras esos esas es son ser fue han hay va vamos
                asi bien aqui ahi alla entonces hace hacer tiene tienen tener puede pueden
                dice decir dos tres""".split()),
    "en": set("""the of and to a in is it you that he was for on are with as i his they be at
                one have this from or had by hot but some what there we can out other were all
                your when up use word how said an each she which do their time if will way
                about many then them would write like so these her long make thing see him two
                has look more day could go come did no most my over know than call first who
                its now find down been made may part""".split()),
}

# unidades y marcas de cantidad verificable
NUM_TOKEN = re.compile(r"(?<![a-z])\d[\d.,]*(?![a-z])")
YEAR = re.compile(r"\b(1[6-9]\d{2}|20[0-4]\d)\b")
PCT = re.compile(r"(\d+\s*%|\bpor\s?ciento\b|\bpercent\b)")
UNITS = ["km", "kg", "mts", "metros", "kilometros", "kilos", "toneladas", "litros",
         "euros", "dolares", "pesos", "millones", "miles", "billones", "hectareas",
         "grados", "horas", "minutos", "segundos", "anos", "siglos", "habitantes",
         "miles de millones", "millon", "puntos", "goles"]
NUM_WORDS = ["cero", "uno", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete",
             "ocho", "nueve", "diez", "once", "doce", "trece", "catorce", "quince",
             "veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta",
             "ochenta", "noventa", "cien", "ciento", "mil", "millon", "millones",
             "mitad", "doble", "triple", "tercio", "porcentaje"]

SOCIAL_DOMAINS = re.compile(
    r"(youtube\.com|youtu\.be|instagram\.com|twitter\.com|x\.com|facebook\.com|"
    r"tiktok\.com|patreon\.com|discord\.|twitch\.tv|open\.spotify\.com|"
    r"linktr\.ee|t\.me|threads\.net|linkedin\.com/in|bit\.ly)", re.I)

TRACEABLE_DOMAINS = re.compile(
    r"(\.gov|\.edu|\.ac\.|\.org|doi\.org|arxiv\.org|nature\.com|science\.org|"
    r"pubmed|ncbi\.nlm|who\.int|un\.org|worldbank|ine\.es|indec\.gob|eurostat|"
    r"scholar\.google|jstor|springer|elsevier|wikipedia\.org|reuters\.com|"
    r"apnews\.com|bbc\.co|nytimes\.com|elpais\.com|ft\.com)", re.I)

URL_RE = re.compile(r"https?://[^\s<>\"')]+")
TS_RE = re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\b")  # marcas de tiempo en descripción

# marcas de contenido perecedero en título/tags
PERECEDERO = ["hoy", "ayer", "ultima hora", "en vivo", "directo", "jornada",
              "fecha", "resumen", "highlights", "goles", "vs", "final",
              "semifinal", "cuartos", "clasificacion", "programa", "episodio",
              "noticias", "breaking", "live", "recap", "matchday", "week",
              "2020", "2021", "2022", "2023", "2024", "2025", "2026"]

CLICKBAIT_SUPERLATIVOS = ["increible", "brutal", "impactante", "no vas a creer",
                          "lo que nadie", "la verdad sobre", "por fin", "shock",
                          "escandalo", "el mejor", "el peor", "urgente", "insolito",
                          "asi fue", "esto cambia todo", "nadie te dice",
                          "shocking", "you won't believe", "the truth about",
                          "insane", "gone wrong", "exposed"]


# ---------------------------------------------------------------- CAPA 0: validez

SENT_END = re.compile(r"[.!?…]")

def capa0_validez(row, toks):
    """Qué se puede medir en esta fila. Sin esto, el resto miente."""
    out = {}
    txt = row.get("transcript")
    txt = txt if isinstance(txt, str) else ""
    n_w = len(toks)
    dur_min = (row.get("duration_seconds") or np.nan) / 60.0

    out["v_tiene_transcripcion"] = int(n_w > 0)
    out["v_fuente_transcripcion"] = row.get("transcript_source") or "ninguna"
    out["v_transcripcion_auto"] = int(bool(row.get("transcript_is_generated")))

    # ¿hay puntuación real o la insertó (o no) el ASR?
    n_sent = len(SENT_END.findall(txt))
    out["v_palabras_por_signo"] = round(n_w / n_sent, 1) if n_sent else np.nan
    out["v_tiene_puntuacion"] = int(bool(n_sent) and (n_w / max(n_sent, 1)) < 60)

    # ¿la transcripción cubre el video o está truncada?
    # 150 wpm es el habla castellana media; <0,55 de lo esperado = sospechosa
    if n_w and dur_min and dur_min > 0:
        esperado = dur_min * 150
        out["v_cobertura_transcripcion"] = round(n_w / esperado, 2)
        out["v_transcripcion_completa"] = int(0.45 <= n_w / esperado <= 1.6)
    else:
        out["v_cobertura_transcripcion"] = np.nan
        out["v_transcripcion_completa"] = 0

    out["v_tiene_metadatos"] = int(pd.notna(row.get("category_id")))
    out["v_tiene_descripcion"] = int(bool((row.get("description") or "").strip()))
    out["v_apto_panel"] = int(out["v_tiene_transcripcion"] and
                              out["v_transcripcion_completa"] and
                              out["v_tiene_metadatos"])
    return out


# ---------------------------------------------------------------- CAPA 1+2: indicadores

def mattr(tokens, window=200):
    """Diversidad léxica insensible a la longitud (media móvil de TTR)."""
    n = len(tokens)
    if n == 0:
        return np.nan
    if n < window:
        return len(set(tokens)) / n
    vals = []
    for i in range(0, n - window + 1, max(1, window // 4)):
        w = tokens[i:i + window]
        vals.append(len(set(w)) / window)
    return float(np.mean(vals))


def lex_rate(text_norm, key, lang, n_w, per=1000):
    langs = ["es", "en"] if lang not in ("es", "en") else [lang]
    c = sum(count_phrases(text_norm, LEX[key][l]) for l in langs)
    return (c / n_w * per) if n_w else np.nan


def indicadores(row, toks, tnorm, lang, val):
    out = {}
    n_w = len(toks)
    dur_min = (row.get("duration_seconds") or np.nan) / 60.0
    per10 = (dur_min / 10.0) if dur_min and dur_min > 0 else np.nan

    # --- forma del habla -------------------------------------------------
    out["ritmo_ppm"] = round(n_w / dur_min, 1) if (n_w and dur_min) else np.nan

    # variabilidad del ritmo, desde transcript_segments (bins de 30 s)
    out["ritmo_cv"] = np.nan
    out["p_tramo_silencioso"] = np.nan
    segs = row.get("transcript_segments")
    if isinstance(segs, str) and segs.strip().startswith("["):
        try:
            S = json.loads(segs)
            if S and dur_min and dur_min > 0:
                bins = {}
                for s in S:
                    b = int(float(s.get("start", 0)) // 30)
                    bins[b] = bins.get(b, 0) + len(words(s.get("text", "")))
                total_bins = max(1, int(math.ceil(dur_min * 60 / 30)))
                serie = np.array([bins.get(b, 0) for b in range(total_bins)], float)
                if serie.mean() > 0:
                    out["ritmo_cv"] = round(float(serie.std() / serie.mean()), 3)
                    out["p_tramo_silencioso"] = round(
                        float((serie < 0.4 * serie.mean()).mean()), 3)
        except Exception:
            pass

    # sólo con puntuación real
    if val["v_tiene_puntuacion"]:
        n_sent = len(SENT_END.findall(row.get("transcript") or ""))
        out["palabras_por_frase"] = round(n_w / n_sent, 1) if n_sent else np.nan
        out["preguntas_1000w"] = round(
            (row.get("transcript") or "").count("?") / n_w * 1000, 2) if n_w else np.nan
    else:
        out["palabras_por_frase"] = np.nan
        out["preguntas_1000w"] = np.nan

    # --- léxico ----------------------------------------------------------
    out["mattr_200"] = round(mattr(toks, 200), 4) if n_w else np.nan
    stop = STOP.get(lang, STOP["es"]) | STOP["en"]
    content = [t for t in toks if t not in stop and not t.isdigit()]
    out["p_palabras_contenido"] = round(len(content) / n_w, 3) if n_w else np.nan
    out["hapax_ratio"] = np.nan   # DESCARTADO del panel: corr -0,82 con log(duración)
    if content:
        from collections import Counter
        c = Counter(content)
        out["hapax_ratio"] = round(sum(1 for v in c.values() if v == 1) / len(c), 3)
    out["long_media_palabra"] = round(np.mean([len(t) for t in toks]), 2) if n_w else np.nan
    out["muletillas_1000w"] = round(lex_rate(tnorm, "muletillas", lang, n_w), 2)

    # --- evidencia / densidad de datos -----------------------------------
    n_num = len(NUM_TOKEN.findall(tnorm)) + count_phrases(tnorm, NUM_WORDS)
    out["cifras_100w"] = round(n_num / n_w * 100, 2) if n_w else np.nan
    out["anios_1000w"] = round(len(YEAR.findall(tnorm)) / n_w * 1000, 2) if n_w else np.nan
    out["porcentajes_1000w"] = round(len(PCT.findall(tnorm)) / n_w * 1000, 2) if n_w else np.nan
    out["unidades_1000w"] = round(count_phrases(tnorm, UNITS) / n_w * 1000, 2) if n_w else np.nan
    out["atribucion_1000w"] = round(lex_rate(tnorm, "atribucion", lang, n_w), 2)

    # --- razonamiento / carga cognitiva ----------------------------------
    out["conectores_1000w"] = round(lex_rate(tnorm, "conectores", lang, n_w), 2)
    out["matizadores_1000w"] = round(lex_rate(tnorm, "matizadores", lang, n_w), 2)
    out["absolutos_1000w"] = round(lex_rate(tnorm, "absolutos", lang, n_w), 2)
    m, a = out["matizadores_1000w"], out["absolutos_1000w"]
    out["ratio_matiz_absoluto"] = round((m + 0.5) / (a + 0.5), 3) if pd.notna(m) and pd.notna(a) else np.nan

    # --- estructura -------------------------------------------------------
    out["marcadores_estructura_1000w"] = round(lex_rate(tnorm, "estructura", lang, n_w), 2)
    nch = row.get("n_chapters")
    out["capitulos_10min"] = round(nch / per10, 2) if (pd.notna(nch) and pd.notna(per10) and per10 > 0) else np.nan
    out["tiene_indice"] = int(pd.notna(nch) and nch >= 2)

    # --- optimización para retención ("azúcares añadidos") ----------------
    cta = lex_rate(tnorm, "cta", lang, n_w, per=1000)
    pat = lex_rate(tnorm, "patrocinio", lang, n_w, per=1000)
    ant = lex_rate(tnorm, "anticipacion", lang, n_w, per=1000)
    out["cta_1000w"] = round(cta, 2)
    out["patrocinio_1000w"] = round(pat, 2)
    out["anticipacion_1000w"] = round(ant, 2)
    out["promocional_1000w"] = round(cta + pat, 2) if pd.notna(cta) else np.nan

    # --- trazabilidad (descripción) ---------------------------------------
    desc = row.get("description") or ""
    urls = URL_RE.findall(desc)
    ext = [u for u in urls if not SOCIAL_DOMAINS.search(u)]
    trace = [u for u in urls if TRACEABLE_DOMAINS.search(u)]
    # NO se normalizan por duración: la descripción es un artefacto fijo, no un flujo.
    # Dividir por minutos metía la inversa de la duración dentro del indicador
    # (corr -0,68 con log(duración) en la v1; en absoluto baja a -0,05).
    out["enlaces_total"] = len(urls)
    out["enlaces_externos"] = len(ext)
    out["enlaces_fuente"] = len(trace)
    out["tiene_fuentes_externas"] = int(len(ext) > 0)
    out["desc_caracteres"] = len(desc)
    out["desc_timestamps"] = len(TS_RE.findall(desc))

    # --- correspondencia promesa ↔ contenido -------------------------------
    title_n = norm(row.get("title") or "")
    tkeys = [t for t in words(title_n) if t not in stop and len(t) > 3]
    out["titulo_palabras_clave"] = len(tkeys)
    out["cobertura_titulo"] = np.nan
    out["foco_promesa"] = np.nan
    if tkeys and toks:
        presentes = sum(1 for k in set(tkeys) if k in set(toks))
        out["cobertura_titulo"] = round(presentes / len(set(tkeys)), 3)
        pos = [i for i, t in enumerate(toks) if t in set(tkeys)]
        if pos:
            out["foco_promesa"] = round(pos[0] / len(toks), 3)  # 0 = arranca por el tema
            out["densidad_tema_100w"] = round(len(pos) / len(toks) * 100, 2)
    out.setdefault("densidad_tema_100w", np.nan)

    # tags como segunda promesa
    try:
        tg = json.loads(row.get("tags")) if isinstance(row.get("tags"), str) else []
    except Exception:
        tg = []
    out["n_tags"] = len(tg) if isinstance(tg, list) else 0

    # --- señales del título (banderas, no juicio) --------------------------
    title_raw = row.get("title") or ""
    letras = [c for c in title_raw if c.isalpha()]
    out["titulo_p_mayusculas"] = round(sum(c.isupper() for c in letras) / len(letras), 3) if letras else np.nan
    out["titulo_exclamaciones"] = title_raw.count("!") + title_raw.count("¡")
    out["titulo_es_pregunta"] = int("?" in title_raw or "¿" in title_raw)
    out["titulo_superlativos"] = count_phrases(norm(title_raw), CLICKBAIT_SUPERLATIVOS)
    out["titulo_numero_lista"] = int(bool(re.match(r"^\s*(top\s*)?\d{1,2}\b", title_n)))
    out["titulo_banderas"] = (int(out["titulo_p_mayusculas"] > 0.5 if pd.notna(out["titulo_p_mayusculas"]) else 0)
                              + int(out["titulo_exclamaciones"] > 0)
                              + int(out["titulo_superlativos"] > 0))
    return out


# ---------------------------------------------------------------- ETIQUETAS (reglas)

def etiquetas(row, ind, val, lang):
    e = {}
    dur = row.get("duration_seconds")
    dur_min = dur / 60.0 if pd.notna(dur) else np.nan
    title_n = norm(row.get("title") or "")
    try:
        tags = json.loads(row.get("tags")) if isinstance(row.get("tags"), str) else []
    except Exception:
        tags = []
    tags_n = " ".join(norm(t) for t in tags) if isinstance(tags, list) else ""
    cat = row.get("category_name") or "sin_categoria"
    blob = f"{title_n} {tags_n}"

    # 1. formato por duración (la "porción")
    if pd.isna(dur_min):
        e["et_porcion"] = "desconocida"
    elif dur_min <= 1:
        e["et_porcion"] = "short"
    elif dur_min <= 10:
        e["et_porcion"] = "corto"
    elif dur_min <= 30:
        e["et_porcion"] = "medio"
    elif dur_min <= 60:
        e["et_porcion"] = "largo"
    else:
        e["et_porcion"] = "muy_largo"

    # 2. formato editorial (reglas ordenadas; la primera que matchea gana)
    def has(*ws):
        return any(w in blob for w in ws)

    if has("podcast", "entrevista", "episodio", "charla con", "mano a mano") or \
       (pd.notna(dur_min) and dur_min > 45 and (row.get("n_chapters") or 0) >= 3):
        f = "conversacion_larga"
    elif has("resumen", "highlights", "goles", "compacto", "recap", "lo mejor de"):
        f = "resumen_evento"
    elif re.match(r"^\s*(como|how to|tutorial|guia|aprende|paso a paso)", title_n):
        f = "instructivo"
    elif ind.get("titulo_numero_lista") or has("top ", "ranking", "mejores", "peores"):
        f = "lista_ranking"
    elif has("en vivo", "directo", "live", "stream"):
        f = "directo"
    elif has("analisis", "explicado", "por que", "que paso", "la historia de"):
        f = "explicativo"
    elif has("review", "reseña", "opinion", "critica", "reacciono", "reaccion"):
        f = "opinion_review"
    elif cat in ("News & Politics",):
        f = "actualidad"
    elif cat in ("Education", "Science & Technology"):
        f = "divulgacion"
    else:
        f = "sin_clasificar"
    e["et_formato"] = f

    # 3. caducidad: ¿el contenido pierde validez con el tiempo?
    e["et_caducidad"] = "perecedero" if count_phrases(blob, PERECEDERO) > 0 else "perenne"

    # 4. tipo de promesa del título
    if row.get("title") and ("?" in row["title"] or "¿" in row["title"]):
        e["et_promesa"] = "pregunta"
    elif ind.get("titulo_numero_lista"):
        e["et_promesa"] = "lista"
    elif re.match(r"^\s*(como|no |deja|mira|aprende|descubre|how|stop|watch)", title_n):
        e["et_promesa"] = "imperativa"
    else:
        e["et_promesa"] = "declarativa"

    # 5. trazabilidad declarada
    if ind.get("enlaces_fuente", 0) and ind["enlaces_fuente"] > 0:
        e["et_trazabilidad"] = "con_fuentes_verificables"
    elif ind.get("tiene_fuentes_externas"):
        e["et_trazabilidad"] = "con_enlaces_externos"
    elif ind.get("enlaces_total", 0) > 0:
        e["et_trazabilidad"] = "solo_enlaces_propios"
    else:
        e["et_trazabilidad"] = "sin_enlaces"

    # 6. navegabilidad
    nch = row.get("n_chapters")
    if pd.notna(nch) and nch >= 2:
        e["et_navegabilidad"] = "con_indice"
    elif ind.get("desc_timestamps", 0) >= 2:
        e["et_navegabilidad"] = "timestamps_en_descripcion"
    else:
        e["et_navegabilidad"] = "bloque_continuo"

    # 7. calidad del dato (gate del panel)
    if not val["v_tiene_transcripcion"]:
        e["et_calidad_dato"] = "sin_transcripcion"
    elif not val["v_transcripcion_completa"]:
        e["et_calidad_dato"] = "transcripcion_parcial"
    elif val["v_transcripcion_auto"]:
        e["et_calidad_dato"] = "transcripcion_automatica"
    else:
        e["et_calidad_dato"] = "transcripcion_humana"

    e["et_idioma"] = lang
    e["et_categoria_yt"] = cat
    return e


# ---------------------------------------------------------------- tercios del corpus

def tercios(serie: pd.Series, invertir=False):
    """Nivel bajo/medio/alto = tercios del propio corpus. Relativo, hay que declararlo."""
    s = pd.to_numeric(serie, errors="coerce")
    if s.notna().sum() < 9 or s.nunique() < 3:
        return pd.Series(["insuficiente"] * len(s), index=s.index)
    q1, q2 = s.quantile(1/3), s.quantile(2/3)
    lab = pd.Series(np.where(s <= q1, "bajo", np.where(s <= q2, "medio", "alto")),
                    index=s.index, dtype=object)
    lab[s.isna()] = "sin_dato"
    if invertir:
        lab = lab.replace({"bajo": "alto", "alto": "bajo"})
    return lab


# ---------------------------------------------------------------- DIETA (dashboard)

def dieta(df):
    d = df.copy()
    d["watched_at"] = pd.to_datetime(d["watched_at"], errors="coerce", utc=True)
    d["upload_date"] = pd.to_datetime(d["upload_date"], errors="coerce", utc=True)
    d = d.sort_values("watched_at")
    d["dieta_edad_al_ver_dias"] = (d["watched_at"] - d["upload_date"]).dt.days
    d["dieta_hora_local"] = d["watched_at"].dt.tz_convert("Europe/Paris").dt.hour
    d["dieta_dia"] = d["watched_at"].dt.tz_convert("Europe/Paris").dt.date
    d["dieta_gap_min"] = d["watched_at"].diff().dt.total_seconds() / 60
    d["dieta_en_rafaga"] = (d["dieta_gap_min"] < 30).astype(int)
    d["dieta_minutos"] = d["duration_seconds"] / 60
    return d[["id", "dieta_edad_al_ver_dias", "dieta_hora_local", "dieta_dia",
              "dieta_gap_min", "dieta_en_rafaga", "dieta_minutos"]]


# ---------------------------------------------------------------- main

def build(csv_path):
    df = pd.read_csv(csv_path)
    filas = []
    for _, row in df.iterrows():
        r = row.to_dict()
        for c in ("transcript", "description", "title", "tags", "transcript_segments",
                  "chapters", "transcript_source", "category_name", "video_language",
                  "transcript_lang", "channel"):
            if not isinstance(r.get(c), str):
                r[c] = ""
        tnorm = norm(r.get("transcript") or "")
        toks = words(tnorm)
        lang = (r.get("video_language") or r.get("transcript_lang") or "es")
        lang = "en" if str(lang).startswith("en") else "es"
        val = capa0_validez(r, toks)
        ind = indicadores(r, toks, tnorm, lang, val)
        eti = etiquetas(r, ind, val, lang)
        filas.append({"id": r["id"], "title": r["title"], "channel": r["channel"],
                      "duration_seconds": r.get("duration_seconds"),
                      **val, **ind, **eti})
    F = pd.DataFrame(filas)

    # niveles relativos del panel (tercios del corpus, sólo filas aptas)
    panel = {
        "ritmo_ppm": False,
        "cifras_100w": False,
        "atribucion_1000w": False,
        "mattr_200": False,
        "conectores_1000w": False,
        "enlaces_externos": False,
        "promocional_1000w": False,
        "cobertura_titulo": False,
    }
    apt = F["v_apto_panel"] == 1
    for col, inv in panel.items():
        F[f"nivel_{col}"] = "sin_dato"
        F.loc[apt, f"nivel_{col}"] = tercios(F.loc[apt, col], invertir=inv)

    F = F.merge(dieta(df), on="id", how="left")
    return df, F


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "content_items_rows.csv"
    raw, F = build(src)
    F.to_csv("content_features_draft.csv", index=False)
    print(f"OK -> content_features_draft.csv  ({F.shape[0]} filas, {F.shape[1]} columnas)")

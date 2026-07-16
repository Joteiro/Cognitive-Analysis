# app/scorer.py
"""
Nutri-Score rule-based scorer.
Calcula un score A-E para videos de YouTube usando señales de titulo,
duracion, transcript, categoría, engagement y descripción.
Sin dependencias de LLM — 100% local + YouTube Data API.
"""
import re
from typing import Optional

try:
    import textstat
    TEXTSTAT_AVAILABLE = True
except ImportError:
    TEXTSTAT_AVAILABLE = False


# ─── VERSIÓN DEL ALGORITMO ────────────────────────────────────────────────────
# Subí esto cada vez que cambies pesos, señales o umbrales. Cada score se guarda
# etiquetado con su versión → podés re-scorear el historial y comparar versiones.
# Convención: MAYOR.menor  (MAYOR = cambio que altera resultados de forma notable)
SCORER_VERSION = "1.0"


# ─── PESOS DE CADA SEÑAL (deben sumar 1.0) ────────────────────────────────────
WEIGHTS = {
    "title":             0.15,
    "duration":          0.08,
    "lexical_richness":  0.15,
    "data_density":      0.15,
    "source_presence":   0.10,
    "readability":       0.04,
    "repetition":        0.08,
    # YouTube API signals
    "category":          0.10,
    "engagement":        0.05,
    "description":       0.10,
}
# Total: 1.00


# ─── PALABRAS EMOCIONALES / CLICKBAIT ─────────────────────────────────────────
EMOTIONAL_WORDS = {
    "increíble", "impactante", "sorprendente", "shocking", "amazing",
    "brutal", "épico", "viral", "secreto", "verdad", "jamás", "nunca",
    "terrible", "horrible", "wow", "crazy", "insane", "urgente", "alerta",
    "exclusivo", "escándalo", "trampa", "engaño", "revelación", "peligro",
    "gratis", "hack", "truco", "fácil", "rápido", "simple"
}

SOURCE_WORDS = {
    "según", "estudio", "investigación", "fuente", "paper", "research",
    "evidencia", "datos", "estadística", "encuesta", "informe", "journal",
    "universidad", "científico", "according", "study", "evidence",
    "publicó", "reportó", "demostró", "análisis", "hallazgo"
}

# Categorías de YouTube con score cognitivo asignado (categoryId → 0-1)
CATEGORY_SCORES = {
    "27": 0.95,   # Education
    "28": 0.90,   # Science & Technology
    "25": 0.80,   # News & Politics
    "26": 0.70,   # Howto & Style
    "29": 0.65,   # Nonprofits & Activism
    "22": 0.50,   # People & Blogs
    "23": 0.45,   # Comedy
    "24": 0.40,   # Entertainment
    "1":  0.40,   # Film & Animation
    "17": 0.45,   # Sports
    "20": 0.35,   # Gaming
    "10": 0.40,   # Music
    "19": 0.45,   # Travel & Events
    "15": 0.35,   # Pets & Animals
    "2":  0.35,   # Autos & Vehicles
}


# ─── SEÑALES INDIVIDUALES ─────────────────────────────────────────────────────

def score_title(title: str) -> tuple[float, dict]:
    """Detecta clickbait y carga emocional en el título. 0-1 (1=mejor)."""
    if not title:
        return 0.5, {}

    caps_ratio = sum(1 for c in title if c.isupper()) / max(len(title), 1)
    exclamations = title.count("!")
    questions = title.count("?")
    has_listicle = bool(re.search(r"\b\d+\b", title))
    title_lower = title.lower()
    emotional_hits = sum(1 for w in EMOTIONAL_WORDS if w in title_lower)

    penalty = (
        caps_ratio * 0.3 +
        min(exclamations, 3) * 0.10 +
        min(emotional_hits, 4) * 0.10
    )
    raw = max(0.0, 1.0 - penalty)

    details = {
        "caps_ratio": round(caps_ratio, 2),
        "exclamations": exclamations,
        "questions": questions,
        "has_listicle": has_listicle,
        "emotional_words": emotional_hits,
    }
    return round(raw, 3), details


def score_duration(duration_seconds: Optional[int]) -> tuple[float, dict]:
    """Duración larga → mayor potencial cognitivo. 0-1."""
    if not duration_seconds:
        return 0.5, {"format": "unknown"}

    if duration_seconds < 60:
        return 0.10, {"format": "short"}
    elif duration_seconds < 180:
        return 0.30, {"format": "very_short"}
    elif duration_seconds < 600:
        return 0.55, {"format": "medium"}
    elif duration_seconds < 1800:
        return 0.80, {"format": "long"}
    else:
        return 0.95, {"format": "very_long"}


def score_lexical_richness(text: str) -> tuple[float, dict]:
    """Ratio palabras únicas / total. Más variedad léxica → mejor. 0-1."""
    words = re.findall(r"\b\w+\b", text.lower())
    if len(words) < 200:
        return 0.5, {"reason": "transcript_too_short_for_reliable_lex"}

    ratio = len(set(words)) / len(words)
    normalized = min((ratio - 0.2) / 0.5, 1.0)
    normalized = max(normalized, 0.0)
    return round(normalized, 3), {"unique_ratio": round(ratio, 3), "total_words": len(words)}


def score_data_density(text: str) -> tuple[float, dict]:
    """Presencia de números, porcentajes y cifras. 0-1."""
    words = re.findall(r"\b\w+\b", text)
    if not words:
        return 0.0, {}

    numbers = re.findall(r"\b\d+[.,]?\d*\s*%?\b", text)
    density = len(numbers) / (len(words) / 100)
    normalized = min(density / 5.0, 1.0)
    return round(normalized, 3), {"numbers_found": len(numbers), "density_per_100w": round(density, 2)}


def score_source_presence(text: str) -> tuple[float, dict]:
    """Detección de referencias a fuentes primarias. 0-1."""
    text_lower = text.lower()
    hits = {w for w in SOURCE_WORDS if w in text_lower}
    normalized = min(len(hits) / 5.0, 1.0)
    return round(normalized, 3), {"source_words_found": sorted(hits)}


def score_readability(text: str) -> tuple[float, dict]:
    """Complejidad sintáctica óptima (ni muy simple ni muy compleja). 0-1."""
    if not TEXTSTAT_AVAILABLE or len(text.split()) < 50:
        return 0.5, {"reason": "textstat_unavailable_or_short"}

    try:
        flesch = textstat.flesch_reading_ease(text)
        if 30 <= flesch <= 60:
            score = 1.0
        elif flesch < 10:
            score = 0.5
        elif flesch < 30:
            score = 0.75
        elif flesch < 80:
            score = 0.65
        else:
            score = 0.3
        return round(score, 3), {"flesch_score": round(flesch, 1)}
    except Exception:
        return 0.5, {"reason": "textstat_error"}


def score_repetition(text: str) -> tuple[float, dict]:
    """Ratio de bigramas únicos. Menos repetición → más contenido nuevo. 0-1."""
    words = re.findall(r"\b\w+\b", text.lower())
    if len(words) < 20:
        return 0.5, {}

    bigrams = [f"{words[i]}_{words[i+1]}" for i in range(len(words) - 1)]
    unique_ratio = len(set(bigrams)) / len(bigrams)
    return round(unique_ratio, 3), {"unique_bigram_ratio": round(unique_ratio, 3)}


# ─── SEÑALES DE YOUTUBE DATA API ──────────────────────────────────────────────

def score_category(category_id: Optional[str]) -> tuple[float, dict]:
    """
    Categoría de YouTube como proxy del valor educativo esperado.
    0-1 (1=más cognitivo).
    """
    if not category_id:
        return 0.5, {"reason": "no_category"}

    score = CATEGORY_SCORES.get(str(category_id), 0.5)
    return round(score, 3), {"category_id": category_id}


def score_engagement(
    view_count: Optional[int],
    like_count: Optional[int],
    comment_count: Optional[int],
) -> tuple[float, dict]:
    """
    Ratio like/view como señal de calidad percibida por la audiencia.
    Ratio comment/view como proxy de contenido que genera reflexión.
    0-1.
    """
    if not view_count or view_count < 100:
        return 0.5, {"reason": "insufficient_views"}

    like_ratio    = (like_count or 0) / view_count
    comment_ratio = (comment_count or 0) / view_count

    if like_ratio >= 0.05:
        like_score = 1.0
    elif like_ratio >= 0.03:
        like_score = 0.8
    elif like_ratio >= 0.01:
        like_score = 0.6
    elif like_ratio >= 0.005:
        like_score = 0.45
    else:
        like_score = 0.3

    if comment_ratio >= 0.005:
        comment_score = 1.0
    elif comment_ratio >= 0.002:
        comment_score = 0.7
    elif comment_ratio >= 0.001:
        comment_score = 0.5
    else:
        comment_score = 0.3

    combined = like_score * 0.6 + comment_score * 0.4
    return round(combined, 3), {
        "like_ratio":    round(like_ratio, 4),
        "comment_ratio": round(comment_ratio, 4),
        "like_score":    round(like_score, 3),
        "comment_score": round(comment_score, 3),
    }


def score_description_quality(description: Optional[str]) -> tuple[float, dict]:
    """
    Calidad de la descripción: longitud, presencia de fuentes y links.
    Descripción rica → creador que documenta su contenido. 0-1.
    """
    if not description or len(description.strip()) < 20:
        return 0.2, {"reason": "empty_or_minimal_description"}

    words = description.split()
    word_count = len(words)
    has_links = bool(re.search(r"https?://", description))
    desc_lower = description.lower()
    source_hits = sum(1 for w in SOURCE_WORDS if w in desc_lower)

    if word_count >= 200:
        length_score = 1.0
    elif word_count >= 100:
        length_score = 0.75
    elif word_count >= 50:
        length_score = 0.55
    else:
        length_score = 0.35

    bonus = 0.0
    if has_links:
        bonus += 0.15
    bonus += min(source_hits / 3.0, 1.0) * 0.10

    final = min(length_score + bonus, 1.0)
    return round(final, 3), {
        "word_count":  word_count,
        "has_links":   has_links,
        "source_hits": source_hits,
    }


# ─── SCORE COMPUESTO ──────────────────────────────────────────────────────────

def compute_score(
    title: str,
    duration_seconds: Optional[int],
    transcript: Optional[str],
    # YouTube API fields (opcionales — degradan gracefully a 0.5)
    category_id: Optional[str] = None,
    view_count: Optional[int] = None,
    like_count: Optional[int] = None,
    comment_count: Optional[int] = None,
    description: Optional[str] = None,
) -> dict:
    """
    Calcula el score completo. Devuelve:
      - letter: A/B/C/D/E
      - numeric: 0-100
      - labels: lista de etiquetas descriptivas
      - details: breakdown completo de señales
    """
    transcript_text = transcript or ""
    has_transcript = len(transcript_text.split()) >= 50

    # ── Señales de transcript ──────────────────────────────────────────────────
    title_score,    title_det    = score_title(title)
    duration_score, duration_det = score_duration(duration_seconds)

    if has_transcript:
        lexical_score,  lexical_det  = score_lexical_richness(transcript_text)
        data_score,     data_det     = score_data_density(transcript_text)
        source_score,   source_det   = score_source_presence(transcript_text)
        readability_sc, readab_det   = score_readability(transcript_text)
        repetition_sc,  repetit_det  = score_repetition(transcript_text)
    else:
        lexical_score  = 0.5; lexical_det  = {"reason": "no_transcript"}
        data_score     = 0.5; data_det     = {"reason": "no_transcript"}
        source_score   = 0.5; source_det   = {"reason": "no_transcript"}
        readability_sc = 0.5; readab_det   = {"reason": "no_transcript"}
        repetition_sc  = 0.5; repetit_det  = {"reason": "no_transcript"}

    # ── Señales de YouTube API ─────────────────────────────────────────────────
    category_sc,   category_det = score_category(category_id)
    engagement_sc, engage_det   = score_engagement(view_count, like_count, comment_count)
    desc_sc,       desc_det     = score_description_quality(description)

    # ── Score ponderado ────────────────────────────────────────────────────────
    numeric = (
        title_score    * WEIGHTS["title"]            +
        duration_score * WEIGHTS["duration"]         +
        lexical_score  * WEIGHTS["lexical_richness"] +
        data_score     * WEIGHTS["data_density"]     +
        source_score   * WEIGHTS["source_presence"]  +
        readability_sc * WEIGHTS["readability"]      +
        repetition_sc  * WEIGHTS["repetition"]       +
        category_sc    * WEIGHTS["category"]         +
        engagement_sc  * WEIGHTS["engagement"]       +
        desc_sc        * WEIGHTS["description"]
    ) * 100

    numeric = round(numeric, 1)

    # ── Letra ─────────────────────────────────────────────────────────────────
    if numeric >= 80:
        letter = "A"
    elif numeric >= 60:
        letter = "B"
    elif numeric >= 40:
        letter = "C"
    elif numeric >= 20:
        letter = "D"
    else:
        letter = "E"

    # ── Etiquetas descriptivas ─────────────────────────────────────────────────
    labels = _generate_labels(
        title_score, duration_det, lexical_score,
        data_score, source_score, has_transcript, title_det,
        category_id=category_id,
        engagement_sc=engagement_sc,
    )

    details = {
        "has_transcript": has_transcript,
        "signals": {
            "title":            {"score": title_score,    **title_det},
            "duration":         {"score": duration_score, **duration_det},
            "lexical_richness": {"score": lexical_score,  **(lexical_det if isinstance(lexical_det, dict) else {})},
            "data_density":     {"score": data_score,     **(data_det if isinstance(data_det, dict) else {})},
            "source_presence":  {"score": source_score,   **(source_det if isinstance(source_det, dict) else {})},
            "readability":      {"score": readability_sc, **(readab_det if isinstance(readab_det, dict) else {})},
            "repetition":       {"score": repetition_sc,  **(repetit_det if isinstance(repetit_det, dict) else {})},
            "category":         {"score": category_sc,    **category_det},
            "engagement":       {"score": engagement_sc,  **engage_det},
            "description":      {"score": desc_sc,        **desc_det},
        }
    }

    return {
        "letter":  letter,
        "numeric": numeric,
        "labels":  labels,
        "details": details,
    }


def _generate_labels(
    title_score, duration_det, lexical_score,
    data_score, source_score, has_transcript, title_det,
    category_id=None, engagement_sc=0.5,
) -> list:
    labels = []
    fmt = duration_det.get("format", "unknown")

    if has_transcript:
        cognitive_density = (lexical_score + data_score + source_score) / 3
    else:
        cognitive_density = None

    # ── Formato + densidad cognitiva ──
    if fmt in ("short", "very_short"):
        labels.append("⚡ Formato corto / consumo rápido")
    elif fmt in ("long", "very_long"):
        if cognitive_density is None:
            labels.append("⏱️ Contenido largo")
        elif cognitive_density >= 0.45:
            labels.append("🧠 Requiere atención sostenida")
        elif cognitive_density <= 0.35:
            labels.append("🎙️ Consumo de fondo / pasivo")
        else:
            labels.append("⏱️ Contenido largo")

    # ── Categoría educativa ──
    cat_str = str(category_id) if category_id else ""
    if cat_str in ("27", "28"):
        labels.append("🎓 Contenido educativo / científico")
    elif cat_str == "25":
        labels.append("📰 Noticias y análisis")

    # ── Título clickbait ──
    if title_score < 0.5:
        labels.append("🎣 Título de alto estímulo emocional")

    # ── Calidad del contenido (con transcript) ──
    if has_transcript:
        if source_score >= 0.6:
            labels.append("📚 Cita fuentes o evidencia")
        elif data_score >= 0.6:
            labels.append("📊 Rico en datos y cifras")
        elif cognitive_density is not None and cognitive_density < 0.25:
            labels.append("🎯 Baja densidad informativa")
        elif source_score < 0.2 and data_score < 0.2:
            labels.append("🎯 Opinión sin fuentes primarias")

        if lexical_score >= 0.7:
            labels.append("📖 Alta densidad conceptual")
        elif lexical_score <= 0.25:
            labels.append("🔁 Vocabulario muy repetitivo")
    else:
        labels.append("⚠️ Sin transcript disponible")

    # ── Engagement alto ──
    if engagement_sc >= 0.75:
        labels.append("💬 Alto engagement de la comunidad")

    return labels[:3]  # máximo 3 etiquetas

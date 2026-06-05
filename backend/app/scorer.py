# app/scorer.py
"""
Nutri-Score rule-based scorer.
Calcula un score A-E para videos de YouTube usando señales de titulo,
duracion y transcript. Sin dependencias de LLM — 100% local.
"""
import re
import json
from collections import Counter
from typing import Optional

try:
    import textstat
    TEXTSTAT_AVAILABLE = True
except ImportError:
    TEXTSTAT_AVAILABLE = False


# ─── PESOS DE CADA SEÑAL (deben sumar 1.0) ────────────────────────────────────
WEIGHTS = {
    "title":             0.20,
    "duration":          0.10,
    "lexical_richness":  0.20,
    "data_density":      0.20,
    "source_presence":   0.15,
    "readability":       0.05,
    "repetition":        0.10,
}

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

    # Penalizaciones
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
        # Con menos de 200 palabras el ratio está inflado artificialmente
        # (cualquier texto corto tiene alta proporción de palabras únicas)
        return 0.5, {"reason": "transcript_too_short_for_reliable_lex"}

    ratio = len(set(words)) / len(words)
    # Normalizar: típicamente cae entre 0.2 y 0.7
    normalized = min((ratio - 0.2) / 0.5, 1.0)
    normalized = max(normalized, 0.0)
    return round(normalized, 3), {"unique_ratio": round(ratio, 3), "total_words": len(words)}


def score_data_density(text: str) -> tuple[float, dict]:
    """Presencia de números, porcentajes y cifras. 0-1."""
    words = re.findall(r"\b\w+\b", text)
    if not words:
        return 0.0, {}

    numbers = re.findall(r"\b\d+[.,]?\d*\s*%?\b", text)
    density = len(numbers) / (len(words) / 100)  # por cada 100 palabras
    normalized = min(density / 5.0, 1.0)         # 5 números/100 palabras = score máximo
    return round(normalized, 3), {"numbers_found": len(numbers), "density_per_100w": round(density, 2)}


def score_source_presence(text: str) -> tuple[float, dict]:
    """Detección de referencias a fuentes primarias. 0-1."""
    text_lower = text.lower()
    hits = {w for w in SOURCE_WORDS if w in text_lower}
    normalized = min(len(hits) / 5.0, 1.0)  # 5+ palabras de fuente = score máximo
    return round(normalized, 3), {"source_words_found": sorted(hits)}


def score_readability(text: str) -> tuple[float, dict]:
    """Complejidad sintáctica óptima (ni muy simple ni muy compleja). 0-1."""
    if not TEXTSTAT_AVAILABLE or len(text.split()) < 50:
        return 0.5, {"reason": "textstat_unavailable_or_short"}

    try:
        flesch = textstat.flesch_reading_ease(text)
        # Rango ideal: 30-60 (contenido que requiere atención pero es comprensible)
        if 30 <= flesch <= 60:
            score = 1.0
        elif flesch < 10:
            score = 0.5   # extremadamente complejo
        elif flesch < 30:
            score = 0.75  # complejo
        elif flesch < 80:
            score = 0.65  # fácil
        else:
            score = 0.3   # muy fácil / simple
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


# ─── SCORE COMPUESTO ──────────────────────────────────────────────────────────

def compute_score(
    title: str,
    duration_seconds: Optional[int],
    transcript: Optional[str],
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

    # Calcular señales
    title_score,    title_det    = score_title(title)
    duration_score, duration_det = score_duration(duration_seconds)

    if has_transcript:
        lexical_score,  lexical_det  = score_lexical_richness(transcript_text)
        data_score,     data_det     = score_data_density(transcript_text)
        source_score,   source_det   = score_source_presence(transcript_text)
        readability_sc, readab_det   = score_readability(transcript_text)
        repetition_sc,  repetit_det  = score_repetition(transcript_text)
    else:
        # Sin transcript: usamos neutrales para no castigar injustamente
        lexical_score  = lexical_det  = 0.5
        data_score     = data_det     = 0.5
        source_score   = source_det   = 0.5
        readability_sc = readab_det   = 0.5
        repetition_sc  = repetit_det  = 0.5

    # Score ponderado
    numeric = (
        title_score    * WEIGHTS["title"]            +
        duration_score * WEIGHTS["duration"]         +
        lexical_score  * WEIGHTS["lexical_richness"] +
        data_score     * WEIGHTS["data_density"]     +
        source_score   * WEIGHTS["source_presence"]  +
        readability_sc * WEIGHTS["readability"]      +
        repetition_sc  * WEIGHTS["repetition"]
    ) * 100

    numeric = round(numeric, 1)

    # Letra
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

    # Etiquetas descriptivas
    labels = _generate_labels(
        title_score, duration_det, lexical_score,
        data_score, source_score, has_transcript, title_det
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
        }
    }

    return {
        "letter": letter,
        "numeric": numeric,
        "labels": labels,
        "details": details,
    }


def _generate_labels(
    title_score, duration_det, lexical_score,
    data_score, source_score, has_transcript, title_det
) -> list:
    labels = []

    fmt = duration_det.get("format", "unknown")

    # Densidad cognitiva combinada (solo significativa si hay transcript)
    if has_transcript:
        cognitive_density = (lexical_score + data_score + source_score) / 3
    else:
        cognitive_density = None

    # ── Etiqueta de formato: cruza duración con densidad cognitiva ──
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
    # medium: no etiqueta de formato, el contenido habla por sí solo

    # ── Título clickbait ──
    if title_score < 0.5:
        labels.append("🎣 Título de alto estímulo emocional")

    # ── Calidad del contenido (solo con transcript) ──
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

    return labels[:3]  # máximo 3 etiquetas

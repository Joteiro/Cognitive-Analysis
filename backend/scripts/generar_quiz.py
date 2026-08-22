#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generar_quiz.py (v0.1, PILOTO) -- genera preguntas de retencion desde las
transcripciones y descarta las que se pueden contestar sin ver el video.

POR QUE EXISTE
    El panel de descriptores mide COMPOSICION: que trae el video. No mide
    EFECTO: que le quedo a quien lo vio. Un quiz diferido da, por primera vez
    en el proyecto, una variable DEPENDIENTE -- y una que no sale de una
    rubrica propia ni del juicio de un LLM, sino de un hecho verificable:
    la persona se acuerda o no se acuerda. Eso es lo que rompe la
    circularidad que marco el profesor.

EL PROBLEMA QUE RESUELVE ESTE SCRIPT
    Una pregunta contestable sin haber visto el video no mide retencion,
    mide conocimiento previo. Si no se filtran, el "porcentaje de acierto"
    no significa nada y toda la validacion posterior se cae.
    Por eso cada pregunta pasa DOS controles antes de sobrevivir:

      1. ANCLAJE. El modelo debe devolver una cita textual de la
         transcripcion que justifique la respuesta. El script comprueba que
         esa cita EXISTA de verdad en el texto. Si no aparece, el modelo se
         la invento y la pregunta se descarta.

      2. TRIVIALIDAD. El MISMO modelo intenta contestar la pregunta SIN la
         transcripcion, viendo solo lo que veria alguien que paso por el
         titulo en su historial: titulo, canal y las cuatro opciones. Si
         acierta, la pregunta era contestable sin ver el video y se
         descarta. Este es el grupo de control, y sale gratis.

    El script NO escribe en la base. Es un piloto: produce archivos para
    leerlos y decidir si la funcionalidad vale la pena antes de construir
    notificaciones, interfaz y guardado de respuestas.

USO   (con el venv de analisis: backend\\scripts\\.venv)
    # ver que videos entrarian, sin gastar una sola llamada a la API
    .venv\\Scripts\\python generar_quiz.py --dry-run

    # preguntarle a la API cual es TU cupo real y si el piloto entra
    .venv\\Scripts\\python generar_quiz.py --limites

    # generar sobre 5 videos para mirar la pinta que tienen
    .venv\\Scripts\\python generar_quiz.py --max 5

    # los 37 informativos del historial, retomando lo ya hecho
    .venv\\Scripts\\python generar_quiz.py --reanudar

    # por defecto usa Gemini 2.5 Flash (mas cupo/min, sin recorte); para Groq:
    .venv\\Scripts\\python generar_quiz.py --proveedor groq

EL CUELLO DE BOTELLA
    En el plan gratuito lo que ata no es el numero de peticiones sino los
    TOKENS POR MINUTO, y la transcripcion es casi todo el gasto. El script
    lee las cabeceras `x-ratelimit-*` de cada respuesta y espera solo cuando
    el cupo se agota, guarda despues de cada video, y `--reanudar` retoma sin
    volver a pagar lo ya generado. Si una sola peticion no entra en la
    ventana, baja `--max-palabras`.

REQUISITOS
    backend/.env con:
        DATABASE_URL=postgresql://...      (la que ya usas)
        # segun el proveedor que elijas con --proveedor (defecto: gemini):
        GEMINI_API_KEY=...                 (gratis en aistudio.google.com/apikey)
        GROQ_API_KEY=gsk_...               (gratis en console.groq.com)
    pip install -r requirements-analisis.txt   (psycopg2, dotenv, requests)

SALIDA (en docs/)
    quiz_piloto.json          todo, incluidas las descartadas y por que
    quiz_piloto.csv           una fila por pregunta, para cruzar con el panel
    quiz_piloto_informe.md    tasas de supervivencia y ejemplos comentados
"""
import argparse
import json
import os
import random
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("Falta requests.  pip install -r requirements-analisis.txt")
    sys.exit(2)

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------

# OJO: esta version se guarda en cada fila de la salida y tiene que subir CADA
# VEZ que cambien los prompts o los filtros. Se dejo en "0.1" mientras el
# prompt pasaba por tres revisiones, con lo cual las corridas v1, v2 y v3
# quedaron todas etiquetadas igual siendo instrumentos distintos: exactamente
# el error de `scorer_version='1.0'` que el proyecto ya cometio una vez.
# La version miente si no se sube a mano.
VERSION = "quiz-1.2"

# El defecto de Groq es 1024, y los modelos de razonamiento (gpt-oss, qwen3)
# se lo gastan PENSANDO antes de escribir una sola llave del JSON. Sintoma:
# HTTP 400 `json_validate_failed` con `failed_generation` vacio en los videos
# largos, y respuestas truncadas (3 preguntas de 6) en los cortos. No era el
# texto de entrada: era el techo de salida.
#
# PERO OJO, y esto es lo contraintuitivo: **Groq cuenta el
# max_completion_tokens dentro del cupo por minuto de la peticion**. Reservar
# 6000 de salida hacia que TODA peticion pidiera ~8700 tokens y chocara con el
# limite de 8000 de gpt-oss-120b, sin importar si el video tenia 8.716 o 2.904
# palabras. Los tres fallos pedian 8690, 8706 y 8803: no los dominaba la
# entrada, los dominaba la reserva.
#
# Ademas el cupo es POR MODELO: llama-3.3-70b tenia 12.000 TPM y
# gpt-oss-120b tiene 8.000. Un numero fijo escrito a mano se rompe con el
# proximo cambio de catalogo, asi que el techo se CALCULA en cada llamada a
# partir del cupo que la API informa. Ver `ClienteLLM.techo_salida`.
MAX_SALIDA_GENERACION = 8000    # tope deseable para generar 6 preguntas (se recorta al cupo real)
# El JSON del control es minusculo (dos campos), pero NO se puede reservar poco:
# los modelos de razonamiento --y Gemini 2.5 Flash piensa por defecto-- gastan el
# presupuesto de salida PENSANDO antes de escribir la primera llave. Con 700
# tokens el pensamiento se comia todo y el JSON salia truncado ("Unterminated
# string"): en la primera corrida con Gemini se perdieron asi 14 de 18 preguntas
# buenas, descartadas por `control_fallo` cuando el problema no era la pregunta
# sino que no llegabamos a leer la respuesta del control. Hay que dejarle aire.
MAX_SALIDA_CONTROL = 3000
MIN_SALIDA = 1200               # por debajo de esto no cabe ni el razonamiento
MARGEN_TPM = 600                # colchon para que la estimacion de entrada falle a favor
TPM_POR_DEFECTO = 8000          # si no se pudo leer el cupo, se asume el mas chico visto

# Subido de "low" a "medium" tras la v0.6: con esfuerzo bajo la trivialidad
# llego al 60 % (azar = 25 %). La hipotesis es que disenar buenos distractores
# es justo la parte que exige razonar -- hay que rastrear la transcripcion
# buscando otras cifras y nombres que podrian encajar -- y con esfuerzo bajo el
# modelo escribe los distractores obvios. Se puede bajar con --esfuerzo low
# si el cupo aprieta.
REASONING_EFFORT = "medium"

# Las URLs concretas viven en PROVEEDORES (mas abajo): cada proveedor expone su
# propio dialecto OpenAI y el cliente arma chat/completions y models a partir de
# la base.

# Preferencia de modelo, de mejor a peor para esta tarea. El primero que la
# cuenta tenga disponible es el que se usa.
#
# Por que una lista y no un nombre fijo: los proveedores retiran modelos con
# poco aviso y un nombre hardcodeado convierte el script en basura seis meses
# despues. El script pregunta que hay disponible y elige. Se imprime cual
# eligio, y queda guardado en la salida: si el dia de manana las preguntas
# cambian de calidad, se puede saber si fue por el modelo.
MODELOS_PREFERIDOS = [
    "openai/gpt-oss-120b",       # 2026-08-16: el mayor de chat disponible en la cuenta
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",   # retirado por Groq; queda por si reaparece
    "llama-3.1-70b-versatile",
]

# Proveedores. El script nacio contra Groq; se agrego Gemini porque su cupo por
# minuto (250.000 tokens/min en el free tier de 2.5 Flash) es ~30x el de Groq
# (8.000). Eso elimina el recorte de transcripcion --el que mas dañaba la calidad
# de las preguntas-- porque hasta el video mas largo entra entero en una sola
# ventana. Ambos hablan el mismo dialecto OpenAI: solo cambian la URL, la clave,
# la lista de modelos y como se descubre (o se fija) el cupo.
PROVEEDORES = {
    "gemini": {
        "base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "claves": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "modelos": [
            "gemini-2.5-flash",        # el elegido para el piloto
            "gemini-2.5-flash-lite",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
        ],
        "tpm": 250000,              # Gemini no manda cabeceras: el cupo se fija aca
        "pausa": 6.5,               # el limite real es 10 PETICIONES/min, no los tokens
        "cabeceras_cupo": False,    # no expone x-ratelimit-*: no leer ni esperar por ellas
        "include_reasoning": False, # ese extra es propio de Groq; Gemini lo rechaza
        "param_salida": "max_tokens",
        # Gemini 2.5 Flash PIENSA dentro del presupuesto de salida: los tokens
        # de razonamiento se descuentan de max_tokens. Con 8.000 el JSON de 6
        # preguntas se cortaba a la mitad en 6 de 30 videos ("Unterminated
        # string"). No dependia del tamano de la entrada: fallaron videos de
        # 3.454 palabras y funcionaron de 8.716. Su cupo es de 250.000
        # tokens/min, asi que subirlo no cuesta nada.
        "max_salida": 24000,
        "strip_prefix": True,       # lista "models/gemini-..."; el chat quiere el nombre pelado
    },
    "groq": {
        "base": "https://api.groq.com/openai/v1",
        "claves": ["GROQ_API_KEY"],
        "modelos": MODELOS_PREFERIDOS,
        "tpm": TPM_POR_DEFECTO,
        "pausa": 2.0,
        "cabeceras_cupo": True,
        "include_reasoning": True,
        "param_salida": "max_completion_tokens",
        "max_salida": MAX_SALIDA_GENERACION,   # Groq: lo ata el cupo de 8.000/min
        "strip_prefix": False,
    },
}

# Modelos que NO son de chat y que jamas deben elegirse como respaldo.
#
# Historia: la heuristica de respaldo era "que tenga 'llama' o 'instruct' en el
# nombre", y cuando Groq retiro llama-3.3-70b eligio
# `meta-llama/llama-prompt-guard-2-86m` -- un clasificador de inyeccion de
# prompts de 86 millones de parametros con contexto de unos cientos de tokens.
# El sintoma fue un HTTP 400 de "reduce the length of the messages", que hace
# pensar en un problema de longitud del texto cuando en realidad el modelo
# estaba mal elegido. Coincidir en el nombre no es ser apto para la tarea.
NO_CHAT = ("whisper", "guard", "orpheus", "tts", "embed", "rerank",
           "moderation", "safeguard", "prompt-guard",
           "image", "imagen", "veo")   # los ultimos tres, no-chat de Gemini

# Por video. Subio de 4 a 6 tras el piloto v0.1: con tres filtros encadenados
# sobreviven menos de la mitad, y con 4 generadas quedaban 1,8 utiles por
# video, por debajo del minimo de 2 que hace falta para distinguir a quien
# retuvo de quien no. Generar de mas es barato; el gasto real es la
# transcripcion, que se manda una sola vez por video.
N_PREGUNTAS = 6
PAUSA_SEGUNDOS = 2.0       # entre llamadas, para no despertar el limite de tasa
MAX_REINTENTOS = 4

# Por encima de esto se muestrea la transcripcion en tres ventanas.
#
# Por que 3000 y no mas: en el plan gratuito el cuello de botella NO es el
# numero de peticiones sino los TOKENS POR MINUTO, y la transcripcion es
# practicamente todo el gasto (el control de trivialidad no manda texto).
# 3000 palabras son unos 4200 tokens por video: con eso el piloto entero
# entra en un cupo modesto. Para cuatro preguntas alcanza de sobra; lo que
# se pierde es cobertura de los videos muy largos, y queda anotado en la
# salida como `transcripcion_recortada` para no olvidarlo al interpretar.
MAX_PALABRAS = 3000

# Un quiz de opcion multiple con 4 opciones se acierta al azar el 25 % de las
# veces. El control usa temperatura 0 y una sola pasada: no es una medida de
# probabilidad, es un filtro binario "esto era adivinable / no lo era".
N_OPCIONES = 4

RAIZ = Path(__file__).resolve().parent.parent.parent   # .../Cognitive Analysis
DOCS = RAIZ / "docs"
# Las salidas del piloto van a su propia carpeta: son muchas (json + csv + md
# por cada version del instrumento) y ensuciaban docs/, donde viven los
# informes del estudio. `formato_verificado.json` NO se mueve: no es una
# salida del quiz, es una entrada que el quiz consume.
QUIZ = DOCS / "quiz_piloto"
# Tres carpetas por tipo de artefacto: los tests generados, los formularios que
# contesta la gente y las respuestas que devuelven. Antes convivian los tres en
# la misma carpeta y con una decena de versiones ya no se encontraba nada.
SALIDA = QUIZ / "tests"
FORMULARIOS = QUIZ / "formularios"
RESPUESTAS = QUIZ / "respuestas"


# ---------------------------------------------------------------------------
# Normalizacion de texto (compartida por el control de anclaje)
# ---------------------------------------------------------------------------

def normalizar(texto: str) -> str:
    """Minusculas, sin tildes, sin puntuacion, espacios colapsados.

    Los subtitulos automaticos de YouTube no traen puntuacion y escriben mal
    las tildes. Comparar la cita contra la transcripcion en crudo daria
    falsos negativos constantes: el modelo devuelve la frase con puntuacion
    "arreglada" y no coincidiria nunca.
    """
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9ñ ]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def cita_esta_en_transcripcion(cita: str, transcripcion_norm: str) -> tuple:
    """Devuelve (bool, motivo). Tolerante, pero no tanto como para dejar pasar
    una invencion.

    Primero prueba la coincidencia literal ya normalizada. Si falla -- porque
    el modelo reordeno un articulo o se comio una muletilla -- busca la tirada
    mas larga de palabras consecutivas de la cita que si aparezca. Se acepta
    si esa tirada llega a 6 palabras o cubre el 60 % de la cita.

    Por que 6: por debajo de eso cualquier cita comparte trozos con cualquier
    transcripcion en el mismo idioma ("y esto es lo que", "por lo tanto en")
    y el control dejaria de filtrar nada.
    """
    c = normalizar(cita)
    if not c:
        return False, "cita_vacia"

    palabras = c.split()
    # Una cita corta puede aparecer literalmente en cualquier transcripcion
    # ("en el video de hoy") sin anclar nada. El minimo va antes de la
    # comprobacion literal a proposito.
    if len(palabras) < 6:
        return False, f"cita_demasiado_corta_{len(palabras)}_palabras"

    if c in transcripcion_norm:
        return True, "literal"

    mejor = 0
    for inicio in range(len(palabras)):
        # se corta apenas deja de crecer: la tirada es contigua por definicion
        for fin in range(len(palabras), inicio + mejor, -1):
            trozo = " ".join(palabras[inicio:fin])
            if trozo in transcripcion_norm:
                mejor = max(mejor, fin - inicio)
                break

    if mejor >= 6 or mejor >= 0.6 * len(palabras):
        return True, f"parcial_{mejor}_de_{len(palabras)}"
    return False, f"no_encontrada_max_{mejor}_palabras"


VACIAS = {"el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al",
          "y", "o", "que", "en", "con", "por", "para", "su", "sus", "es", "son",
          "the", "of", "and", "to", "in", "a", "mas", "no", "se", "lo"}


# Tipos de pregunta cuya respuesta es una SINTESIS, no un dato copiable.
TIPOS_INFERENCIA = {"argumento", "relacion", "definicion"}


def respuesta_esta_en_cita(respuesta: str, cita: str, tipo: str = "dato") -> tuple:
    """Tercer control: la cita tiene que RESPALDAR la respuesta.

    Nace de un caso real del piloto v0.1: la pregunta era "en que plataforma
    se transmite los lunes", la respuesta "YouTube", y la cita decia "los dias
    lunes a las 21 horas yo hago una transmision formal" -- que existe en la
    transcripcion y no menciona ninguna plataforma. Anclar no es justificar.

    PERO el umbral no puede ser el mismo para todos los tipos, y la v0.6 lo
    demostro: de 6 descartes por este control, 5 eran de tipo argumento,
    relacion o definicion. No fue casualidad. La respuesta a "por que el autor
    sostiene X" es una SINTESIS -- "porque controla el presupuesto y la
    direccion" -- que por naturaleza no aparece literal en ninguna cita. El
    control, tal como estaba, mataba sistematicamente las preguntas de
    comprension y dejaba pasar solo las de dato suelto: premiaba al generador
    peor.

    Asi que el umbral depende del tipo:
      - dato: la respuesta se copia del texto, se exige la mitad de sus
        palabras de contenido.
      - inferencia: se exige solo que la cita comparta ALGO con la respuesta
        (un termino de contenido), porque lo que ancla el razonamiento es la
        cita entera, ya verificada por el control de anclaje.
    """
    r = [t for t in normalizar(respuesta).split() if t not in VACIAS and len(t) > 1]
    if not r:
        return False, "respuesta_vacia"
    c = set(normalizar(cita).split())
    presentes = [t for t in r if t in c]

    if tipo in TIPOS_INFERENCIA:
        minimo = 1
        etiqueta = "inferencia"
    else:
        minimo = max(1, (len(r) + 1) // 2)
        etiqueta = "dato"

    if len(presentes) >= minimo:
        return True, f"{etiqueta}_{len(presentes)}_de_{len(r)}"
    return False, f"{etiqueta}_solo_{len(presentes)}_de_{len(r)}_pedia_{minimo}"


# Marcas inequivocas de que un fragmento es publicidad del canal y no
# contenido. Descubierto porque una pregunta sobre un festival patrocinado
# SOBREVIVIO a los tres controles y quedo en el dataset final: el peor
# resultado posible, porque mide si recordas un anuncio.
#
# La lista es corta a proposito. NO incluye "publicidad", "promocion" ni
# "anuncio": uno de los videos del corpus trata precisamente sobre publicidad
# institucional, y esas palabras mataran preguntas legitimas. Se prefiere
# dejar pasar algun anuncio antes que descartar contenido real; el resto lo
# tiene que atrapar la regla del prompt y la revision a mano.
PROMO = (
    "patrocina", "patrocinado por", "codigo de descuento", "cupon de descuento",
    "usa mi codigo", "link en la descripcion", "enlace en la descripcion",
    "suscribite al canal", "suscribete al canal", "dale like",
    "activa la campanita", "este video es posible gracias a",
    "entradas ya a la venta", "consegui tus entradas", "mi curso",
    "nuestra tienda", "invitado de hoy es gracias a",
)


def _magnitud(opcion: str) -> float:
    """Valor numerico aproximado de una opcion, resolviendo 'millones'/'mil'."""
    t = normalizar(opcion)
    m = re.search(r"(\d+(?:[.,]\d+)?)", t)
    if not m:
        return float("nan")
    v = float(m.group(1).replace(",", "."))
    if "millon" in t or "millones" in t:
        v *= 1e6
    elif "mil " in t or t.endswith(" mil"):
        v *= 1e3
    return v


def equilibrio_opciones(opciones: list, correcta: int) -> tuple:
    """Cuarto control: que la opcion correcta no se delate por su FORMA.

    Nace de la corrida v0.8, donde el control acerto 8 de 8 preguntas que a
    simple vista no eran triviales. No era filtracion: eran los distractores.
    Tres delatores, todos presentes en esa corrida:

      1. UNIDAD. "En cuantas PERSONAS aumento la plantilla" con opciones
         "1000 canales / 28 personas / 100 canales / 500 personas". Dos
         distractores en la unidad equivocada: la respuesta es la unica cifra
         grande medida en personas. Se contesta sin leer nada.

      2. MAGNITUD. Un contrato de television con opciones de "25 euros",
         "8,3 millones", "14 millones" y "40 millones". El absurdo se
         descarta solo y quedan tres.

      3. LONGITUD. El delator mas sutil y el mas frecuente en preguntas
         escritas por una maquina: la correcta es la mas larga y elaborada,
         los distractores son cortos y genericos. Un modelo fuerte explota
         ese patron sin saber nada del tema.

    Esto no reemplaza al control de trivialidad: lo complementa. El control
    dice QUE la pregunta era adivinable; esto dice POR QUE, y es
    deterministico, reproducible y explicable en la memoria.
    """
    if len(opciones) < 2:
        return False, "faltan_opciones"
    otras = [o for i, o in enumerate(opciones) if i != correcta]
    buena = opciones[correcta]

    # 1. unidad: solo tiene sentido en preguntas NUMERICAS. Sin esta guarda, la
    # comprobacion se dispara con opciones que son nombres propios ("los nazis"
    # vs "Estados Unidos") y las descarta por "unidades distintas", que es un
    # falso positivo: ahi no hay ninguna unidad, hay sujetos.
    # El limite baja de 6 a 4 palabras: con opciones mas ricas ("8,3 millones de
    # euros mas extras") la ultima palabra deja de ser la unidad y la
    # comprobacion produce falsos positivos -- leyo "euros", "extras" y
    # "espanol" como tres unidades distintas de la misma pregunta.
    numericas = sum(1 for o in opciones if re.search(r"\d", o))
    if numericas >= len(opciones) - 1 and all(len(o.split()) <= 4 for o in opciones):
        def unidad(o):
            ts = [t for t in normalizar(o).split() if not t.isdigit() and t not in VACIAS]
            return ts[-1] if ts else ""
        unidades = {unidad(o) for o in opciones if unidad(o)}
        if len(unidades) > 1:
            return False, f"unidades_mezcladas_{sorted(unidades)}"

    # 2. magnitud
    vals = [_magnitud(o) for o in opciones]
    vals = [v for v in vals if v == v and v > 0]
    if len(vals) == len(opciones) and min(vals) > 0:
        razon = max(vals) / min(vals)
        if razon > 50:
            return False, f"magnitudes_dispares_x{razon:.0f}"

    # 3. longitud
    largos = sorted(len(o) for o in otras)
    mediana = largos[len(largos) // 2]
    if mediana > 0:
        prop = len(buena) / mediana
        # 1,6 y 0,5 en vez de 1,4 y 0,6: con opciones en prosa la dispersion
        # natural de longitudes es mayor, y el umbral estrecho descartaba
        # preguntas sanas (4 de 18 en la v1.0, una de ellas falso positivo).
        if prop > 1.6:
            return False, f"correcta_mas_larga_x{prop:.2f}"
        if prop < 0.5:
            return False, f"correcta_mas_corta_x{prop:.2f}"

    return True, "equilibradas"


def cita_es_publicidad(cita: str) -> bool:
    c = normalizar(cita)
    return any(m in c for m in PROMO)


def recortar_transcripcion(texto: str, max_palabras: int = MAX_PALABRAS) -> tuple:
    """Si la transcripcion no entra comoda en el contexto, se toman tres
    ventanas repartidas (principio, medio, final) en vez de truncar.

    Truncar por el principio sesgaria las preguntas hacia los primeros
    minutos, que es justo la parte que todo el mundo recuerda igual. Lo
    interesante para medir retencion esta repartido.
    """
    palabras = texto.split()
    if len(palabras) <= max_palabras:
        return texto, False

    tam = max_palabras // 3
    n = len(palabras)
    ventanas = [
        palabras[0:tam],
        palabras[n // 2 - tam // 2: n // 2 + tam // 2],
        palabras[n - tam: n],
    ]
    return "\n[...]\n".join(" ".join(v) for v in ventanas), True


# ---------------------------------------------------------------------------
# Cliente LLM (Groq o Gemini: mismo dialecto OpenAI, distinto cupo)
# ---------------------------------------------------------------------------

def parse_duracion(texto: str) -> float:
    """'2m59.56s' -> 179.56 ; '7.66s' -> 7.66 ; '1h2m3s' -> 3723.0

    Groq expresa los tiempos de renovacion en este formato, no en segundos
    pelados. Leerlo mal significa dormir dos segundos donde habia que dormir
    dos minutos, y comerse el 429 igual.
    """
    if not texto:
        return 0.0
    total = 0.0
    for valor, unidad in re.findall(r"([\d.]+)\s*(ms|h|m|s)", texto):
        v = float(valor)
        total += {"h": v * 3600, "m": v * 60, "s": v, "ms": v / 1000}[unidad]
    return total


class ClienteLLM:
    def __init__(self, api_key: str, cfg: dict, modelo: str = None):
        self.key = api_key
        self.cfg = cfg
        self.url = cfg["base"] + "/chat/completions"
        self.modelos_url = cfg["base"] + "/models"
        self.modelos_preferidos = cfg["modelos"]
        self.sesion = requests.Session()
        self.sesion.headers.update({"Authorization": f"Bearer {api_key}"})
        self.modelo = modelo or self._elegir_modelo()
        self.llamadas = 0
        self.tokens_usados = 0
        # Los catalogos cambian y no todos los modelos aceptan los mismos
        # parametros. En vez de mantener una tabla de quien soporta que, se
        # intenta con los extras y si la API los rechaza se reintenta sin
        # ellos, una sola vez, y se recuerda. Ya nos mordio dos veces que el
        # catalogo de Groq cambiara por debajo.
        self.extras_ok = True
        self.esfuerzo = REASONING_EFFORT
        self.tpm = cfg["tpm"]
        self.limites = {}       # ultima foto de las cabeceras x-ratelimit-*
        self.esperas = 0.0      # segundos dormidos esperando cupo
        self._aviso_techo = False

    @staticmethod
    def estimar_tokens(mensajes: list) -> int:
        """Estimacion grosera de los tokens de entrada.

        ~3,5 caracteres por token en espanol. No hace falta precision: para
        eso esta MARGEN_TPM. Lo que hace falta es no pasarse.
        """
        caracteres = sum(len(m.get("content") or "") for m in mensajes)
        return int(caracteres / 3.5) + 40 * len(mensajes)

    def techo_salida(self, mensajes: list, deseado: int) -> int:
        """Cuanto se puede pedir de salida sin que la peticion exceda el cupo.

        Groq suma entrada + max_completion_tokens y compara ese total contra el
        limite por minuto. Asi que el techo de salida no es una preferencia:
        es el cupo menos lo que ya ocupa la entrada.
        """
        entrada = self.estimar_tokens(mensajes)
        disponible = self.tpm - entrada - MARGEN_TPM
        if disponible < MIN_SALIDA:
            raise RuntimeError(
                f"La entrada estimada ({entrada} tokens) no deja espacio de salida "
                f"dentro del cupo de {self.tpm} tokens/min del modelo "
                f"{self.modelo}.\n"
                f"  Baja --max-palabras (ahora entrarian ~"
                f"{max(0, int((self.tpm - MARGEN_TPM - MIN_SALIDA - 800) / 1.4))} palabras) "
                f"o usa --preguntas 4.")
        # Sin max(MIN_SALIDA, ...): MIN_SALIDA es el minimo que se necesita
        # para que valga la pena pedir, no un piso que haya que reservar. Si el
        # control solo quiere 700, se le dan 700 y el resto del cupo queda
        # libre para la siguiente peticion.
        return min(deseado, disponible)

    def _leer_limites(self, r) -> None:
        # Gemini no manda cabeceras x-ratelimit-*: su cupo se fijo en PROVEEDORES
        # y no hay nada que aprender de la respuesta.
        if not self.cfg["cabeceras_cupo"]:
            return
        h = r.headers
        self.limites = {k: h[k] for k in h if k.lower().startswith("x-ratelimit")}
        try:
            # El cupo real del modelo, aprendido de la respuesta en vez de
            # escrito a mano: cambia con el modelo y con el catalogo.
            self.tpm = int(float(self.limites["x-ratelimit-limit-tokens"]))
        except (KeyError, ValueError):
            pass

    def _respetar_cupo(self, necesita: int) -> None:
        """Espera ANTES de gastar, si el cupo restante no da para la proxima.

        `necesita` es lo que va a costar ESTA peticion (entrada + techo de
        salida), no una constante. Antes habia un umbral fijo de 8.000 tokens
        que resulto ser igual al cupo total del modelo: el restante estaba
        siempre por debajo y el script dormia antes de CADA llamada. Con 210
        llamadas eso son mas de sesenta minutos de espera inventada.

        Es mas barato dormir 20 segundos que comerse un 429, reintentar y
        que el reintento tambien cuente. El limite que ata en el plan
        gratuito es el de tokens por minuto: una transcripcion entera es un
        pico enorme comparado con la conversacion tipica para la que estan
        pensados esos limites.
        """
        try:
            restantes = float(self.limites.get("x-ratelimit-remaining-tokens", "1e9"))
        except ValueError:
            return
        if restantes < necesita:
            espera = parse_duracion(self.limites.get("x-ratelimit-reset-tokens", "10s")) + 1
            print(f"       quedan {restantes:.0f} tokens y esta peticion necesita "
                  f"{necesita}; espero {espera:.0f}s")
            time.sleep(espera)
            self.esperas += espera

    def describir_limites(self) -> str:
        if not self.limites:
            return "(la API no devolvio cabeceras de limite)"
        orden = ["x-ratelimit-limit-requests", "x-ratelimit-remaining-requests",
                 "x-ratelimit-reset-requests", "x-ratelimit-limit-tokens",
                 "x-ratelimit-remaining-tokens", "x-ratelimit-reset-tokens"]
        filas = [f"  {k:<34} {self.limites[k]}" for k in orden if k in self.limites]
        otras = [f"  {k:<34} {v}" for k, v in sorted(self.limites.items()) if k not in orden]
        return "\n".join(filas + otras)

    def _elegir_modelo(self) -> str:
        try:
            r = self.sesion.get(self.modelos_url, timeout=30)
            r.raise_for_status()
            disponibles = {m["id"] for m in r.json().get("data", [])}
        except Exception as e:
            print(f"AVISO  no se pudo listar modelos ({e}); se usa el primero de la lista")
            return self.modelos_preferidos[0]

        # Gemini lista los modelos como "models/gemini-2.5-flash" pero su endpoint
        # de chat acepta el nombre pelado; Groq los lista y los pide igual
        # ("openai/gpt-oss-120b"). Se compara tolerando el prefijo pero se
        # devuelve el nombre preferido tal cual, que es el que cada API espera.
        for m in self.modelos_preferidos:
            if m in disponibles or any(d.split("/")[-1] == m for d in disponibles):
                return m

        # Ninguno de los conocidos. Se descartan primero los que no son de chat
        # y despues se ordena por tamano declarado en el nombre (120b > 27b >
        # 20b > 7b), que es la unica pista fiable que dan estos catalogos.
        def tamano(nombre: str) -> float:
            m = re.findall(r"(\d+(?:\.\d+)?)\s*b\b", nombre.lower())
            return max((float(x) for x in m), default=0.0)

        candidatos = [x for x in disponibles
                      if not any(mal in x.lower() for mal in NO_CHAT)]
        candidatos.sort(key=tamano, reverse=True)

        if not candidatos:
            raise RuntimeError(
                "Ningun modelo de chat utilizable en esta cuenta.\n"
                f"  Disponibles: {sorted(disponibles)}\n"
                "  Pasa uno a mano con --modelo si crees que alguno sirve.")

        elegido = candidatos[0].split("/")[-1] if self.cfg["strip_prefix"] else candidatos[0]
        print("AVISO  ninguno de los modelos preferidos existe ya (los proveedores "
              "retiran modelos sin aviso).\n"
              f"       Disponibles de chat: {candidatos}\n"
              f"       Se usara el mayor: {elegido}. Si no sirve, pasa otro "
              "con --modelo\n"
              "       y actualiza la lista de modelos del proveedor en el script.")
        return elegido

    def pedir(self, mensajes: list, temperatura: float = 0.3, json_estricto: bool = True,
              max_salida: int = None) -> str:
        if max_salida is None:
            max_salida = self.cfg.get("max_salida", MAX_SALIDA_GENERACION)
        techo = self.techo_salida(mensajes, max_salida)
        if max_salida >= MAX_SALIDA_GENERACION and techo < 2500 and not self._aviso_techo:
            self._aviso_techo = True
            print(f"       AVISO el techo de salida quedo en {techo} tokens. Si las "
                  f"respuestas salen truncadas,\n"
                  f"             baja --max-palabras o usa --preguntas 4.")

        cuerpo = {
            "model": self.modelo,
            "messages": mensajes,
            "temperature": temperatura,
            self.cfg["param_salida"]: techo,
        }
        if json_estricto:
            cuerpo["response_format"] = {"type": "json_object"}
        if self.extras_ok and self.esfuerzo:
            cuerpo["reasoning_effort"] = self.esfuerzo
            # include_reasoning es un extra de Groq; Gemini lo rechaza.
            if self.cfg["include_reasoning"]:
                cuerpo["include_reasoning"] = False

        self._respetar_cupo(self.estimar_tokens(mensajes) + techo)
        espera = 5
        for intento in range(1, MAX_REINTENTOS + 1):
            try:
                r = self.sesion.post(self.url, json=cuerpo, timeout=120)
            except requests.RequestException as e:
                if intento == MAX_REINTENTOS:
                    raise
                print(f"       red fallo ({e}); reintento en {espera}s")
                time.sleep(espera)
                espera *= 2
                continue

            self._leer_limites(r)

            if r.status_code == 429:
                # 429 significa DOS cosas muy distintas y hay que separarlas:
                #   - limite POR MINUTO: se arregla esperando unos segundos.
                #   - cupo DIARIO del free tier: NO se arregla esperando (se
                #     resetea a medianoche hora del Pacifico). Reintentar con
                #     backoff corto contra el cupo diario gasta los cuatro
                #     intentos y termina en "agotados los reintentos" sin explicar
                #     nada -- que es justo lo que confundia. Si el cuerpo dice que
                #     es diario, se corta ya con un mensaje util.
                cuerpo_err = r.text[:500]
                # Gemini, cuando el limite es POR MINUTO, suele adjuntar cuanto
                # esperar (RetryInfo.retryDelay, unos 30-60s): ahi si vale la pena
                # dormir y reintentar. El cupo DIARIO del free tier, en cambio,
                # llega como el mensaje generico de OpenAI --"exceeded your current
                # quota" / RESOURCE_EXHAUSTED / "check your plan and billing"-- SIN
                # retryDelay, porque no se arregla esperando segundos: se resetea a
                # medianoche del Pacifico. Reintentar contra eso solo gasta los
                # cuatro intentos sin explicar nada.
                m_delay = re.search(r'retry\w*delay"?\s*[:=]\s*"?(\d+(?:\.\d+)?)',
                                    cuerpo_err, re.IGNORECASE)
                pista_diaria = re.search(
                    r"per\s*-?\s*day|daily|requests?\s*per\s*day|exceeded your current quota|"
                    r"check your plan and billing|RESOURCE_EXHAUSTED",
                    cuerpo_err, re.IGNORECASE)
                if pista_diaria and not m_delay:
                    raise RuntimeError(
                        "HTTP 429: agotaste el CUPO DIARIO del free tier (la API dice "
                        "'exceeded your current quota').\n"
                        "  Google recorto los limites gratuitos en diciembre de 2025 y con "
                        "--esfuerzo high + --preguntas 12\n"
                        "  se gasta muy rapido. NO se arregla esperando segundos: el cupo "
                        "diario se resetea a\n"
                        "  medianoche hora del Pacifico (~07:00-08:00 UTC). Que podes hacer:\n"
                        "    - esperar al reset y seguir con --reanudar (no re-paga lo ya hecho)\n"
                        "    - iterar con corridas CHICAS: --max 1 --preguntas 6 --esfuerzo medium\n"
                        "      (guarda el high + muchas preguntas para la corrida final)\n"
                        "    - si el ir y venir con la cuota molesta mas de lo que cuesta, activar\n"
                        "      billing saca el tope: este piloto entero son centavos en 2.5 Flash\n"
                        f"  Respuesta de la API: {cuerpo_err}")
                # limite por minuto: se respeta el retryDelay sugerido si vino; si
                # no, la cabecera retry-after; si tampoco, se duplica la espera.
                pausa = (float(m_delay.group(1)) if m_delay else
                         parse_duracion(r.headers.get("retry-after", "")) or
                         float(r.headers.get("retry-after", espera) or espera))
                print(f"       limite por minuto; espero {pausa:.0f}s · {cuerpo_err[:120]}")
                time.sleep(pausa + 1)
                self.esperas += pausa
                espera *= 2
                continue

            if r.status_code >= 400:
                detalle = r.text[:300]
                # 413 / "request too large": el cupo por minuto es mas chico que
                # esta sola peticion. Reintentar no sirve: hay que mandar menos
                # texto. Se dice explicitamente para no perder cuatro intentos.
                if r.status_code == 413 or "too large" in detalle.lower():
                    raise RuntimeError(
                        f"HTTP {r.status_code}: la peticion no entra en el cupo por minuto.\n"
                        f"  Recorda que Groq suma la ENTRADA + el max_completion_tokens\n"
                        f"  reservado, y compara ese total contra el limite del modelo.\n"
                        f"  Cupo leido: {self.tpm} tokens/min. Baja --max-palabras.\n"
                        f"  Detalle: {detalle}")
                # Si el 400 se queja de uno de los parametros opcionales, se
                # reintenta sin ellos en vez de morir. Es la degradacion que
                # permite sobrevivir a un cambio de catalogo.
                if r.status_code == 400 and self.extras_ok and any(
                        p in detalle for p in ("reasoning_effort", "include_reasoning",
                                               "max_completion_tokens", "max_tokens")):
                    print("       el modelo no acepta los parametros de razonamiento; "
                          "reintento sin ellos")
                    self.extras_ok = False
                    cuerpo.pop("reasoning_effort", None)
                    cuerpo.pop("include_reasoning", None)
                    continue

                # 400/401/403/404 son errores de la peticion, no del momento:
                # reintentarlos cuatro veces solo hace perder un minuto y medio
                # antes de mostrar el mismo mensaje. Se corta ya.
                if r.status_code in (400, 401, 403, 404):
                    raise RuntimeError(f"HTTP {r.status_code} (no se reintenta): {detalle}")
                if intento == MAX_REINTENTOS:
                    raise RuntimeError(f"HTTP {r.status_code}: {detalle}")
                time.sleep(espera)
                espera *= 2
                continue

            self.llamadas += 1
            datos = r.json()
            self.tokens_usados += datos.get("usage", {}).get("total_tokens", 0)
            return datos["choices"][0]["message"]["content"]

        raise RuntimeError("agotados los reintentos")


# ---------------------------------------------------------------------------
# Los dos prompts
# ---------------------------------------------------------------------------

SISTEMA_GENERADOR = """Eres un disenador de evaluaciones de comprension. Trabajas SOLO con la transcripcion que te dan.

REGLA 0 — LAS CUATRO OPCIONES TIENEN QUE PARECERSE ENTRE SI.
Antes de escribir nada, entiende esto: una pregunta se rompe cuando la correcta se distingue por su FORMA en vez de por su contenido. Tres errores que arruinan una pregunta aunque el tema sea dificil:
- LONGITUD: si la correcta es la mas larga y detallada y los distractores son cortos y genericos, se acierta sin leer la pregunta. Las cuatro opciones deben tener una longitud parecida (que ninguna pase de una vez y media la mas corta).
- UNIDAD: si preguntas por personas, las CUATRO opciones van en personas. Nunca mezcles unidades (personas con canales, euros con anos, kilometros con horas).
- MAGNITUD: si la correcta son 14 millones, los distractores tienen que estar en ese orden ("8,3 millones", "22 millones", "40 millones"). Nunca pongas un absurdo como "25 euros": se descarta solo y reduce el examen a tres opciones.

REGLA 0-BIS — LOS CUATRO DISTRACTORES TIENEN QUE RESPONDER LA MISMA PREGUNTA.
Este es el error mas frecuente y el que mas preguntas arruina. Un distractor NO es "otra cosa que se dijo en el video": es OTRA RESPUESTA POSIBLE A ESA PREGUNTA EXACTA, falsa pero del mismo tipo y del mismo alcance.

Ejemplo de lo que NO hay que hacer:
  Pregunta: "Que estrategia uso la CIA para promover la imagen de una America libre y creativa?"
  Opciones: financiar revistas literarias / amenazar con aranceles / recortar visados de estudiante / promover peliculas de Hollywood
  Esta rota: solo dos opciones son estrategias culturales. Las de aranceles y visados no responden la pregunta, se descartan sin saber nada, y el examen se reduce a dos.

Ejemplo de lo que SI hay que hacer:
  Opciones: financiar revistas literarias y giras musicales / becar a periodistas extranjeros / producir documentales en lenguas locales / patrocinar festivales de cine europeos
  Las cuatro son estrategias culturales plausibles de la CIA. Solo una es la que dice la transcripcion.

Comprobacion obligatoria antes de dar por buena una pregunta: leete las cuatro opciones tapando cual es la correcta. Si alguna se puede descartar SOLO porque no viene al caso -- porque cambia de tema, de tipo o de escala -- reescribila.

REGLA 0-TER — EL ENUNCIADO NO PUEDE CONTENER LA PISTA.
No pongas en la pregunta adjetivos ni frases que describan la respuesta. "Como se describe el taller, REFLEJANDO LA ALTA DEMANDA de su obra?" regala que la respuesta habla de produccion masiva. Preguntalo seco: "Como se describe el taller de Rubens?".

REGLA 0-QUATER — PREGUNTA POR LO QUE ES CIERTO *EN ESTE VIDEO*, NO POR LO QUE ES CIERTO EN EL MUNDO.
Esta es la regla que mas importa y la mas dificil de cumplir.

Si la respuesta es un hecho publico documentado, cualquier persona informada la acierta sin haber visto nada, por buenos que sean los distractores. "Que hizo la CIA en la Guerra Fria" tiene una respuesta que esta en los libros: no mide si viste el video, mide cultura general.

Lo que si mide retencion es aquello que es cierto UNICAMENTE porque este video lo dice:
- La cifra concreta que cita ESTE narrador (aunque otras fuentes den otra).
- El ejemplo, la anecdota o la comparacion que ELIGIO para ilustrar su punto.
- Su opinion, su conclusion o la palabra con que califica algo.
- Detalles arbitrarios y verificables solo mirando ("anadio un loro rojo en la esquina superior izquierda").
- El orden en que encadena su argumento, o que atribuye a que causa.

Prueba definitiva antes de dar una pregunta por buena: pregunta-te "¿alguien que sabe mucho del tema pero NO vio el video podria acertar esto?". Si la respuesta es si, la pregunta no sirve por mas elegante que sea. Cambiala por una sobre lo que el narrador dijo, eligio o afirmo.

REGLA 1 — LOS DISTRACTORES SON LO MAS IMPORTANTE.
Un test se rompe cuando la respuesta correcta es simplemente la opcion que mas "suena bien". Si alguien que no vio el video puede acertar eligiendo la opcion mas plausible, la pregunta no sirve.
Los tres distractores deben ser COSAS QUE SI APARECEN EN LA TRANSCRIPCION pero que NO contestan esa pregunta: otras cifras que dijo el hablante, otros nombres que menciono, otros lugares de los que hablo. Asi las cuatro opciones son igual de plausibles para quien no vio el video, y solo distingue quien recuerda cual iba con cual.

Las cuatro opciones tienen que ser INTERCAMBIABLES EN LA FORMA:
- Misma unidad y misma moneda en las cuatro. Si la respuesta esta en euros, las cuatro en euros; PROHIBIDO mezclar euros con dolares, o una cifra "en millones" con otra a secas. (Error real a evitar: correcta "1220 millones de euros" con distractores "5000 millones de dolares" -> quien adivina descarta los dolares y la correcta queda cantada.)
- Mismo orden de magnitud y mismo formato (no mezcles "40.000" con "3"), parecida cantidad de palabras y mismo nivel de detalle. Si es un nombre propio, los otros tres tambien; si es una fecha, todas fechas parecidas.
- Igual de LLAMATIVAS. Si la respuesta correcta es sorprendente o muy especifica, los otros tres tambien tienen que ser sorprendentes y especificos, sacados del video. Nunca rodees la respuesta interesante de rellenos genericos. (Error real a evitar: "quienes fueron los pioneros? -> los nazis" con distractores sosos como "los paises europeos" o "Espana" -> quien adivina elige lo chocante.)

Antes de dar por buena una pregunta hace esta prueba mental: imagina a una persona lista que NO vio el video y solo lee el titulo y las cuatro opciones. Si la correcta se delata por su formato, su longitud, su rareza o por ser la unica "obvia", REESCRIBI los distractores. Si no consegues cuatro opciones igual de plausibles, descarta esa pregunta y hace otra.

REGLA 2 — NADA QUE SE PUEDA ADIVINAR.
Prohibido preguntar cultura general, cosas deducibles del TITULO del video, o cuya respuesta sea la unica razonable del mundo real. Si la respuesta esta en el titulo, la pregunta esta mal.

REGLA 3 — LA CITA DEBE CONTENER LA RESPUESTA.
La cita es un fragmento LITERAL y CONTIGUO de la transcripcion, copiado tal cual (no lo reescribas ni le arregles la puntuacion), de entre 8 y 30 palabras, y la respuesta correcta tiene que estar DENTRO de esa cita, no deducirse de ella. Si tu cita no contiene la respuesta, cambia la pregunta.

REGLA 4 — NADA DE PUBLICIDAD.
Las transcripciones contienen anuncios: patrocinios, venta de entradas, cursos, merchandising, pedidos de suscripcion. NO son contenido del video. Prohibido preguntar sobre ellos. Si el fragmento mas llamativo es un anuncio, ignoralo y busca otro. Recordar un anuncio no es haber aprendido nada del video.

REGLA 5 — PRIORIZA LA COMPRENSION SOBRE EL DATO SUELTO.
Las preguntas de "dato" (una cifra, un nombre, una fecha) son las mas faciles de adivinar y las que menos miden retencion real. Al menos la MITAD de las preguntas deben ser de comprension: tipo "relacion", "argumento" o "definicion" -- por que el hablante sostiene algo, que consecuencia le atribuye a que causa, que conclusion saca de que hecho. Usa las de dato suelto con moderacion, y solo cuando puedas rodear la respuesta de distractores del mismo tipo sacados del propio texto.

Responde en el mismo idioma de la transcripcion.

Devuelve SOLO un objeto JSON con esta forma exacta:
{"preguntas": [{"pregunta": "...", "opciones": ["...", "...", "...", "..."], "correcta": 0, "cita": "...", "tipo": "dato|argumento|definicion|relacion"}]}
El campo "correcta" es el indice (0-3) de la opcion correcta."""

SISTEMA_CONTROL = """Eres una persona informada que NO vio el video. Solo conoces el titulo y el canal.

Te dan una pregunta de opcion multiple. Contesta con tu mejor conjetura usando conocimiento general, el titulo, y el aspecto de las opciones. Siempre eliges una: no puedes abstenerte.

Devuelve SOLO un objeto JSON con esta forma: {"eleccion": <indice 0-3>, "seguridad": "alta|media|baja"}"""

# Nota: Groq rechaza con HTTP 400 cualquier peticion que use response_format
# json_object si la palabra "json" no aparece LITERALMENTE en algun mensaje.
# No basta con mostrar un ejemplo entre llaves. Si tocas estos prompts,
# comproba que la palabra siga ahi.


def parsear_preguntas(crudo: str) -> list:
    """Extrae las preguntas aunque el JSON venga cortado.

    Un JSON truncado a mitad de la septima pregunta sigue conteniendo seis
    preguntas perfectamente formadas. Tirar el video entero por eso es
    desperdiciar una llamada cara: en la corrida de 30 videos se perdieron 6
    completos --el 20 %-- por este motivo.

    Primero se intenta el parseo normal. Si falla, se recorren las llaves
    contando anidamiento y se rescata cada objeto {...} completo del array,
    descartando el ultimo si quedo a medias.
    """
    try:
        return json.loads(crudo).get("preguntas", [])
    except json.JSONDecodeError:
        pass

    # Pila de posiciones de apertura: hay que capturar los objetos ANIDADOS
    # (cada pregunta) y no solo el envolvente. Con un simple contador de
    # profundidad, el `{` del objeto exterior desplaza todo y las preguntas
    # nunca vuelven a profundidad cero.
    preguntas, pila, en_cadena, escape = [], [], False, False
    for i, ch in enumerate(crudo):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            en_cadena = not en_cadena
            continue
        if en_cadena:
            continue
        if ch == "{":
            pila.append(i)
        elif ch == "}" and pila:
            ini = pila.pop()
            try:
                obj = json.loads(crudo[ini:i + 1])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "pregunta" in obj and "opciones" in obj:
                preguntas.append(obj)
    return preguntas


def construir_prompt_generador(video: dict, transcripcion: str) -> list:
    return [
        {"role": "system", "content": SISTEMA_GENERADOR},
        {"role": "user", "content": (
            f"TITULO: {video['title']}\n"
            f"CANAL: {video['channel']}\n\n"
            f"TRANSCRIPCION:\n{transcripcion}\n\n"
            f"Genera exactamente {N_PREGUNTAS} preguntas."
        )},
    ]


def construir_prompt_control(video: dict, pregunta: dict) -> list:
    opciones = "\n".join(f"{i}. {o}" for i, o in enumerate(pregunta["opciones"]))
    return [
        {"role": "system", "content": SISTEMA_CONTROL},
        {"role": "user", "content": (
            f"TITULO DEL VIDEO: {video['title']}\n"
            f"CANAL: {video['channel']}\n\n"
            f"PREGUNTA: {pregunta['pregunta']}\n{opciones}"
        )},
    ]


# ---------------------------------------------------------------------------
# Proceso por video
# ---------------------------------------------------------------------------

def procesar_video(groq: "ClienteLLM", video: dict, rng: random.Random,
                   max_palabras: int = MAX_PALABRAS,
                   control: "ClienteLLM" = None) -> dict:
    # POR QUE EL CONTROL PUEDE SER OTRO MODELO.
    # Si el mismo modelo genera la pregunta y despues intenta contestarla sin
    # la transcripcion, el control esta contaminado: reconoce su propia forma
    # de escribir. Las pistas que deja al redactar (la correcta mas larga, el
    # distractor puesto por compromiso) son suyas, y las lee mejor que nadie.
    # Un modelo distinto y de otro proveedor no comparte esos tics, asi que
    # mide lo que se quiere medir: si la pregunta es adivinable para alguien
    # que no vio el video.
    control = control or groq
    transcripcion, recortada = recortar_transcripcion(video["transcript"], max_palabras)
    norm = normalizar(video["transcript"])   # el control se hace contra el TEXTO COMPLETO

    resultado = {
        "content_item_id": video["id"],
        "external_id": video["external_id"],
        "titulo": video["title"],
        "canal": video["channel"],
        "formato": video["formato"],
        "n_palabras": video["transcript_word_count"],
        "transcripcion_recortada": recortada,
        "modelo": groq.modelo,
        "modelo_control": control.modelo,
        "control_independiente": control.modelo != groq.modelo,
        "version": VERSION,
        "generado_at": datetime.now(timezone.utc).isoformat(),
        "preguntas": [],
        "error": None,
    }

    try:
        crudo = groq.pedir(construir_prompt_generador(video, transcripcion), temperatura=0.4)
        preguntas = parsear_preguntas(crudo)
        if not preguntas:
            raise ValueError("no se pudo extraer ninguna pregunta de la respuesta")
    except Exception as e:
        resultado["error"] = f"generacion: {e}"
        return resultado

    for p in preguntas:
        registro = {
            "pregunta": (p.get("pregunta") or "").strip(),
            "opciones": p.get("opciones") or [],
            "cita": (p.get("cita") or "").strip(),
            "tipo": p.get("tipo", "?"),
            "anclada": False,
            "motivo_anclaje": None,
            "justificada": None,
            "motivo_justificacion": None,
            "equilibrada": None,
            "motivo_equilibrio": None,
            "linea_base_acerto": None,
            "dificil": None,
            "trivial": None,
            "control_eleccion": None,
            "control_seguridad": None,
            "sobrevive": False,
            "descarte": None,
        }

        # --- forma ---
        if len(registro["opciones"]) != N_OPCIONES or not registro["pregunta"]:
            registro["descarte"] = "formato_invalido"
            resultado["preguntas"].append(registro)
            continue
        if len({normalizar(o) for o in registro["opciones"]}) != N_OPCIONES:
            registro["descarte"] = "opciones_duplicadas"
            resultado["preguntas"].append(registro)
            continue
        try:
            idx = int(p.get("correcta"))
            texto_correcto = registro["opciones"][idx]
        except (TypeError, ValueError, IndexError):
            registro["descarte"] = "indice_correcto_invalido"
            resultado["preguntas"].append(registro)
            continue

        # --- barajar ---
        # Los generadores tienden a poner la respuesta correcta en la primera
        # posicion. Si no se baraja, el control puede acertar por posicion en
        # vez de por conocimiento, y el filtro mediria el sesgo del modelo.
        rng.shuffle(registro["opciones"])
        registro["correcta"] = registro["opciones"].index(texto_correcto)

        # --- control 1: anclaje (la cita existe) ---
        ok, motivo = cita_esta_en_transcripcion(registro["cita"], norm)
        registro["anclada"] = ok
        registro["motivo_anclaje"] = motivo
        if not ok:
            registro["descarte"] = "cita_no_verificable"
            resultado["preguntas"].append(registro)
            continue

        # --- control 2: suficiencia (la cita respalda la respuesta) ---
        ok, motivo = respuesta_esta_en_cita(texto_correcto, registro["cita"],
                                            registro["tipo"])
        registro["justificada"] = ok
        registro["motivo_justificacion"] = motivo
        if not ok:
            registro["descarte"] = "cita_no_justifica"
            resultado["preguntas"].append(registro)
            continue

        # --- control 2c: que la correcta no se delate por su forma ---
        ok, motivo = equilibrio_opciones(registro["opciones"], registro["correcta"])
        registro["equilibrada"] = ok
        registro["motivo_equilibrio"] = motivo
        if not ok:
            registro["descarte"] = "opciones_desbalanceadas"
            resultado["preguntas"].append(registro)
            continue

        # --- control 2b: que no sea una pregunta sobre el anuncio ---
        if cita_es_publicidad(registro["cita"]):
            registro["descarte"] = "pregunta_sobre_publicidad"
            resultado["preguntas"].append(registro)
            continue

        # --- control 3: trivialidad ---
        time.sleep(PAUSA_SEGUNDOS)
        try:
            crudo = control.pedir(construir_prompt_control(video, registro),
                                  temperatura=0.0, max_salida=MAX_SALIDA_CONTROL)
            ctrl = json.loads(crudo)
            eleccion = int(ctrl.get("eleccion", -1))
            registro["control_eleccion"] = eleccion
            registro["control_seguridad"] = ctrl.get("seguridad")
            registro["trivial"] = (eleccion == registro["correcta"])
        except Exception as e:
            registro["descarte"] = f"control_fallo: {e}"
            resultado["preguntas"].append(registro)
            continue

        # LA TRIVIALIDAD YA NO DESCARTA (v1.1).
        #
        # Sobre temas de conocimiento publico -- politica, historia del arte,
        # actualidad -- ninguna pregunta bien construida es del todo
        # inadivinable: si los cuatro distractores son plausibles y del mismo
        # tipo, lo unico que queda para discriminar es cual es VERDAD en el
        # mundo, y eso el modelo de control lo sabe. Descartar por eso dejaba
        # 1 pregunta utilizable por video y tiraba las otras cinco.
        #
        # No hace falta que cada item sea inadivinable: hace falta CONOCER la
        # tasa de acierto sin exposicion y descontarla. El control ya da ese
        # dato pregunta por pregunta y sale gratis. Asi que se guarda como
        # linea de base en vez de usarse como filtro binario.
        #
        # La retencion se puede calcular entonces de dos maneras, y conviene
        # informar las dos:
        #   - sobre el SUBCONJUNTO DIFICIL (los items que la linea de base
        #     fallo): interpretacion directa, n mas chico;
        #   - sobre TODOS los items descontando la linea de base: usa todo el
        #     material, al precio de asumir que la linea de base del modelo
        #     aproxima la de la persona.
        registro["linea_base_acerto"] = registro["trivial"]
        registro["dificil"] = not registro["trivial"]
        registro["sobrevive"] = True

        resultado["preguntas"].append(registro)

    return resultado


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

CONSULTA = """
select ci.id, ci.external_id, ci.title, ci.channel, ci.transcript,
       ci.transcript_word_count, ci.duration_seconds, f.formato
from content_items ci
join content_features f on f.content_item_id = ci.id
where f.apto
  and (%(formato)s = 'todos' or f.formato = %(formato)s)
  and ci.corpus = %(corpus)s
  and ci.transcript is not null
  and ci.transcript_word_count >= %(min_palabras)s
order by ci.transcript_word_count desc
"""


def traer_videos(dsn: str, formato: str, corpus: str, min_palabras: int) -> list:
    import psycopg2
    import psycopg2.extras
    with psycopg2.connect(dsn, connect_timeout=20) as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(CONSULTA, {"formato": formato, "corpus": corpus,
                                   "min_palabras": min_palabras})
            return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------

def escribir_informe(resultados: list, ruta: Path, modelo: str, segundos: float) -> None:
    todas = [p for r in resultados for p in r["preguntas"]]
    n = len(todas)
    ancladas = [p for p in todas if p["anclada"]]
    justificadas = [p for p in todas if p.get("justificada")]
    evaluadas = [p for p in todas if p["trivial"] is not None]
    triviales = [p for p in evaluadas if p["trivial"]]
    vivas = [p for p in todas if p["sobrevive"]]
    con_error = [r for r in resultados if r["error"]]

    def pct(a, b):
        return f"{100.0 * a / b:.0f} %" if b else "n/d"

    lineas = [
        "# Piloto de quiz de retencion -- informe",
        "",
        f"Generado {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · modelo `{modelo}` · "
        f"{segundos / 60:.1f} min de ejecucion · version `{VERSION}`",
        "",
        "## 1. Que se midio",
        "",
        "Cada pregunta pasa **tres filtros de descarte** y despues se le mide una **linea",
        "de base**. Los filtros: **anclaje** (la cita existe de verdad en la transcripcion:",
        "control de invencion), **suficiencia** (la cita respalda la respuesta, con umbral",
        "distinto segun el tipo de pregunta) y **equilibrio** (que la correcta no se delate",
        "por su forma: unidad, magnitud o longitud).",
        "",
        "La **linea de base** no descarta. Un modelo distinto del que genero las preguntas",
        "intenta contestarlas sin la transcripcion, viendo solo lo que veria alguien que paso",
        "por el titulo. Su acierto es el suelo contra el que hay que leer la retencion humana.",
        "",
        "Por que no se descarta lo adivinable: sobre temas de conocimiento publico ninguna",
        "pregunta bien construida es del todo inadivinable, porque si los cuatro distractores",
        "son plausibles y del mismo tipo, lo unico que discrimina es cual es verdad en el",
        "mundo -- y eso el modelo lo sabe. **No hace falta que cada item sea inadivinable:",
        "hace falta conocer la tasa de acierto sin exposicion y descontarla.**",
        "",
        "## 2. Numeros",
        "",
        "| | n | sobre el total |",
        "|---|---:|---:|",
        f"| Videos procesados | {len(resultados)} | |",
        f"| Videos que fallaron por completo | {len(con_error)} | {pct(len(con_error), len(resultados))} |",
        f"| Preguntas generadas | {n} | 100 % |",
        f"| Con cita verificable (existe) | {len(ancladas)} | {pct(len(ancladas), n)} |",
        f"| Cuya cita justifica la respuesta | {len(justificadas)} | {pct(len(justificadas), n)} |",
        f"| **Utilizables** (pasan los tres filtros) | **{len(vivas)}** | **{pct(len(vivas), n)}** |",
        "",
        f"Preguntas utilizables por video: {len(vivas) / len(resultados):.1f} de {N_PREGUNTAS} generadas."
        if resultados else "",
        "",
        "### Linea de base (sin ver el video)",
        "",
        "| | n | |",
        "|---|---:|---:|",
        f"| Items con linea de base medida | {len(evaluadas)} | |",
        f"| La linea de base acerto | {len(triviales)} | {pct(len(triviales), len(evaluadas))} |",
        f"| **Subconjunto dificil** (la linea de base fallo) | **{len(evaluadas) - len(triviales)}** | "
        f"{pct(len(evaluadas) - len(triviales), len(evaluadas))} |",
        "",
        "Referencia: con cuatro opciones el azar acierta el 25 %. Una linea de base muy por",
        "encima indica que el tema es de conocimiento publico, no que la pregunta este mal.",
        "",
        "**Como calcular la retencion con esto, de dos formas complementarias:**",
        "",
        "1. *Sobre el subconjunto dificil*: proporcion de aciertos de la persona entre los",
        f"   {len(evaluadas) - len(triviales)} items que la linea de base fallo. Interpretacion directa, n mas chico.",
        "2. *Sobre todos los items, descontando la base*: `(acierto_persona - acierto_base) /",
        "   (1 - acierto_base)`, la correccion clasica por adivinacion. Usa todo el material,",
        "   al precio de asumir que la linea de base del modelo aproxima la de la persona.",
        "",
        "Informar las dos y compararlas es en si mismo un resultado: si divergen mucho, la",
        "linea de base del modelo no representa bien a la persona.",
        "",
        "### Motivos de descarte",
        "",
        "| motivo | n |",
        "|---|---:|",
    ]

    motivos = {}
    for p in todas:
        if p["descarte"]:
            motivos[p["descarte"].split(":")[0]] = motivos.get(p["descarte"].split(":")[0], 0) + 1
    for m, k in sorted(motivos.items(), key=lambda x: -x[1]):
        lineas.append(f"| {m} | {k} |")

    # Reparto por tipo: si sale todo "dato", el quiz mide memoria de detalles
    # y no comprension, por bien que se vean los porcentajes de arriba.
    tipos = {}
    for p in todas:
        tipos[p["tipo"]] = tipos.get(p["tipo"], 0) + 1
    lineas += ["", "### Tipo de pregunta", "", "| tipo | generadas | sobreviven |", "|---|---:|---:|"]
    for t, k in sorted(tipos.items(), key=lambda x: -x[1]):
        vivos_t = sum(1 for p in todas if p["tipo"] == t and p["sobrevive"])
        lineas.append(f"| {t} | {k} | {vivos_t} |")

    lineas += ["", "## 3. Ejemplos", ""]

    def bloque(p, titulo_video, encabezado):
        out = [f"**{encabezado}** — _{titulo_video}_", "", f"> {p['pregunta']}", ""]
        for i, o in enumerate(p["opciones"]):
            marca = " ✔" if i == p.get("correcta") else ""
            out.append(f"{i}. {o}{marca}")
        out += ["", f"Cita ({p['motivo_anclaje']}): «{p['cita']}»"]
        if p["trivial"] is not None:
            out.append(f"Control sin video: eligio {p['control_eleccion']} "
                       f"(seguridad {p['control_seguridad']}) → "
                       f"{'ACERTO, descartada' if p['trivial'] else 'fallo, sobrevive'}")
        if p["descarte"]:
            out.append(f"Descarte: `{p['descarte']}`")
        out.append("")
        return out

    mostrados = 0
    for r in resultados:
        for p in r["preguntas"]:
            if p["sobrevive"] and mostrados < 3:
                lineas += bloque(p, r["titulo"], "SOBREVIVE")
                mostrados += 1
    mostrados = 0
    for r in resultados:
        for p in r["preguntas"]:
            if p["descarte"] and mostrados < 3:
                lineas += bloque(p, r["titulo"], "DESCARTADA")
                mostrados += 1

    lineas += [
        "## 4. Como leer esto",
        "",
        "Lo que decide si la funcionalidad sigue adelante no es el numero de preguntas",
        "generadas sino el de **supervivientes por video**. Con menos de dos por video no",
        "hay quiz posible: no alcanza para distinguir a quien retuvo de quien no.",
        "",
        "Una tasa de trivialidad muy por encima del 25 % significa que el generador esta",
        "haciendo preguntas de cultura general disfrazadas, y hay que endurecer el prompt.",
        "Muy por debajo del 25 % tambien es sospechoso: sugiere distractores tan raros que",
        "el control los descarta por absurdos, y entonces la pregunta tampoco discrimina.",
        "",
        "Las preguntas de este piloto **no estan revisadas por una persona**. Antes de",
        "usarlas para medir nada hay que leerlas: el control automatico filtra invencion y",
        "trivialidad, no ambiguedad ni preguntas mal planteadas.",
    ]

    ruta.write_text("\n".join(lineas), encoding="utf-8")


def escribir_csv(resultados: list, ruta: Path) -> None:
    import csv
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["content_item_id", "external_id", "titulo", "formato", "n_palabras",
                    "tipo", "pregunta", "op0", "op1", "op2", "op3", "correcta",
                    "anclada", "motivo_anclaje", "linea_base_acerto", "dificil",
                    "control_seguridad", "utilizable", "descarte"])
        for r in resultados:
            for p in r["preguntas"]:
                ops = (p["opciones"] + ["", "", "", ""])[:4]
                w.writerow([r["content_item_id"], r["external_id"], r["titulo"],
                            r["formato"], r["n_palabras"], p["tipo"], p["pregunta"],
                            *ops, p.get("correcta", ""), p["anclada"], p["motivo_anclaje"],
                            p.get("linea_base_acerto"), p.get("dificil"),
                            p.get("control_seguridad"), p["sobrevive"],
                            p["descarte"] or ""])


# ---------------------------------------------------------------------------

def recontrolar(control: "ClienteLLM", resultados: list) -> list:
    """Rehace SOLO el control de trivialidad sobre preguntas ya generadas.

    Por que existe: comparar dos modelos de control regenerando las preguntas
    no compara nada. El generador escribe preguntas distintas en cada corrida,
    asi que cambiarian dos cosas a la vez y el numero no seria atribuible a
    ninguna. Aca las preguntas quedan CONGELADAS y lo unico que se mueve es
    quien intenta adivinarlas.

    Es ademas barato: no se manda ninguna transcripcion, solo la pregunta y
    sus cuatro opciones (~700 tokens de salida por llamada).

    Se re-controlan las preguntas que en su momento LLEGARON al control; las
    descartadas antes (cita inventada, opciones desbalanceadas, publicidad)
    siguen descartadas: el control no las rescata.
    """
    for r in resultados:
        video = {"title": r["titulo"], "channel": r["canal"]}
        r["modelo_control_previo"] = r.get("modelo_control")
        r["modelo_control"] = control.modelo
        r["control_independiente"] = control.modelo != r.get("modelo")
        for p in r["preguntas"]:
            if p.get("trivial") is None or p.get("correcta") is None:
                continue          # nunca llego al control: no se toca
            p["trivial_previo"] = p["trivial"]
            p["control_seguridad_previa"] = p.get("control_seguridad")
            try:
                ctrl = json.loads(control.pedir(construir_prompt_control(video, p),
                                                temperatura=0.0,
                                                max_salida=MAX_SALIDA_CONTROL))
                eleccion = int(ctrl.get("eleccion", -1))
                p["control_eleccion"] = eleccion
                p["control_seguridad"] = ctrl.get("seguridad")
                p["trivial"] = (eleccion == p["correcta"])
            except Exception as e:
                p["descarte"] = f"control_fallo: {e}"
                p["sobrevive"] = False
                continue
            p["linea_base_acerto"] = p["trivial"]
            p["dificil"] = not p["trivial"]
            p["sobrevive"] = True
            p["descarte"] = None
            time.sleep(PAUSA_SEGUNDOS)
        vivas = sum(1 for p in r["preguntas"] if p["sobrevive"])
        antes = sum(1 for p in r["preguntas"] if p.get("trivial_previo") is False)
        print(f"  {r['titulo'][:50]}: {antes} -> {vivas} supervivientes")
    return resultados


def main() -> int:
    global N_PREGUNTAS, PAUSA_SEGUNDOS
    ap = argparse.ArgumentParser(description="Piloto de generacion de quiz de retencion")
    ap.add_argument("--proveedor-control", default=None, choices=["gemini", "groq"],
                    help="proveedor del CONTROL de trivialidad. Si se deja vacio se usa "
                         "el mismo que genera, lo cual contamina el control: un modelo "
                         "reconoce su propia forma de escribir. Recomendado: el otro.")
    ap.add_argument("--modelo-control", default=None,
                    help="modelo concreto para el control")
    ap.add_argument("--recontrolar", default=None, metavar="ETIQUETA",
                    help="no generar nada: leer docs/quiz_piloto_<ETIQUETA>.json y rehacer "
                         "solo el control de trivialidad con el modelo de control indicado. "
                         "Aisla la variable: las preguntas quedan congeladas.")
    ap.add_argument("--proveedor", default="gemini", choices=["gemini", "groq"],
                    help="que API usar (defecto gemini: ~30x mas cupo/min que groq, "
                         "asi entra la transcripcion entera sin recortar)")
    ap.add_argument("--max", type=int, default=0, help="cuantos videos procesar (0 = todos)")
    ap.add_argument("--formato", default="informativo",
                    help="informativo | practico_personal | entretenimiento | "
                         "deporte_gaming | todos. El defecto deja fuera 42 de los 79 "
                         "videos del historial: con 'todos' el formato pasa a ser una "
                         "variable con variacion real en vez de una constante.")
    ap.add_argument("--corpus", default="historial")
    ap.add_argument("--min-palabras", type=int, default=400,
                    help="por debajo de esto no hay material para 4 preguntas")
    ap.add_argument("--modelo", default=None,
                    help="forzar un modelo concreto del proveedor elegido")
    ap.add_argument("--max-palabras", type=int, default=0,
                    help="palabras de transcripcion por video (0 = automatico: la "
                         "transcripcion entera en gemini, "
                         f"{MAX_PALABRAS} en groq); bajarlo si el cupo por minuto no da")
    ap.add_argument("--limites", action="store_true",
                    help="preguntarle a la API cual es TU cupo real y estimar el piloto")
    ap.add_argument("--reanudar", action="store_true",
                    help="saltar los videos que ya esten en el json de salida")
    ap.add_argument("--preguntas", type=int, default=N_PREGUNTAS,
                    help=f"preguntas a generar por video (defecto {N_PREGUNTAS})")
    ap.add_argument("--etiqueta", default="",
                    help="sufijo para los archivos de salida, p.ej. --etiqueta v2 escribe "
                         "quiz_piloto_v2.json. Sirve para comparar versiones del prompt "
                         "sobre los MISMOS videos sin pisar la corrida anterior.")
    ap.add_argument("--semilla", type=int, default=20260814,
                    help="semilla del barajado, para que el piloto sea reproducible")
    ap.add_argument("--dry-run", action="store_true",
                    help="listar candidatos sin llamar a la API")
    ap.add_argument("--ignorar-verificacion", action="store_true",
                    help="no filtrar por docs/formato_verificado.json")
    ap.add_argument("--esfuerzo", default=REASONING_EFFORT,
                    choices=["low", "medium", "high", "none"],
                    help=f"reasoning_effort del modelo (defecto {REASONING_EFFORT}); "
                         "'none' lo omite. Mas esfuerzo = mejores distractores pero "
                         "muchos mas tokens")
    args = ap.parse_args()

    N_PREGUNTAS = args.preguntas
    sufijo = f"_{args.etiqueta}" if args.etiqueta else ""

    cfg = PROVEEDORES[args.proveedor]
    # El cuello de botella cambia con el proveedor: en Groq son los tokens/min,
    # en Gemini free son las PETICIONES/min. La pausa entre llamadas sale de ahi.
    PAUSA_SEGUNDOS = cfg["pausa"]
    # En Gemini el cupo por minuto alcanza para mandar la transcripcion entera,
    # asi que el recorte --que sesgaba las preguntas hacia lo mas recordado-- se
    # apaga por defecto. En Groq se mantiene el tope historico.
    if not args.max_palabras:
        args.max_palabras = 1_000_000 if args.proveedor == "gemini" else MAX_PALABRAS

    env = RAIZ / "backend" / ".env"
    try:
        from dotenv import load_dotenv
        load_dotenv(env)
    except ImportError:
        pass

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print(f"No hay DATABASE_URL. Ponela en {env}")
        return 2

    print(f"Leyendo candidatos: formato={args.formato} corpus={args.corpus} "
          f"min_palabras={args.min_palabras}")
    videos = traer_videos(dsn, args.formato, args.corpus, args.min_palabras)

    # Filtro de clasificacion: se saltan los videos que verificar_formato.py
    # marco como "posible clasificacion diferente". La etiqueta NO se corrige
    # -- esto es una decision sobre que datos usar, no un cambio de dato.
    # Nota honesta sobre el criterio: se excluye TODO desacuerdo, no solo los
    # "de confianza alta". Con una sola pasada el modelo declara su propia
    # confianza, y sobre 79 videos declaro "alta" las 79 veces: el campo no
    # discrimina. Se deja el filtro como esta, pero llamandolo por su nombre.
    verif = DOCS / "formato_verificado.json"
    if verif.exists() and not args.ignorar_verificacion:
        marcados = {}
        for d in json.loads(verif.read_text(encoding="utf-8")):
            if d.get("formato_observado") and d["formato_observado"] != d["formato"]:
                marcados[d["content_item_id"]] = d
        fuera = [v for v in videos if v["id"] in marcados]
        for v in fuera:
            m = marcados[v["id"]]
            print(f"  SALTEADO [{v['id']}] {v['title'][:45]} — el modelo lo ve como "
                  f"'{m['formato_observado']}', no '{m['formato']}'")
        videos = [v for v in videos if v["id"] not in marcados]
    elif not verif.exists():
        print("  (sin formato_verificado.json: no se filtra por clasificacion; "
              "corre verificar_formato.py)")

    if args.max and args.max < len(videos):
        # La consulta ordena por palabras descendente. Quedarse con los N
        # primeros daria los N videos mas largos, que son el caso mas facil
        # para generar preguntas: una muestra asi hace parecer que la
        # funcionalidad anda mejor de lo que anda. Se reparten a lo largo de
        # todo el rango de duracion.
        paso = len(videos) / args.max
        videos = [videos[int(i * paso)] for i in range(args.max)]
    print(f"  {len(videos)} videos")
    if not videos:
        print("Nada que hacer.")
        return 0

    if args.dry_run:
        print(f"\n{'id':>6}  {'palabras':>8}  titulo")
        for v in videos:
            print(f"{v['id']:>6}  {v['transcript_word_count']:>8}  {v['title'][:70]}")
        coste = len(videos) * (1 + N_PREGUNTAS)
        palabras = sum(min(v["transcript_word_count"], args.max_palabras) for v in videos)
        tokens = int(palabras * 1.4) + len(videos) * 1200 + coste * 350
        print(f"\nEjecutar de verdad son ~{coste} llamadas y ~{tokens:,} tokens "
              f"(con --max-palabras {args.max_palabras}), mas ~{coste * PAUSA_SEGUNDOS / 60:.0f} "
              f"min de pausas.")
        print("Lo que limita en el plan gratuito son los TOKENS por minuto, no las "
              "llamadas.\nCorre --limites para ver tu cupo real.")
        return 0

    api_key = next((os.getenv(k) for k in cfg["claves"] if os.getenv(k)), None)
    if not api_key:
        donde = {"gemini": "aistudio.google.com/apikey",
                 "groq": "console.groq.com"}[args.proveedor]
        print(f"No hay {' ni '.join(cfg['claves'])}. Sacala gratis en {donde} "
              f"y ponela en {env}")
        return 2

    groq = ClienteLLM(api_key, cfg, args.modelo)
    groq.esfuerzo = None if args.esfuerzo == "none" else args.esfuerzo
    # Sonda de una llamada minuscula: sirve para APRENDER el cupo por minuto
    # del modelo antes de la primera peticion de verdad. Sin esto, la primera
    # generacion se calcularia contra el valor por defecto y podria chocar.
    try:
        groq.pedir([{"role": "user", "content": "Responde solo con el json {\"ok\":1}"}],
                   temperatura=0.0, max_salida=MIN_SALIDA)
    except Exception as e:
        print(f"AVISO  la sonda de cupo fallo ({e}); se asume {TPM_POR_DEFECTO} tokens/min")
    print(f"Modelo: {groq.modelo} · esfuerzo {groq.esfuerzo} · "
          f"cupo {groq.tpm} tokens/min")
    # Cliente separado para el control de trivialidad (ver procesar_video).
    control = groq
    if args.proveedor_control and args.proveedor_control != args.proveedor:
        cfg_c = PROVEEDORES[args.proveedor_control]
        clave_c = next((os.getenv(k) for k in cfg_c["claves"] if os.getenv(k)), None)
        if not clave_c:
            print(f"AVISO  no hay clave para el proveedor de control "
                  f"({' ni '.join(cfg_c['claves'])}); el control lo hace el mismo "
                  f"modelo que genera, y eso contamina la medida.")
        else:
            control = ClienteLLM(clave_c, cfg_c, args.modelo_control)
            control.esfuerzo = None
            print(f"Control independiente: {control.modelo} ({args.proveedor_control})")
    elif args.modelo_control and args.modelo_control != groq.modelo:
        control = ClienteLLM(api_key, cfg, args.modelo_control)
        control.esfuerzo = None
        print(f"Control independiente: {control.modelo} ({args.proveedor})")
    else:
        print("AVISO  el control lo hace el MISMO modelo que genera las preguntas. "
              "Mide de menos:\n"
              "       reconoce sus propios tics de redaccion. Usa "
              "--proveedor-control para separarlos.")

    rng = random.Random(args.semilla)

    if args.limites:
        # La sonda de arriba ya leyo las cabeceras: aca solo se informan.
        print("\nTu cupo real, segun la API:")
        if cfg["cabeceras_cupo"]:
            print(groq.describir_limites())
        else:
            print(f"  {args.proveedor} no expone cabeceras x-ratelimit-*.")
            print(f"  Cupo asumido: {cfg['tpm']:,} tokens/min. En el free tier de Gemini lo "
                  f"que ata NO son los tokens (sobran) sino las PETICIONES: ~10/min y "
                  f"~500/dia en 2.5 Flash.")
            print(f"  El piloto son ~{len(videos) * (1 + N_PREGUNTAS)} llamadas: si supera "
                  f"las 500/dia, cortas y segui al dia siguiente con --reanudar.")

        # 1 palabra ~ 1,4 tokens en espanol con estos tokenizadores; se suma el
        # texto fijo del prompt y la respuesta generada.
        palabras = sum(min(v["transcript_word_count"], args.max_palabras) for v in videos)
        tok_gen = int(palabras * 1.4) + len(videos) * 1200
        tok_ctl = len(videos) * N_PREGUNTAS * 350
        total = tok_gen + tok_ctl
        print(f"\nEl piloto sobre {len(videos)} videos con --max-palabras {args.max_palabras}:")
        print(f"  ~{total:,} tokens en total ({tok_gen:,} de generacion + {tok_ctl:,} de control)")
        print(f"  ~{len(videos) * (1 + N_PREGUNTAS)} llamadas")

        try:
            tpm = float(groq.limites.get("x-ratelimit-limit-tokens", 0))
        except ValueError:
            tpm = 0
        if tpm:
            print(f"\n  Tu ventana es de {tpm:,.0f} tokens. El piloto necesita "
                  f"~{total / tpm:.1f} ventanas.")
            mayor = int(min(max(v['transcript_word_count'] for v in videos),
                            args.max_palabras) * 1.4) + 1200
            if mayor > tpm:
                print(f"  AVISO: el video mas largo pide ~{mayor:,} tokens en UNA peticion y "
                      f"no entra en la ventana. Baja --max-palabras a ~{int(tpm / 1.4 * 0.7):,}.")
            else:
                print("  Cada peticion entra sola en la ventana: el script solo tendra que esperar.")
        print("\nEl script se autorregula: lee estas cabeceras en cada respuesta y espera "
              "cuando el cupo se acaba. Si el limite es diario, corta y sigue con --reanudar.")
        return 0

    # Reanudar: no se vuelve a pagar por lo ya generado. Importa de verdad si
    # el limite que te frena es diario.
    if args.recontrolar:
        origen = SALIDA / f"quiz_piloto_{args.recontrolar}.json"
        if not origen.exists():
            print(f"No existe {origen}")
            return 2
        if control is groq:
            print("ERROR  --recontrolar sin un control distinto no tiene sentido: "
                  "compararias\n       un modelo consigo mismo. Usa "
                  "--proveedor-control y/o --modelo-control.")
            return 2
        previos = json.loads(origen.read_text(encoding="utf-8"))
        print(f"Re-controlando {len(previos)} videos de {origen.name} "
              f"con {control.modelo}")
        inicio = time.time()
        resultados = recontrolar(control, previos)
        SALIDA.mkdir(parents=True, exist_ok=True)
        (SALIDA / f"quiz_piloto{sufijo}.json").write_text(
            json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
        escribir_csv(resultados, SALIDA / f"quiz_piloto{sufijo}.csv")
        escribir_informe(resultados, SALIDA / f"quiz_piloto{sufijo}_informe.md",
                         groq.modelo, time.time() - inicio)
        todas = [p for r in resultados for p in r["preguntas"]]
        vivas = sum(1 for p in todas if p["sobrevive"])
        print(f"\n{vivas} de {len(todas)} sobreviven "
              f"({vivas / len(resultados):.1f} por video)")
        print(f"Informe: docs/quiz_piloto/quiz_piloto{sufijo}_informe.md")
        return 0

    salida_json = SALIDA / f"quiz_piloto{sufijo}.json"
    hechos = {}
    if args.reanudar and salida_json.exists():
        for r in json.loads(salida_json.read_text(encoding="utf-8")):
            if not r.get("error"):
                hechos[r["content_item_id"]] = r
        antes = len(videos)
        videos = [v for v in videos if v["id"] not in hechos]
        print(f"Reanudando: {len(hechos)} ya hechos, quedan {len(videos)} de {antes}")

    inicio = time.time()
    SALIDA.mkdir(parents=True, exist_ok=True)
    resultados = list(hechos.values())

    def guardar():
        salida_json.write_text(json.dumps(resultados, ensure_ascii=False, indent=2),
                               encoding="utf-8")

    for i, v in enumerate(videos, 1):
        print(f"[{i}/{len(videos)}] {v['title'][:60]} ({v['transcript_word_count']} palabras)")
        try:
            r = procesar_video(groq, v, rng, args.max_palabras, control)
        except KeyboardInterrupt:
            print("\nInterrumpido. Lo hecho queda guardado; segui con --reanudar")
            break
        vivas = sum(1 for p in r["preguntas"] if p["sobrevive"])
        if r["error"]:
            print(f"       FALLO  {r['error']}")
        else:
            print(f"       {len(r['preguntas'])} generadas, {vivas} sobreviven")

        # El script proyecta su propio final en vez de confiar en una
        # estimacion hecha de antemano. Los limites de tasa reales no se
        # deducen de las cabeceras: se observan corriendo. Si el ritmo no te
        # sirve, cortas con Ctrl+C y segui con --reanudar.
        transcurrido = time.time() - inicio
        ritmo = transcurrido / i
        faltan = ritmo * (len(videos) - i)
        print(f"       ritmo {ritmo/60:.1f} min/video · "
              f"{groq.esperas/60:.0f} min esperando cupo · "
              f"quedan {len(videos)-i} → ~{faltan/60:.0f} min")

        resultados.append(r)
        # Se guarda despues de CADA video: si el cupo diario corta a mitad de
        # camino, no se pierde ni se vuelve a pagar lo ya generado.
        guardar()
        time.sleep(PAUSA_SEGUNDOS)

    segundos = time.time() - inicio
    guardar()
    escribir_csv(resultados, SALIDA / f"quiz_piloto{sufijo}.csv")
    escribir_informe(resultados, SALIDA / f"quiz_piloto{sufijo}_informe.md",
                     groq.modelo, segundos)

    total = sum(len(r["preguntas"]) for r in resultados)
    vivas = sum(1 for r in resultados for p in r["preguntas"] if p["sobrevive"])
    base = sum(1 for r in resultados for p in r["preguntas"] if p.get("linea_base_acerto"))
    dif = sum(1 for r in resultados for p in r["preguntas"] if p.get("dificil"))
    print("\n" + "=" * 60)
    print(f"{total} generadas · {vivas} utilizables ({100.0 * vivas / total:.0f} %) · "
          f"linea de base acerto {base} · subconjunto dificil {dif}" if total
          else "sin preguntas")
    print(f"{groq.llamadas} llamadas y {groq.tokens_usados:,} tokens "
          f"en {segundos / 60:.1f} min ({groq.esperas / 60:.1f} min esperando cupo)")
    print(f"Informe: docs/quiz_piloto/quiz_piloto{sufijo}_informe.md")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

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

VERSION = "quiz-piloto-0.1"

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELOS_URL = "https://api.groq.com/openai/v1/models"

# Preferencia de modelo, de mejor a peor para esta tarea. El primero que la
# cuenta tenga disponible es el que se usa.
#
# Por que una lista y no un nombre fijo: los proveedores retiran modelos con
# poco aviso y un nombre hardcodeado convierte el script en basura seis meses
# despues. El script pregunta que hay disponible y elige. Se imprime cual
# eligio, y queda guardado en la salida: si el dia de manana las preguntas
# cambian de calidad, se puede saber si fue por el modelo.
MODELOS_PREFERIDOS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "llama3-70b-8192",
    "mixtral-8x7b-32768",
    "llama-3.1-8b-instant",
]

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

# Cuando queden menos tokens que esto en la ventana actual, el script espera
# a que el cupo se renueve en vez de comerse un 429.
UMBRAL_TOKENS = 8000

# Un quiz de opcion multiple con 4 opciones se acierta al azar el 25 % de las
# veces. El control usa temperatura 0 y una sola pasada: no es una medida de
# probabilidad, es un filtro binario "esto era adivinable / no lo era".
N_OPCIONES = 4

RAIZ = Path(__file__).resolve().parent.parent.parent   # .../Cognitive Analysis
DOCS = RAIZ / "docs"


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


def respuesta_esta_en_cita(respuesta: str, cita: str) -> tuple:
    """Tercer control: la cita tiene que CONTENER la respuesta, no sugerirla.

    Nace de un caso real del piloto v0.1: la pregunta era "en que plataforma
    se transmite los lunes", la respuesta "YouTube", y la cita decia "los dias
    lunes a las 21 horas yo hago una transmision formal" -- que existe en la
    transcripcion y no menciona ninguna plataforma. El control de anclaje la
    daba por buena porque solo comprueba que la cita EXISTA.

    Anclar no es justificar.
    """
    r = [t for t in normalizar(respuesta).split() if t not in VACIAS and len(t) > 1]
    if not r:
        return False, "respuesta_vacia"
    c = set(normalizar(cita).split())
    presentes = [t for t in r if t in c]
    # Con una sola palabra de contenido, esa palabra tiene que estar. Con
    # varias, se admite que falte alguna: "Reabrir el estrecho de Ormud" no
    # tiene por que aparecer con el verbo conjugado igual.
    if len(presentes) >= max(1, (len(r) + 1) // 2):
        return True, f"{len(presentes)}_de_{len(r)}"
    return False, f"solo_{len(presentes)}_de_{len(r)}"


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
# Cliente de Groq
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


class Groq:
    def __init__(self, api_key: str, modelo: str = None):
        self.key = api_key
        self.sesion = requests.Session()
        self.sesion.headers.update({"Authorization": f"Bearer {api_key}"})
        self.modelo = modelo or self._elegir_modelo()
        self.llamadas = 0
        self.tokens_usados = 0
        self.limites = {}       # ultima foto de las cabeceras x-ratelimit-*
        self.esperas = 0.0      # segundos dormidos esperando cupo

    def _leer_limites(self, r) -> None:
        h = r.headers
        self.limites = {k: h[k] for k in h if k.lower().startswith("x-ratelimit")}

    def _respetar_cupo(self) -> None:
        """Espera ANTES de gastar, si el cupo restante no da para la proxima.

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
        if restantes < UMBRAL_TOKENS:
            espera = parse_duracion(self.limites.get("x-ratelimit-reset-tokens", "10s")) + 1
            print(f"       quedan {restantes:.0f} tokens de cupo; espero {espera:.0f}s")
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
            r = self.sesion.get(GROQ_MODELOS_URL, timeout=30)
            r.raise_for_status()
            disponibles = {m["id"] for m in r.json().get("data", [])}
        except Exception as e:
            print(f"AVISO  no se pudo listar modelos ({e}); se usa el primero de la lista")
            return MODELOS_PREFERIDOS[0]

        for m in MODELOS_PREFERIDOS:
            if m in disponibles:
                return m

        # ninguno de los conocidos: se elige alguno que suene a instruct grande
        candidatos = sorted(x for x in disponibles if "llama" in x or "instruct" in x)
        if candidatos:
            print(f"AVISO  ninguno de los modelos preferidos existe ya. Disponibles: {sorted(disponibles)}")
            return candidatos[-1]
        raise RuntimeError(f"No hay modelo utilizable. La cuenta ve: {sorted(disponibles)}")

    def pedir(self, mensajes: list, temperatura: float = 0.3, json_estricto: bool = True) -> str:
        cuerpo = {
            "model": self.modelo,
            "messages": mensajes,
            "temperature": temperatura,
        }
        if json_estricto:
            cuerpo["response_format"] = {"type": "json_object"}

        self._respetar_cupo()
        espera = 5
        for intento in range(1, MAX_REINTENTOS + 1):
            try:
                r = self.sesion.post(GROQ_URL, json=cuerpo, timeout=120)
            except requests.RequestException as e:
                if intento == MAX_REINTENTOS:
                    raise
                print(f"       red fallo ({e}); reintento en {espera}s")
                time.sleep(espera)
                espera *= 2
                continue

            self._leer_limites(r)

            if r.status_code == 429:
                # el limite de tasa del plan gratuito. La cabecera dice cuanto
                # esperar; si no viene, se duplica la espera.
                pausa = parse_duracion(r.headers.get("retry-after", "")) or float(
                    r.headers.get("retry-after", espera) or espera)
                print(f"       limite de tasa; espero {pausa:.0f}s")
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
                        f"HTTP {r.status_code}: la peticion no entra en tu cupo por minuto. "
                        f"Corre con --max-palabras mas bajo (proba 1500). Detalle: {detalle}")
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

REGLA 1 — LOS DISTRACTORES SON LO MAS IMPORTANTE.
Un test se rompe cuando la respuesta correcta es simplemente la opcion que mas "suena bien". Si alguien que no vio el video puede acertar eligiendo la opcion mas plausible, la pregunta no sirve.
Por eso, siempre que puedas, los tres distractores deben ser COSAS QUE SI APARECEN EN LA TRANSCRIPCION pero que NO contestan esa pregunta: otras cifras que dijo el hablante, otros nombres que menciono, otros lugares de los que hablo. Asi las cuatro opciones son igual de plausibles para quien no vio el video, y solo distingue quien recuerda cual iba con cual.
Ademas: si la respuesta es una cifra, los distractores deben ser del mismo orden de magnitud y el mismo formato (no mezcles "40.000" con "3"); si es un nombre propio, los otros tres tambien; si es una fecha, todas fechas parecidas.
Nunca hagas que la correcta sea la unica opcion "famosa" o la mas conocida del grupo.

REGLA 2 — NADA QUE SE PUEDA ADIVINAR.
Prohibido preguntar cultura general, cosas deducibles del TITULO del video, o cuya respuesta sea la unica razonable del mundo real. Si la respuesta esta en el titulo, la pregunta esta mal.

REGLA 3 — LA CITA DEBE CONTENER LA RESPUESTA.
La cita es un fragmento LITERAL y CONTIGUO de la transcripcion, copiado tal cual (no lo reescribas ni le arregles la puntuacion), de entre 8 y 30 palabras, y la respuesta correcta tiene que estar DENTRO de esa cita, no deducirse de ella. Si tu cita no contiene la respuesta, cambia la pregunta.

REGLA 4 — VARIEDAD.
No hagas solo preguntas de dato suelto. De cada seis preguntas, al menos dos deben ser de tipo "relacion" o "argumento": por que el hablante sostiene algo, que consecuencia le atribuye a que causa, que conclusion saca de que hecho. Esas miden comprension; las de dato solo miden memoria.

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

def procesar_video(groq: Groq, video: dict, rng: random.Random,
                   max_palabras: int = MAX_PALABRAS) -> dict:
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
        "version": VERSION,
        "generado_at": datetime.now(timezone.utc).isoformat(),
        "preguntas": [],
        "error": None,
    }

    try:
        crudo = groq.pedir(construir_prompt_generador(video, transcripcion), temperatura=0.4)
        datos = json.loads(crudo)
        preguntas = datos.get("preguntas", [])
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

        # --- control 2: suficiencia (la cita contiene la respuesta) ---
        ok, motivo = respuesta_esta_en_cita(texto_correcto, registro["cita"])
        registro["justificada"] = ok
        registro["motivo_justificacion"] = motivo
        if not ok:
            registro["descarte"] = "cita_no_justifica"
            resultado["preguntas"].append(registro)
            continue

        # --- control 3: trivialidad ---
        time.sleep(PAUSA_SEGUNDOS)
        try:
            crudo = groq.pedir(construir_prompt_control(video, registro), temperatura=0.0)
            ctrl = json.loads(crudo)
            eleccion = int(ctrl.get("eleccion", -1))
            registro["control_eleccion"] = eleccion
            registro["control_seguridad"] = ctrl.get("seguridad")
            registro["trivial"] = (eleccion == registro["correcta"])
        except Exception as e:
            registro["descarte"] = f"control_fallo: {e}"
            resultado["preguntas"].append(registro)
            continue

        if registro["trivial"]:
            registro["descarte"] = "contestable_sin_ver_el_video"
        else:
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
  and f.formato = %(formato)s
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
        "Cada pregunta pasa dos filtros independientes. El de **anclaje** comprueba que la",
        "cita que el modelo dice haber sacado de la transcripcion exista de verdad ahi: es",
        "el control de invencion. El de **trivialidad** hace que el mismo modelo conteste la",
        "pregunta sin la transcripcion, viendo solo titulo, canal y opciones; si acierta, la",
        "pregunta no medía retencion y se descarta. Con cuatro opciones, el azar acierta el",
        "25 %, asi que una tasa de trivialidad cercana a esa cifra indica preguntas que de",
        "verdad exigen haber visto el video.",
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
        f"| Llegaron al control de trivialidad | {len(evaluadas)} | {pct(len(evaluadas), n)} |",
        f"| Contestables sin ver el video | {len(triviales)} | {pct(len(triviales), len(evaluadas))} de las evaluadas |",
        f"| **Sobreviven** | **{len(vivas)}** | **{pct(len(vivas), n)}** |",
        "",
        f"Preguntas utiles por video: {len(vivas) / len(resultados):.1f} de {N_PREGUNTAS} generadas."
        if resultados else "",
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
                    "anclada", "motivo_anclaje", "trivial", "sobrevive", "descarte"])
        for r in resultados:
            for p in r["preguntas"]:
                ops = (p["opciones"] + ["", "", "", ""])[:4]
                w.writerow([r["content_item_id"], r["external_id"], r["titulo"],
                            r["formato"], r["n_palabras"], p["tipo"], p["pregunta"],
                            *ops, p.get("correcta", ""), p["anclada"], p["motivo_anclaje"],
                            p["trivial"], p["sobrevive"], p["descarte"] or ""])


# ---------------------------------------------------------------------------

def main() -> int:
    global N_PREGUNTAS
    ap = argparse.ArgumentParser(description="Piloto de generacion de quiz de retencion")
    ap.add_argument("--max", type=int, default=0, help="cuantos videos procesar (0 = todos)")
    ap.add_argument("--formato", default="informativo")
    ap.add_argument("--corpus", default="historial")
    ap.add_argument("--min-palabras", type=int, default=400,
                    help="por debajo de esto no hay material para 4 preguntas")
    ap.add_argument("--modelo", default=None, help="forzar un modelo de Groq")
    ap.add_argument("--max-palabras", type=int, default=MAX_PALABRAS,
                    help=f"palabras de transcripcion por video (defecto {MAX_PALABRAS}); "
                         "bajarlo si el cupo por minuto no da")
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
    args = ap.parse_args()

    N_PREGUNTAS = args.preguntas
    sufijo = f"_{args.etiqueta}" if args.etiqueta else ""

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
    verif = DOCS / "formato_verificado.json"
    if verif.exists() and not args.ignorar_verificacion:
        marcados = {}
        for d in json.loads(verif.read_text(encoding="utf-8")):
            if d.get("formato_observado") and d["formato_observado"] != d["formato"] \
                    and d.get("confianza") == "alta":
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

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print(f"No hay GROQ_API_KEY. Sacala gratis en console.groq.com y ponela en {env}")
        return 2

    groq = Groq(api_key, args.modelo)
    print(f"Modelo: {groq.modelo}")
    rng = random.Random(args.semilla)

    if args.limites:
        # Una llamada minuscula solo para leer las cabeceras. No hay que fiarse
        # de lo que diga un blog sobre "el plan gratuito": los limites son por
        # cuenta y por modelo, y cambian. Esto pregunta.
        groq.pedir([{"role": "user", "content": "Responde solo con el json {\"ok\":1}"}],
                   temperatura=0.0)
        print("\nTu cupo real, segun la API:")
        print(groq.describir_limites())

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
    salida_json = DOCS / f"quiz_piloto{sufijo}.json"
    hechos = {}
    if args.reanudar and salida_json.exists():
        for r in json.loads(salida_json.read_text(encoding="utf-8")):
            if not r.get("error"):
                hechos[r["content_item_id"]] = r
        antes = len(videos)
        videos = [v for v in videos if v["id"] not in hechos]
        print(f"Reanudando: {len(hechos)} ya hechos, quedan {len(videos)} de {antes}")

    inicio = time.time()
    DOCS.mkdir(exist_ok=True)
    resultados = list(hechos.values())

    def guardar():
        salida_json.write_text(json.dumps(resultados, ensure_ascii=False, indent=2),
                               encoding="utf-8")

    for i, v in enumerate(videos, 1):
        print(f"[{i}/{len(videos)}] {v['title'][:60]} ({v['transcript_word_count']} palabras)")
        try:
            r = procesar_video(groq, v, rng, args.max_palabras)
        except KeyboardInterrupt:
            print("\nInterrumpido. Lo hecho queda guardado; segui con --reanudar")
            break
        vivas = sum(1 for p in r["preguntas"] if p["sobrevive"])
        if r["error"]:
            print(f"       FALLO  {r['error']}")
        else:
            print(f"       {len(r['preguntas'])} generadas, {vivas} sobreviven")
        resultados.append(r)
        # Se guarda despues de CADA video: si el cupo diario corta a mitad de
        # camino, no se pierde ni se vuelve a pagar lo ya generado.
        guardar()
        time.sleep(PAUSA_SEGUNDOS)

    segundos = time.time() - inicio
    guardar()
    escribir_csv(resultados, DOCS / f"quiz_piloto{sufijo}.csv")
    escribir_informe(resultados, DOCS / f"quiz_piloto{sufijo}_informe.md",
                     groq.modelo, segundos)

    total = sum(len(r["preguntas"]) for r in resultados)
    vivas = sum(1 for r in resultados for p in r["preguntas"] if p["sobrevive"])
    print("\n" + "=" * 60)
    print(f"{total} preguntas generadas, {vivas} sobreviven "
          f"({100.0 * vivas / total:.0f} %)" if total else "sin preguntas")
    print(f"{groq.llamadas} llamadas y {groq.tokens_usados:,} tokens "
          f"en {segundos / 60:.1f} min ({groq.esperas / 60:.1f} min esperando cupo)")
    print(f"Informe: docs/quiz_piloto_informe.md")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

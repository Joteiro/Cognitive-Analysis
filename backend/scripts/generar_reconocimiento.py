#!/usr/bin/env python3
"""Genera una prueba de RECONOCIMIENTO a partir de las transcripciones.

POR QUE EXISTE
    El quiz de opcion multiple mide con 5 items por video y un azar de 0,25.
    Medido sobre los datos reales: el 90 % de la varianza de la retencion es
    ruido binomial, la fiabilidad por video es 0,097 y el techo de correlacion
    de cualquier descriptor perfecto es r = 0,31, por debajo del piso de
    deteccion (0,39 con 50 videos). El instrumento no podia ganar.

    Esta prueba cambia el formato, no la muestra:
      - 20 afirmaciones VERDADERAS, parafraseadas de la transcripcion del video
      - 20 SENUELOS, parafraseados de OTRO video del corpus de referencia que
        la persona nunca vio, de la misma categoria
      - la persona dice si cada afirmacion aparecio en el video, con confianza
      - el puntaje es d' (sensibilidad), no el acierto

    Los senuelos son afirmaciones VERDADERAS de otro video. Quien responde
    desde el conocimiento general no puede discriminar, porque las dos listas
    son ciertas; quien vio el video, si. La contaminacion por conocimiento
    previo se resuelve por construccion, no con un filtro posterior.

EL FILTRO QUE NO SE PUEDE SALTEAR
    Un senuelo sacado de otro video puede resultar verdadero TAMBIEN para el
    video objetivo (dos videos de fisica dicen los dos que la luz viaja a c).
    Si pasa, un "no" correcto se cuenta como falsa alarma y d' baja por un
    defecto del item, no de la memoria. Por eso el modelo de control revisa
    las 40 afirmaciones contra la transcripcion DEL OBJETIVO en una sola
    llamada: los objetivos tienen que quedar respaldados y los senuelos no.
    Es el filtro de anclaje de generar_quiz.py, usado en los dos sentidos.

REQUISITOS
    backend/.env con DATABASE_URL y GEMINI_API_KEY (o GROQ_API_KEY).
    pip install -r requirements-analisis.txt

SALIDA
    docs/reconocimiento/clave_no_abrir/items_<etiqueta>.json
    NO ABRAS ESE ARCHIVO: tiene la clave. Abri solo el HTML que arma
    armar_reconocimiento_html.py.

USO TIPICO
    python generar_reconocimiento.py --max 5 --etiqueta piloto \\
        --proveedor gemini --proveedor-control gemini \\
        --modelo-control gemini-2.5-flash-lite

EL CONTROL NO PUEDE SER GROQ EN EL NIVEL GRATIS
    A diferencia de generar_quiz.py --donde el control recibe solo la pregunta--
    aca recibe la TRANSCRIPCION ENTERA para juzgar el respaldo. Una transcripcion
    de 7.000 palabras son ~13.000 tokens y el cupo gratis de Groq es 8.000/min:
    no entra nunca. El script lo chequea antes de gastar una sola llamada.
"""

import argparse
import collections
import json
import math
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Se reutiliza la plomeria ya depurada de generar_quiz.py: el cliente de LLM
# con sus reintentos y su respeto de cupo, la tabla de proveedores y el
# recorte de transcripciones por ventanas. Reimplementarlo seria repetir los
# errores de API que ya estan documentados ahi.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generar_quiz import (  # noqa: E402
    ClienteLLM, PROVEEDORES, recortar_transcripcion, RAIZ, DOCS, MIN_SALIDA,
    MARGEN_TPM,
)

VERSION = "reconocimiento-1.0"

SALIDA = DOCS / "reconocimiento" / "clave_no_abrir"

N_OBJETIVOS = 20
N_SENUELOS = 20
N_CONTROL_ATENCION = 2
MARGEN = 12           # se piden de mas: entre el anti-anclaje y el filtro de
                      # nombres propios se cae unos 8 de cada 28
MIN_PALABRAS = 600
MAX_PALABRAS_PROMPT = 12000
# NO se fija un techo de salida propio: se deja el `max_salida` del proveedor
# (24000 en Gemini, 8000 en Groq). Fijarlo a mano en 8000 fue el bug que corto
# la generacion en la afirmacion 11: gemini-2.5-flash piensa antes de escribir
# y ese razonamiento sale del MISMO presupuesto, asi que se comio casi todo.

# Afirmaciones absurdas: si alguien las marca como vistas, contesto en
# automatico y esa sesion no se puede usar.
ABSURDAS = [
    "El presentador interrumpe la explicacion para anunciar que el episodio se grabo entero bajo el agua.",
    "A mitad del video el narrador confiesa que todo lo anterior lo dijo en un idioma inventado por el.",
    "El invitado aclara que su empresa cotiza en la bolsa de la Antartida desde hace catorce anos.",
    "Cerca del final se explica que los datos se obtuvieron preguntandole a un perro entrenado para leer.",
    "El conductor promete que la proxima entrega se transmitira exclusivamente en forma de olor.",
    "Se menciona que el estudio de grabacion flota permanentemente a trescientos metros de altura.",
    "El autor aclara que escribio el guion mientras dormia y que no recuerda nada de lo dicho.",
    "En un momento se aclara que todas las cifras del video estan expresadas en unidades marcianas.",
]

CONSULTA_OBJETIVOS = """
select ci.id, ci.title, ci.channel, ci.url, ci.category_name,
       ci.duration_seconds, ci.watched_at, ci.transcript,
       ci.transcript_word_count, left(ci.transcript_lang, 2) as idioma
from content_items ci
where ci.corpus = 'historial'
  and ci.watched_at is not null
  and ci.transcript is not null
  and coalesce(ci.transcript_word_count, 0) >= %(min_palabras)s
  and (%(incluir_con_quiz)s or not exists (
        select 1 from quiz_preguntas q
        where q.content_item_id = ci.id and q.utilizable))
order by ci.duration_seconds
"""

# Los senuelos salen del corpus de referencia: videos que la persona NUNCA
# vio. Si salieran de su historial podria "reconocerlos" del otro video, que
# es un error de fuente y ensucia la tasa de falsas alarmas.
#
# Se trae una MUESTRA de cada transcripcion (no la entera) porque el pool son
# ~400 videos y solo hace falta para medir de que habla cada uno.
CONSULTA_SENUELOS = """
select ci.id, ci.title, ci.category_name, ci.transcript_word_count,
       left(ci.transcript_lang, 2) as idioma,
       left(ci.transcript, 20000) as muestra
from content_items ci
where ci.corpus = 'referencia'
  and ci.watched_at is null
  and ci.transcript is not null
  and coalesce(ci.transcript_word_count, 0) >= %(min_palabras)s
order by ci.id
"""

CONSULTA_TRANSCRIPCION = """
select id, title, category_name, transcript, transcript_word_count
from content_items where id = %(id)s
"""


def traer(dsn, sql, params):
    import psycopg2
    import psycopg2.extras
    with psycopg2.connect(dsn, connect_timeout=20) as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


VACIAS = {
    "que", "los", "las", "una", "uno", "del", "con", "por", "para", "mas", "pero", "como",
    "este", "esta", "esto", "eso", "ese", "esa", "son", "fue", "hay", "muy", "todo", "toda",
    "todos", "todas", "cuando", "donde", "porque", "entonces", "tambien", "asi", "sus", "nos",
    "les", "ese", "otro", "otra", "ya", "ser", "estar", "tener", "hacer", "puede", "hace",
    "bien", "ahi", "aca", "aqui", "algo", "nada", "sin", "sobre", "entre", "desde", "hasta",
    "the", "and", "for", "you", "that", "this", "with", "have", "was", "are", "not", "but",
}


def _tokens(texto):
    from generar_quiz import normalizar
    palabras = re.findall(r"[a-z]+", normalizar(texto or ""))
    return [p for p in palabras if len(p) > 3 and p not in VACIAS]


def elegir_por_similitud(objetivo_texto, pool, usados):
    """Devuelve el video del pool mas parecido al objetivo, por coseno sobre
    TF-IDF.

    POR QUE NO ALCANZA LA CATEGORIA DE YOUTUBE
        `category_name` la declara el canal y no mira el video: 'Entertainment'
        junta un podcast de futbol con una receta de cheesecake. Si el senuelo
        es de otro tema, la persona lo descarta sin acordarse del video --"esto
        habla de cocina, el video era de futbol"-- y d' sale inflado. El
        instrumento pareceria andar midiendo reconocimiento de TEMA, que es el
        falso positivo que no nos podemos permitir.

        Emparejando por contenido real, para decir que no hay que acordarse.
    """
    cands = [p for p in pool if p["id"] not in usados]
    if not cands:
        return None, 0.0, 0.0
    docs = [_tokens(objetivo_texto)] + [_tokens(c.get("muestra") or "") for c in cands]
    df = collections.Counter()
    for d in docs:
        df.update(set(d))
    n = len(docs)
    vecs = []
    for d in docs:
        tf = collections.Counter(d)
        v = {w: (1 + math.log(c)) * math.log(n / (1 + df[w])) for w, c in tf.items() if df[w] > 1}
        norma = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({w: x / norma for w, x in v.items()})
    obj = vecs[0]
    sims = []
    for c, v in zip(cands, vecs[1:]):
        chico, grande = (obj, v) if len(obj) < len(v) else (v, obj)
        sims.append(sum(x * grande.get(w, 0.0) for w, x in chico.items()))
    i = max(range(len(sims)), key=lambda j: sims[j])
    # El coseno no tiene una escala absoluta comparable entre corpus, asi que
    # el diagnostico es RELATIVO AL POOL: cuantos desvios por encima de la
    # similitud tipica quedo el elegido. Si el mejor esta a 1,5 desvios, no
    # habia ningun video del tema y solo es el techo de una distribucion al
    # azar; a 4 o 5 desvios hay uno que habla de lo mismo.
    m = sum(sims) / len(sims)
    var = sum((x - m) ** 2 for x in sims) / max(len(sims) - 1, 1)
    sd = math.sqrt(var)
    zeta = (sims[i] - m) / sd if sd > 0 else 0.0
    return cands[i], sims[i], zeta


ABRE_FRASE = {
    "el", "la", "los", "las", "un", "una", "en", "durante", "cuando", "segun", "este", "esta",
    "cerca", "se", "al", "del", "por", "para", "si", "no", "tras", "ante", "mientras", "aunque",
    "ademas", "tambien", "antes", "despues", "hay", "uno", "dos", "tres", "muchos", "algunos",
    "su", "sus", "lo", "le", "es", "son", "fue", "cada", "todo", "toda", "todos", "todas",
}


def nombres_ausentes(texto, transcripcion_norm):
    """Nombres propios del senuelo que NO aparecen en la transcripcion objetivo.

    POR QUE ES UN TERCER FILTRO Y NO UN DETALLE
        Un senuelo que nombra el Obelisco cuando el video objetivo nunca lo
        menciona se rechaza sin recordar NADA del video: alcanza con saber de
        que iba. Eso pone un piso a d' que no es memoria. Medido en el video
        86: de 6 nombres que solo estaban en senuelos, 4 igual aparecian en la
        transcripcion objetivo y solo 2 eran explotables -- chico, pero
        gratis de sacar, porque no hace falta ninguna llamada al modelo.
    """
    from generar_quiz import normalizar
    fuera = set()
    for w in texto.split()[1:]:            # [1:]: la primera va en mayuscula por ser el inicio
        limpio = w.strip(".,;:()¿?¡!\"'")
        if not re.match(r"^[A-ZÁÉÍÓÚÑ]", limpio):
            continue
        n = normalizar(limpio)
        if len(n) < 4 or n in ABRE_FRASE:
            continue
        if n not in transcripcion_norm:
            fuera.add(limpio)
    return fuera


def _rescatar_cadenas(texto, clave):
    """Salva las cadenas COMPLETAS de una lista JSON que quedo cortada.

    Pasa de verdad: el modelo llega al techo de salida en la mitad de una
    afirmacion y el JSON entero deja de parsear. Como se piden N+MARGEN
    afirmaciones, perder las ultimas dos no cuesta nada; tirar las 26 que
    llegaron enteras, si. Se corta en la ultima comilla que cierra.
    """
    m = re.search(r'"' + re.escape(clave) + r'"\s*:\s*\[', texto)
    if not m:
        return []
    resto = texto[m.end():]
    return [s.encode().decode("unicode_escape") if "\\" in s else s
            for s in re.findall(r'"((?:[^"\\]|\\.)*)"\s*(?=,|\])', resto)]


def parsear_json(crudo, clave, rescatar=False):
    """Los modelos envuelven el JSON en ```json ... ``` con frecuencia
    irregular, y a veces agregan una linea de cortesia antes. Se busca el
    primer objeto que tenga la clave pedida en vez de confiar en el formato.
    Con rescatar=True, una respuesta truncada devuelve lo que llego entero."""
    if not crudo:
        raise ValueError("respuesta vacia")
    texto = re.sub(r"^\s*```(?:json)?|```\s*$", "", crudo.strip(), flags=re.M)
    try:
        d = json.loads(texto)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", texto, re.S)
        if m:
            try:
                d = json.loads(m.group(0))
            except json.JSONDecodeError:
                d = None
        else:
            d = None
        if d is None:
            if rescatar:
                salvadas = _rescatar_cadenas(texto, clave)
                if salvadas:
                    print(f"      AVISO respuesta truncada; se rescatan {len(salvadas)} enteras")
                    return salvadas
            raise ValueError(f"no hay JSON en la respuesta: {texto[:200]}")
    if clave not in d:
        raise ValueError(f"falta la clave '{clave}': {list(d)[:5]}")
    return d[clave]


PROMPT_AFIRMACIONES = """Sos un generador de afirmaciones para una prueba de reconocimiento de memoria.

A partir de la transcripcion que sigue, escribi exactamente {n} afirmaciones en espanol. Cada una:
- trata UN solo hecho, idea o argumento que aparece explicitamente en la transcripcion
- esta PARAFRASEADA: no copies frases literales, cambia las palabras y manten el significado
- tiene entre 12 y 25 palabras
- es autocontenida: se entiende sola, sin contexto
- NUNCA dice "el video", "el autor", "el presentador menciona", "segun el": afirma el contenido directamente
- no nombra el titulo del video ni el canal

Reparti las afirmaciones a lo largo de TODA la transcripcion, no solo del principio.
Evita: saludos, publicidad, pedidos de suscripcion, y cifras exactas que nadie podria recordar.

Devolve SOLO este JSON, sin texto alrededor:
{{"afirmaciones": ["...", "..."]}}

TRANSCRIPCION:
{transcripcion}
"""

PROMPT_VERIFICACION = """Te doy una transcripcion y una lista numerada de {n} afirmaciones.

Para cada afirmacion decidi si LA TRANSCRIPCION LA RESPALDA: si lo que dice esta dicho o claramente implicado en la transcripcion.

Regla que no se negocia: NO uses tu conocimiento del mundo. Si una afirmacion es verdadera en la realidad pero la transcripcion no la dice, la respuesta es 0.

Devolve SOLO este JSON, donde el valor es UNA CADENA de exactamente {n} caracteres, cada uno '1' (respaldada) o '0' (no), en el mismo orden que la lista y sin comas ni espacios:
{{"respaldadas": "1010..."}}

TRANSCRIPCION:
{transcripcion}

AFIRMACIONES:
{lista}
"""


def pedir_afirmaciones(cliente, transcripcion, n, pausa):
    texto, recortada = recortar_transcripcion(transcripcion, MAX_PALABRAS_PROMPT)
    msg = [{"role": "user",
            "content": PROMPT_AFIRMACIONES.format(n=n, transcripcion=texto)}]
    # Sin max_salida: manda el del proveedor (24000 en Gemini). El razonamiento
    # del modelo sale del mismo presupuesto que el texto, asi que apretarlo a
    # mano corta la lista por la mitad.
    crudo = cliente.pedir(msg, temperatura=0.6)
    time.sleep(pausa)
    afs = [a.strip() for a in parsear_json(crudo, "afirmaciones", rescatar=True)
           if isinstance(a, str)]
    return [a for a in afs if 5 <= len(a.split()) <= 45], recortada


def _un_lote(control, texto, afirmaciones, pausa):
    """Un pedido de verificacion. Devuelve la lista de booleanos o None."""
    lista = "\n".join(f"{i+1}. {a}" for i, a in enumerate(afirmaciones))
    msg = [{"role": "user", "content": PROMPT_VERIFICACION.format(
        n=len(afirmaciones), transcripcion=texto, lista=lista)}]
    crudo = control.pedir(msg, temperatura=0.0)
    time.sleep(pausa)
    try:
        v = parsear_json(crudo, "respaldadas")
    except (ValueError, KeyError):
        return None
    if isinstance(v, str):                       # formato nuevo: "1010..."
        bits = re.sub(r"[^01]", "", v)
    else:                                        # por si devuelve la lista vieja
        bits = "".join("1" if int(x) else "0" for x in v)
    if len(bits) != len(afirmaciones):
        return None
    return [b == "1" for b in bits]


def verificar(control, transcripcion, afirmaciones, pausa, lote=16):
    """El control juzga las 40+ afirmaciones mezcladas, sin saber cuales son
    objetivos y cuales senuelos, asi que no puede sesgar por la clase.

    LA SALIDA ES UNA CADENA DE BITS, NO UNA LISTA JSON
        Con `[1, 0, 1, ...]` la respuesta de 64 veredictos son ~200 tokens y
        los modelos 2.5 de Gemini piensan antes de contestar: el razonamiento
        se comia el presupuesto y la lista volvia cortada a los 61 valores, o
        directamente sin contenido (KeyError 'message'). Una cadena "1010..."
        son 64 caracteres y entra siempre.

    Y SI IGUAL FALLA, SE PARTE EN LOTES
        Una lista corta no se puede alinear con las afirmaciones, y aceptarla
        desalinearia los veredictos en silencio -- peor que fallar. Asi que
        primero se intenta entero y, si no cierra, se parte: un lote que falla
        cuesta 16 afirmaciones, no el video.
    """
    texto, _ = recortar_transcripcion(transcripcion, MAX_PALABRAS_PROMPT)
    v = _un_lote(control, texto, afirmaciones, pausa)
    if v is not None:
        return v
    print(f"      AVISO el control no devolvio {len(afirmaciones)} veredictos alineados; "
          f"se parte en lotes de {lote}")
    salida = []
    for i in range(0, len(afirmaciones), lote):
        trozo = afirmaciones[i:i + lote]
        v = _un_lote(control, texto, trozo, pausa)
        if v is None:
            v = _un_lote(control, texto, trozo, pausa)     # un reintento por lote
        if v is None:
            raise ValueError(f"el control fallo en el lote {i//lote + 1} "
                             f"({len(trozo)} afirmaciones) dos veces")
        salida.extend(v)
    return salida


def procesar(video, senuelo_src, gen, control, rng, args, pausa):
    print(f"  [{video['id']}] {video['title'][:60]}")
    print(f"      senuelos de [{senuelo_src['id']}] {senuelo_src['title'][:50]}")

    objetivos, rec1 = pedir_afirmaciones(gen, video["transcript"],
                                         args.objetivos + MARGEN, pausa)
    senuelos, rec2 = pedir_afirmaciones(gen, senuelo_src["transcript"],
                                        args.senuelos + MARGEN, pausa)
    print(f"      generadas: {len(objetivos)} objetivos, {len(senuelos)} senuelos"
          + ("  (transcripcion recortada)" if rec1 or rec2 else ""))

    # Verificacion cruzada contra la transcripcion DEL OBJETIVO, mezcladas.
    todas = [(a, "objetivo") for a in objetivos] + [(a, "senuelo") for a in senuelos]
    rng.shuffle(todas)
    veredictos = verificar(control, video["transcript"], [t[0] for t in todas], pausa)

    ok_obj, ok_sen = [], []
    desc_obj = desc_sen = 0
    for (texto, clase), respaldada in zip(todas, veredictos):
        if clase == "objetivo":
            # Un objetivo que el control no encuentra en la transcripcion esta
            # mal parafraseado o es una invencion del generador: fuera.
            if respaldada:
                ok_obj.append(texto)
            else:
                desc_obj += 1
        else:
            # Un senuelo que SI aparece en el video objetivo convertiria un
            # "no" correcto en falsa alarma: fuera.
            if respaldada:
                desc_sen += 1
            else:
                ok_sen.append(texto)
    print(f"      control: descarta {desc_obj} objetivos no respaldados y "
          f"{desc_sen} senuelos que SI aparecen en el objetivo")

    # Tercer filtro, deterministico y sin llamadas: fuera los senuelos que
    # nombran entidades que el video objetivo nunca menciona.
    # Es una PREFERENCIA, no un corte a ciegas: en el video 27 el corte duro se
    # llevo 25 de 32 senuelos y dejo 6 contra 31 objetivos, que arruina d'. Se
    # ordenan por cuantos nombres ausentes tienen y se descartan solo mientras
    # queden suficientes.
    from generar_quiz import normalizar
    trans_norm = normalizar(video["transcript"])
    puntuados = sorted(((len(nombres_ausentes(t, trans_norm)), t) for t in ok_sen),
                       key=lambda p: p[0])
    limpios = [t for k, t in puntuados if k == 0]
    sucios = [t for k, t in puntuados if k > 0]
    # min() con len(sucios): sin eso, cuando hacen falta mas rescates que
    # sucios disponibles el contador de descartes daba negativo (-1 en el 27).
    rescatados = min(max(0, args.senuelos - len(limpios)), len(sucios))
    ok_sen = limpios + sucios[:rescatados]
    desc_nom = len(sucios) - rescatados
    print(f"      nombres propios: descarta {desc_nom} senuelos que nombran algo "
          f"que el objetivo nunca menciona"
          + (f" (se conservan {rescatados} para no quedarse corto)" if rescatados else ""))

    # BALANCEADO. d' se calcula con la tasa de aciertos sobre objetivos y la de
    # falsas alarmas sobre senuelos; si hay 20 de una clase y 6 de la otra, esa
    # segunda tasa se estima con 6 datos y el error de medicion se dispara.
    # Mejor 6 y 6 que 20 y 6.
    n = min(len(ok_obj), len(ok_sen), args.objetivos)
    if n < args.objetivos:
        print(f"      AVISO quedan {len(ok_obj)} objetivos y {len(ok_sen)} senuelos; "
              f"se usan {n} de cada uno para que el par quede balanceado")
    rng.shuffle(ok_obj)
    rng.shuffle(ok_sen)
    items = ([{"texto": t, "clase": "objetivo", "origen_video_id": video["id"]}
              for t in ok_obj[:n]]
             + [{"texto": t, "clase": "senuelo", "origen_video_id": senuelo_src["id"]}
                for t in ok_sen[:n]]
             + [{"texto": t, "clase": "control_atencion", "origen_video_id": None}
                for t in rng.sample(ABSURDAS, args.control_atencion)])
    rng.shuffle(items)
    for i, it in enumerate(items, 1):
        it["n"] = i

    return {
        "content_item_id": video["id"],
        "titulo": video["title"],
        "canal": video["channel"],
        "url": video["url"],
        "categoria": video["category_name"],
        "duration_seconds": video["duration_seconds"],
        "watched_at": video["watched_at"].isoformat() if video["watched_at"] else None,
        "senuelo_origen_id": senuelo_src["id"],
        "senuelo_origen_titulo": senuelo_src["title"],
        "n_objetivos": sum(1 for i in items if i["clase"] == "objetivo"),
        "n_senuelos": sum(1 for i in items if i["clase"] == "senuelo"),
        "descartes": {"objetivos_no_respaldados": desc_obj,
                      "senuelos_respaldados_por_el_objetivo": desc_sen,
                      "senuelos_con_nombres_ausentes": desc_nom},
        "items": items,
    }


def fijar_esfuerzo(cliente, valor, proveedor):
    """Apaga el razonamiento de verdad.

    En los modelos 2.5 de Gemini, OMITIR `reasoning_effort` no apaga el
    pensamiento: lo deja en su presupuesto dinamico por defecto, que sale del
    MISMO cupo que el texto y se lo come. Hay que mandar "none" explicito.
    En Groq ese valor no existe, pero ClienteLLM reintenta sin los extras si la
    API los rechaza, asi que mandarlo no rompe nada.
    """
    if valor == "none":
        cliente.esfuerzo = "none" if proveedor == "gemini" else None
    else:
        cliente.esfuerzo = valor
    return cliente


MULETILLA = re.compile(
    r"\b(el video|el autor|el presentador|segun el|se menciona|se explica|el narrador|"
    r"se comenta|el conductor|el entrevistado)\b", re.I)


def revisar(etiqueta):
    """Informe de control de calidad del lote, SIN mostrar una sola afirmacion.

    Existe porque los dos numeros que importan --cuanto descarto el control--
    salian solo por consola, y el archivo que los tiene es el que no hay que
    abrir. Esto te los devuelve sin quemarte la prueba.
    """
    import statistics as st
    ruta = SALIDA / f"items_{etiqueta}.json"
    if not ruta.exists():
        print(f"No existe {ruta}")
        return 1
    d = json.loads(ruta.read_text(encoding="utf-8"))
    print(f"{ruta.name} · {d['generado_at'][:19]}")
    print(f"generador {d['modelo_generador']} · control {d['modelo_control']}\n")
    for v in d["videos"]:
        it = [i for i in v["items"] if i["clase"] != "control_atencion"]
        de = v["descartes"]
        n_obj = sum(1 for i in it if i["clase"] == "objetivo")
        n_sen = len(it) - n_obj
        print(f"[{v['content_item_id']}] {v['titulo'][:58]}")
        print(f"  senuelos de [{v['senuelo_origen_id']}] {v['senuelo_origen_titulo'][:44]}"
              f"  (similitud {v.get('senuelo_similitud')})")
        print(f"  quedaron {n_obj} objetivos + {n_sen} senuelos + "
              f"{len(v['items']) - len(it)} controles de atencion")
        print(f"  DESCARTADOS POR EL CONTROL:")
        print(f"    {de['objetivos_no_respaldados']:3d} objetivos que no encontro en la transcripcion")
        print(f"       (muchos = el generador esta inventando cosas que el video no dice)")
        print(f"    {de['senuelos_respaldados_por_el_objetivo']:3d} senuelos que SI aparecen en el video objetivo")
        print(f"       (cero = el filtro de anti-anclaje no esta trabajando)")
        if "senuelos_con_nombres_ausentes" in de:
            print(f"    {de['senuelos_con_nombres_ausentes']:3d} senuelos que nombran algo que el objetivo nunca menciona")
        print(f"  CALIDAD Y PISTAS DE ESTILO (objetivo | senuelo):")
        fila = {}
        for clase in ("objetivo", "senuelo"):
            g = [i["texto"] for i in it if i["clase"] == clase]
            if not g:
                continue
            fila[clase] = (st.median(len(t.split()) for t in g),
                           sum(1 for t in g if MULETILLA.search(t)))
        if len(fila) == 2:
            (lo, mo), (ls, ms) = fila["objetivo"], fila["senuelo"]
            print(f"    largo mediano   {lo:4.0f} | {ls:<4.0f} palabras"
                  + ("   <- OJO: se diferencian por largo" if abs(lo - ls) > 4 else ""))
            print(f"    'el video/...'  {mo:4d} | {ms:<4d}"
                  + ("   <- OJO: concentrada en una clase, es una pista"
                     if (mo == 0) != (ms == 0) and mo + ms >= 3 else ""))
        dup = [t for t, n in collections.Counter(i["texto"] for i in it).items() if n > 1]
        if dup:
            print(f"    {len(dup)} afirmaciones duplicadas  <- OJO")
        print()
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max", type=int, default=5, help="cuantos videos (0 = todos)")
    ap.add_argument("--ids", default="", help="ids separados por coma; ignora --max")
    ap.add_argument("--objetivos", type=int, default=N_OBJETIVOS)
    ap.add_argument("--senuelos", type=int, default=N_SENUELOS)
    ap.add_argument("--control-atencion", type=int, default=N_CONTROL_ATENCION)
    ap.add_argument("--min-palabras", type=int, default=MIN_PALABRAS)
    ap.add_argument("--min-desvios", type=float, default=3.0,
                    help="a cuantos desvios de la similitud tipica del pool tiene que quedar "
                         "el senuelo elegido; por debajo se marca FLOJO (defecto 3)")
    ap.add_argument("--min-pool", type=int, default=20,
                    help="minimo de videos EN EL MISMO IDIOMA para poder emparejar; "
                         "por debajo el objetivo se saltea (defecto 20)")
    ap.add_argument("--esfuerzo", default="none",
                    choices=["none", "low", "medium", "high"],
                    help="razonamiento del generador. 'none' por defecto: parafrasear no lo "
                         "necesita y el razonamiento come del mismo techo de salida")
    ap.add_argument("--incluir-con-quiz", action="store_true",
                    help="tambien los videos que ya tienen quiz de opcion multiple "
                         "(rendir una prueba es en si mismo un evento de memoria)")
    ap.add_argument("--proveedor", default="gemini", choices=["gemini", "groq"])
    ap.add_argument("--modelo", default=None)
    ap.add_argument("--proveedor-control", default=None, choices=["gemini", "groq"])
    ap.add_argument("--modelo-control", default=None)
    ap.add_argument("--semilla", type=int, default=20260923)
    ap.add_argument("--etiqueta", default="piloto")
    ap.add_argument("--dry-run", action="store_true",
                    help="muestra que videos se elegirian y no gasta una sola llamada")
    ap.add_argument("--revisar", action="store_true",
                    help="informe de calidad de un lote ya generado, sin mostrar ninguna "
                         "afirmacion; no toca la base ni el modelo")
    ap.add_argument("--reanudar", action="store_true",
                    help="conserva los videos que ya estan en el archivo de la etiqueta y "
                         "genera solo los que faltan")
    ap.add_argument("--rehacer", action="store_true",
                    help="con --reanudar: los videos de --ids se regeneran aunque ya esten")
    args = ap.parse_args()

    if args.revisar:
        return revisar(args.etiqueta)

    env = RAIZ / "backend" / ".env"
    try:
        from dotenv import load_dotenv
        if env.exists():
            load_dotenv(env)
    except ImportError:
        pass

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print(f"No hay DATABASE_URL. Ponela en {env}")
        return 2

    rng = random.Random(args.semilla)

    # Que ya esta hecho, para no volver a pagarlo.
    ruta = SALIDA / f"items_{args.etiqueta}.json"
    previos, ya_hechos = [], set()
    if args.reanudar and ruta.exists():
        previos = json.loads(ruta.read_text(encoding="utf-8")).get("videos", [])
        ya_hechos = {v["content_item_id"] for v in previos}
        if args.rehacer and args.ids:
            rehacer = {int(x) for x in args.ids.split(",") if x.strip()}
            previos = [v for v in previos if v["content_item_id"] not in rehacer]
            ya_hechos -= rehacer
            print(f"--rehacer: se regeneran {sorted(rehacer & set(ya_hechos | rehacer))}")
        print(f"--reanudar: ya estan {sorted(ya_hechos)}; se generan solo los que faltan")

    candidatos = traer(dsn, CONSULTA_OBJETIVOS,
                       {"min_palabras": args.min_palabras,
                        "incluir_con_quiz": args.incluir_con_quiz})
    if args.ids:
        pedidos = {int(x) for x in args.ids.split(",") if x.strip()}
        candidatos = [v for v in candidatos if v["id"] in pedidos]
    else:
        # Estratificado por duracion: se parte la lista ordenada en --max
        # tramos y se sortea uno de cada tramo. Elegir los mas cortos para
        # ahorrar tiempo colapsaria el rango de log(duracion), que es la
        # linea de base del estudio.
        n = args.max or len(candidatos)
        if n < len(candidatos):
            tramos = [candidatos[i * len(candidatos) // n:(i + 1) * len(candidatos) // n]
                      for i in range(n)]
            candidatos = [rng.choice(t) for t in tramos if t]

    candidatos = [v for v in candidatos if v["id"] not in ya_hechos]

    if not candidatos:
        if ya_hechos:
            print("No falta ninguno: todos los pedidos ya estan en el archivo.")
            return 0
        print("No hay videos que cumplan. Baja --min-palabras o usa --incluir-con-quiz.")
        return 1

    print(f"Videos elegidos: {len(candidatos)}")
    for v in candidatos:
        print(f"  [{v['id']:4d}] {v['duration_seconds']//60:3d} min · "
              f"{v['transcript_word_count']:5d} palabras · {v['category_name']} · {v['title'][:50]}")

    # Un video de senuelos distinto por objetivo, elegido por PARECIDO DE
    # CONTENIDO. Ver elegir_por_similitud: la categoria de YouTube no sirve.
    pool = traer(dsn, CONSULTA_SENUELOS, {"min_palabras": args.min_palabras})
    idiomas = collections.Counter(p.get("idioma") or "?" for p in pool)
    print(f"\nPool de senuelos: {len(pool)} videos del corpus que nunca viste "
          f"({', '.join(f'{k}:{n}' for k, n in idiomas.most_common())})")

    usados = set()
    parejas = []
    print(f"\n{'objetivo':>8s} {'senuelos':>9s} {'sim':>6s} {'desvios':>8s}  emparejamiento")
    for v in candidatos:
        # EL SENUELO TIENE QUE ESTAR EN EL MISMO IDIOMA. Sin esto, el unico
        # objetivo en ingles se emparejo con el unico otro video en ingles del
        # pool --geologia contra un chimpance-- y la similitud dio 0,41 con 8,6
        # desvios: el coseno estaba midiendo IDIOMA, no tema. Un senuelo en otro
        # idioma se descarta sin recordar nada, que es justo lo que hay que evitar.
        idi = v.get("idioma")
        mismo = [p for p in pool if (p.get("idioma") or "?") == (idi or "?")]
        if len(mismo) < args.min_pool:
            print(f"{v['id']:8d} {'':9s} {'':6s} {'':8s}  SALTEADO: solo {len(mismo)} "
                  f"videos en '{idi}' para emparejar (hacen falta {args.min_pool})")
            continue
        s, sim, zeta = elegir_por_similitud(v["transcript"], mismo, usados)
        if s is None:
            print(f"  AVISO sin senuelos disponibles para [{v['id']}]; se saltea")
            continue
        usados.add(s["id"])
        parejas.append((v, s, sim, zeta))
        flag = "  <- FLOJO" if zeta < args.min_desvios else ""
        print(f"{v['id']:8d} {s['id']:9d} {sim:6.3f} {zeta:8.1f}  "
              f"{v['title'][:30]} | {s['title'][:30]}{flag}")

    flojos = [p for p in parejas if p[3] < args.min_desvios]
    if flojos:
        print(f"\nAVISO  {len(flojos)} pareja(s) con el senuelo a menos de {args.min_desvios} desvios")
        print("       de la similitud tipica del pool: no habia ningun video de ese tema. Ahi el")
        print("       senuelo se descarta por el TEMA, sin acordarse de nada, y d' sale inflado.")
        print("       Sacalos con --ids, o declara que esos videos miden de mas.")

    if args.dry_run:
        print("\n--dry-run: no se hizo ninguna llamada al modelo.")
        return 0

    # Recien ahora se pide la transcripcion ENTERA de los elegidos: traer las
    # 400 completas para rankear seria mover decenas de megas al pedo.
    parejas = [(v, traer(dsn, CONSULTA_TRANSCRIPCION, {"id": s["id"]})[0], sim)
               for v, s, sim, _ in parejas]

    cfg = PROVEEDORES[args.proveedor]
    pausa = cfg["pausa"]
    api_key = next((os.getenv(k) for k in cfg["claves"] if os.getenv(k)), None)
    if not api_key:
        print(f"No hay {' ni '.join(cfg['claves'])} en {env}")
        return 2
    gen = fijar_esfuerzo(ClienteLLM(api_key, cfg, args.modelo), args.esfuerzo, args.proveedor)
    print(f"\nGenerador: {gen.modelo} ({args.proveedor}) · razonamiento {gen.esfuerzo}")

    control = gen
    if args.proveedor_control and args.proveedor_control != args.proveedor:
        cfg_c = PROVEEDORES[args.proveedor_control]
        clave_c = next((os.getenv(k) for k in cfg_c["claves"] if os.getenv(k)), None)
        if clave_c:
            control = fijar_esfuerzo(ClienteLLM(clave_c, cfg_c, args.modelo_control),
                                     "none", args.proveedor_control)
            print(f"Control: {control.modelo} ({args.proveedor_control}) "
                  f"· razonamiento {control.esfuerzo}")
        else:
            print("AVISO  sin clave para el control; lo hace el mismo modelo que genera. "
                  "Reconoce sus propias parafrasis y descarta de menos.")
    elif args.modelo_control and args.modelo_control != gen.modelo:
        control = fijar_esfuerzo(ClienteLLM(api_key, cfg, args.modelo_control),
                                 "none", args.proveedor)
        print(f"Control: {control.modelo} ({args.proveedor}) "
              f"· razonamiento {control.esfuerzo}")
    else:
        print("AVISO  el control es el MISMO modelo que genera. Usa --proveedor-control "
              "para separarlos.")

    # PRECHEQUEO DEL CUPO DEL CONTROL.
    # La verificacion le manda al control la transcripcion ENTERA del objetivo;
    # el control de generar_quiz.py solo recibia la pregunta, asi que el perfil
    # de tokens no tiene nada que ver. Con el cupo de 8.000/min del nivel gratis
    # de Groq esto no entra NUNCA, y descubrirlo despues de gastar las llamadas
    # de generacion es tirar creditos. Se chequea el peor caso antes de empezar.
    peor = max(parejas, key=lambda p: p[0].get("transcript_word_count") or 0)[0]
    texto_peor, _ = recortar_transcripcion(peor["transcript"], MAX_PALABRAS_PROMPT)
    n_peor = args.objetivos + args.senuelos + 2 * MARGEN
    lista_ficticia = "\n".join(f"{i+1}. " + "palabra " * 22 for i in range(n_peor))
    msg_peor = [{"role": "user", "content": PROMPT_VERIFICACION.format(
        n=n_peor, transcripcion=texto_peor, lista=lista_ficticia)}]
    necesita = ClienteLLM.estimar_tokens(msg_peor) + MARGEN_TPM + MIN_SALIDA
    print(f"\nChequeo de cupo del control: la verificacion mas grande pide ~{necesita} tokens; "
          f"{control.modelo} tiene {control.tpm}/min")
    if necesita > control.tpm:
        print(f"\nNO ENTRA. El control recibe la transcripcion entera, no una pregunta suelta.")
        print(f"  Con --proveedor-control groq el cupo gratis es {control.tpm} tokens/min y el")
        print(f"  video mas largo del lote necesita ~{necesita}. Opciones, de mejor a peor:")
        print(f"    1) --proveedor-control gemini --modelo-control gemini-2.5-flash-lite")
        print(f"       (250.000/min, y sigue siendo un modelo distinto del generador)")
        print(f"    2) sacar del lote los videos mas largos con --ids")
        print(f"    3) bajar MAX_PALABRAS_PROMPT, a costa de que el control juzgue contra una")
        print(f"       transcripcion recortada y descarte objetivos validos por no encontrarlos")
        return 2

    SALIDA.mkdir(parents=True, exist_ok=True)
    salida = {"version": VERSION,
              "generado_at": datetime.now(timezone.utc).isoformat(),
              "semilla": args.semilla,
              "modelo_generador": gen.modelo,
              "modelo_control": control.modelo,
              "videos": list(previos)}

    t0 = time.time()
    fallados = []
    for i, (v, s, sim) in enumerate(parejas, 1):
        print(f"\n({i}/{len(parejas)})")
        try:
            ficha = procesar(v, s, gen, control, rng, args, pausa)
            ficha["senuelo_similitud"] = round(sim, 4)
            salida["videos"].append(ficha)
        except Exception as e:
            print(f"      ERROR  {type(e).__name__}: {e}  -- se saltea este video")
            fallados.append((v["id"], f"{type(e).__name__}: {str(e)[:110]}"))
            continue
        # Se guarda despues de cada video: una corrida cortada no se pierde.
        ruta.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nListo en {time.time()-t0:.0f} s · {len(salida['videos'])} videos en el archivo · {ruta}")
    if fallados:
        # Resumen al final: los ERROR quedan sepultados 200 lineas mas arriba y
        # despues no se sabe cuales faltaron ni por que.
        print(f"\nFALLARON {len(fallados)} de {len(parejas)}:")
        for vid, motivo in fallados:
            print(f"  [{vid}] {motivo}")
        print(f"\nPara reintentar SOLO esos, sin volver a pagar los que salieron:")
        print(f"  --ids {','.join(str(v) for v, _ in fallados)} --etiqueta {args.etiqueta} --reanudar")
    print("\nNO ABRAS ESE ARCHIVO: tiene la clave. Segui con armar_reconocimiento_html.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

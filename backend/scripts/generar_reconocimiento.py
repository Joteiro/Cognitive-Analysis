#!/usr/bin/env python3
"""Genera una prueba de RECONOCIMIENTO a partir de las transcripciones. (v2)

QUE CAMBIO RESPECTO DE v1, Y POR QUE
    En v1 los senuelos salian de OTRO video del corpus. El piloto de 6 videos
    mostro que eso se resolvia sin memoria: el formulario muestra el titulo
    --y tiene que mostrarlo, si no la pregunta no tiene referente-- asi que
    alcanzaba con descartar por tema todo lo que no encajara con el titulo.
    La evidencia: d' = 2,78 con acierto 0,90 y falsas alarmas 0,09, tres de
    seis videos entre el 87 % y el 100 % del techo, y --el dato que lo parte--
    los videos que la persona NO recordaba haber visto dieron d' MAS alto
    (3,26) que los que si recordaba (2,42). 19 de 20 aciertos en un video que
    no recordaba haber mirado.

    En v2 los senuelos salen del MISMO video: variantes falsas pero plausibles
    de su propio contenido. Asi la consistencia tematica con el titulo no sirve
    para nada y solo discrimina la memoria episodica. Es el diseno estandar de
    senuelos relacionados en investigacion de reconocimiento.

    Consecuencias en el codigo:
      - `PROMPT_ALTERACIONES` es nuevo: convierte afirmaciones verdaderas en
        variantes falsas con cinco tecnicas acotadas.
      - El anti-anclaje se INVIERTE y es la misma llamada: la variante alterada
        NO tiene que estar respaldada por la transcripcion, y la verdadera si.
      - Se cayeron los tres filtros que existian solo para elegir el video de
        senuelos: similitud, idioma y nombres propios.
      - `procesar()` ya no necesita `senuelo_src`.

CALIBRAR LA DIFICULTAD
    v1 estaba contra el techo y por eso la varianza entre videos dio negativa.
    Los senuelos del mismo video son bastante mas dificiles. El objetivo es
    acierto ~0,75 y falsas alarmas ~0,25, que es donde la medida tiene margen
    para moverse en las dos direcciones. Si el piloto sale con acierto > 0,90,
    subir `--sutileza`; si sale por debajo de 0,60, bajarla.

REQUISITOS
    backend/.env con DATABASE_URL y GEMINI_API_KEY (o GROQ_API_KEY).
    pip install -r requirements-analisis.txt

SALIDA
    docs/reconocimiento/clave_no_abrir/items_<etiqueta>.json
    NO ABRAS ESE ARCHIVO: tiene la clave. Abri solo el HTML que arma
    armar_reconocimiento_html.py, y para ver como salio el lote usa --revisar.

EL CONTROL NO PUEDE SER GROQ EN EL NIVEL GRATIS
    A diferencia de generar_quiz.py --donde el control recibe solo la pregunta--
    aca recibe la TRANSCRIPCION ENTERA para juzgar el respaldo. Una transcripcion
    de 7.000 palabras son ~13.000 tokens y el cupo gratis de Groq es 8.000/min:
    no entra nunca. El script lo chequea antes de gastar una sola llamada.

USO TIPICO
    python generar_reconocimiento.py --max 8 --etiqueta piloto2 \\
        --proveedor gemini --proveedor-control gemini \\
        --modelo-control gemini-2.5-flash-lite
"""

import argparse
import collections
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Se reutiliza la plomeria ya depurada de generar_quiz.py: el cliente de LLM
# con sus reintentos y su respeto de cupo, la tabla de proveedores y el
# recorte de transcripciones por ventanas.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generar_quiz import (  # noqa: E402
    ClienteLLM, PROVEEDORES, recortar_transcripcion, RAIZ, DOCS, MIN_SALIDA,
    MARGEN_TPM,
)

VERSION = "reconocimiento-2.0"

SALIDA = DOCS / "reconocimiento" / "clave_no_abrir"

N_OBJETIVOS = 20
N_CONTROL_ATENCION = 2
MARGEN = 12           # hechos de mas: el control descarta objetivos que no
                      # encuentra y alteradas que quedaron verdaderas
MIN_PALABRAS = 600
MAX_PALABRAS_PROMPT = 12000
# NO se fija un techo de salida propio: se deja el `max_salida` del proveedor
# (24000 en Gemini, 8000 en Groq). Fijarlo a mano en 8000 fue el bug que corto
# la generacion en la afirmacion 11: gemini-2.5-flash piensa antes de escribir
# y ese razonamiento sale del MISMO presupuesto.

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
       ci.transcript_word_count
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


def traer(dsn, sql, params):
    import psycopg2
    import psycopg2.extras
    with psycopg2.connect(dsn, connect_timeout=20) as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def _rescatar_cadenas(texto, clave):
    """Salva las cadenas COMPLETAS de una lista JSON que quedo cortada.

    Pasa de verdad: el modelo llega al techo de salida en la mitad de una
    afirmacion y el JSON entero deja de parsear. Como se piden N+MARGEN
    afirmaciones, perder las ultimas dos no cuesta nada; tirar las 26 que
    llegaron enteras, si.
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
        d = None
        if m:
            try:
                d = json.loads(m.group(0))
            except json.JSONDecodeError:
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


def fijar_esfuerzo(cliente, valor, proveedor):
    """Apaga el razonamiento de verdad.

    En los modelos 2.5 de Gemini, OMITIR `reasoning_effort` no apaga el
    pensamiento: lo deja en su presupuesto dinamico por defecto, que sale del
    MISMO cupo que el texto y se lo come. Hay que mandar "none" explicito.
    """
    if valor == "none":
        cliente.esfuerzo = "none" if proveedor == "gemini" else None
    else:
        cliente.esfuerzo = valor
    return cliente


# ---------------------------------------------------------------------------
# PROMPTS
# ---------------------------------------------------------------------------

PROMPT_AFIRMACIONES = """Sos un generador de afirmaciones para una prueba de reconocimiento de memoria.

A partir de la transcripcion que sigue, escribi exactamente {n} afirmaciones en espanol. Cada una:
- trata UN solo hecho, idea o argumento que aparece explicitamente en la transcripcion
- esta PARAFRASEADA: no copies frases literales, cambia las palabras y manten el significado
- tiene entre 12 y 25 palabras
- es autocontenida: se entiende sola, sin contexto
- NUNCA dice "el video", "el autor", "el presentador menciona", "segun el": afirma el contenido directamente
- no nombra el titulo del video ni el canal

Reparti las afirmaciones a lo largo de TODA la transcripcion, no solo del principio.
Que cada una hable de un hecho DISTINTO: no repitas el mismo dato con otras palabras.
Evita: saludos, publicidad, pedidos de suscripcion, y cifras exactas que nadie podria recordar.

Devolve SOLO este JSON, sin texto alrededor:
{{"afirmaciones": ["...", "..."]}}

TRANSCRIPCION:
{transcripcion}
"""

SUTILEZA = {
    "baja": "El cambio tiene que ser claro: quien vio el video lo nota sin esfuerzo.",
    "media": "El cambio tiene que ser reconocible para quien vio el video, sin ser grosero.",
    "alta": "El cambio tiene que ser fino: cambia UNA sola pieza de la afirmacion y el resto "
            "queda identico, palabra por palabra.",
}

PROMPT_ALTERACIONES = """Sos un generador de DISTRACTORES para una prueba de reconocimiento de memoria.

Te doy {n} afirmaciones VERDADERAS, sacadas de la transcripcion de un video. Convertí cada una en una version FALSA PARA ESE VIDEO, usando UNA de estas cinco tecnicas (varialas entre afirmaciones):

1. cambiar una cifra, una fecha o una cantidad
2. invertir una relacion causal: lo que era causa pasa a ser consecuencia
3. atribuir la afirmacion a otro interlocutor, a otro lugar o a otra entidad
4. negar la conclusion, o exagerarla hasta que deje de ser lo que se dijo
5. fusionar dos afirmaciones de la lista en una sola que combine mal sus partes

Reglas que no se negocian:

- **PLAUSIBLE EN EL MUNDO.** Quien no vio el video no tiene que poder descartarla por absurda ni por conocimiento general. Nada de disparates, nada de imposibles fisicos, nada de cifras ridiculas.
- **MISMO TEMA Y MISMO VOCABULARIO** que la original. Si la original habla de geologia, la falsa habla de geologia.
- **MISMO LARGO**, con una diferencia maxima de tres palabras.
- **MISMO REGISTRO**: nunca digas "el video", "el autor", "se menciona". Afirma directamente, igual que la original.
- El cambio es de CONTENIDO, no de redaccion. Alguien que vio el video tiene que poder decir "eso no es lo que decia", no "eso esta escrito raro".

{sutileza}

Devolve SOLO este JSON, con exactamente {n} elementos, en el MISMO ORDEN que la lista:
{{"alteradas": ["...", "..."]}}

AFIRMACIONES VERDADERAS:
{lista}
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


# ---------------------------------------------------------------------------
# LLAMADAS
# ---------------------------------------------------------------------------

def pedir_afirmaciones(cliente, transcripcion, n, pausa):
    texto, recortada = recortar_transcripcion(transcripcion, MAX_PALABRAS_PROMPT)
    msg = [{"role": "user",
            "content": PROMPT_AFIRMACIONES.format(n=n, transcripcion=texto)}]
    crudo = cliente.pedir(msg, temperatura=0.6)
    time.sleep(pausa)
    afs = [a.strip() for a in parsear_json(crudo, "afirmaciones", rescatar=True)
           if isinstance(a, str)]
    return [a for a in afs if 5 <= len(a.split()) <= 45], recortada


def _lote_alteraciones(cliente, originales, sutileza, pausa):
    lista = "\n".join(f"{i+1}. {a}" for i, a in enumerate(originales))
    msg = [{"role": "user", "content": PROMPT_ALTERACIONES.format(
        n=len(originales), sutileza=SUTILEZA[sutileza], lista=lista)}]
    crudo = cliente.pedir(msg, temperatura=0.8)
    time.sleep(pausa)
    try:
        v = parsear_json(crudo, "alteradas", rescatar=True)
    except (ValueError, KeyError):
        return None
    v = [a.strip() for a in v if isinstance(a, str) and a.strip()]
    return v if len(v) == len(originales) else None


def alterar(cliente, originales, sutileza, pausa, lote=10):
    """Convierte afirmaciones verdaderas en variantes falsas del MISMO video.

    La alineacion importa: si vuelven menos alteradas que originales no se
    puede saber cual corresponde a cual. Igual que en la verificacion, primero
    se intenta entero y si no cierra se parte en lotes -- un lote que falla
    cuesta 10 afirmaciones, no el video.
    """
    v = _lote_alteraciones(cliente, originales, sutileza, pausa)
    if v is not None:
        return v
    print(f"      AVISO el generador no devolvio {len(originales)} alteradas alineadas; "
          f"se parte en lotes de {lote}")
    salida = []
    for i in range(0, len(originales), lote):
        trozo = originales[i:i + lote]
        v = _lote_alteraciones(cliente, trozo, sutileza, pausa)
        if v is None:
            v = _lote_alteraciones(cliente, trozo, sutileza, pausa)
        if v is None:
            raise ValueError(f"el generador fallo al alterar el lote {i//lote + 1} "
                             f"({len(trozo)} afirmaciones) dos veces")
        salida.extend(v)
    return salida


def _un_lote_verificacion(control, texto, afirmaciones, pausa):
    lista = "\n".join(f"{i+1}. {a}" for i, a in enumerate(afirmaciones))
    msg = [{"role": "user", "content": PROMPT_VERIFICACION.format(
        n=len(afirmaciones), transcripcion=texto, lista=lista)}]
    crudo = control.pedir(msg, temperatura=0.0)
    time.sleep(pausa)
    try:
        v = parsear_json(crudo, "respaldadas")
    except (ValueError, KeyError):
        return None
    bits = re.sub(r"[^01]", "", v) if isinstance(v, str) else \
        "".join("1" if int(x) else "0" for x in v)
    return [b == "1" for b in bits] if len(bits) == len(afirmaciones) else None


def verificar(control, transcripcion, afirmaciones, pausa, lote=16):
    """EL ANTI-ANCLAJE, INVERTIDO PARA LOS SENUELOS.

    El control juzga todas las afirmaciones mezcladas --sin saber cuales son
    objetivos y cuales alteradas-- contra la transcripcion del video. Despues:
      - el objetivo que NO encuentra se descarta (el generador lo invento)
      - la alterada que SI encuentra se descarta (la alteracion fallo y la
        variante sigue siendo verdadera, asi que un "si" correcto se contaria
        como falsa alarma)
    Es la misma llamada que en v1; lo que cambia es el signo que se espera de
    cada clase.

    La salida es una CADENA DE BITS, no una lista JSON: con `[1, 0, 1, ...]`
    una respuesta de 64 veredictos son ~200 tokens, y los modelos 2.5 de Gemini
    piensan antes de contestar y se comian el presupuesto. "1010..." son 64
    caracteres y entra siempre.
    """
    texto, _ = recortar_transcripcion(transcripcion, MAX_PALABRAS_PROMPT)
    v = _un_lote_verificacion(control, texto, afirmaciones, pausa)
    if v is not None:
        return v
    print(f"      AVISO el control no devolvio {len(afirmaciones)} veredictos alineados; "
          f"se parte en lotes de {lote}")
    salida = []
    for i in range(0, len(afirmaciones), lote):
        trozo = afirmaciones[i:i + lote]
        v = _un_lote_verificacion(control, texto, trozo, pausa)
        if v is None:
            v = _un_lote_verificacion(control, texto, trozo, pausa)
        if v is None:
            raise ValueError(f"el control fallo en el lote {i//lote + 1} "
                             f"({len(trozo)} afirmaciones) dos veces")
        salida.extend(v)
    return salida


# ---------------------------------------------------------------------------
# UN VIDEO
# ---------------------------------------------------------------------------

def procesar(video, gen, control, rng, args, pausa):
    print(f"  [{video['id']}] {video['title'][:60]}")

    # Se piden el doble de hechos que objetivos: la mitad quedan como
    # objetivos y la otra mitad son la materia prima de los senuelos. Se
    # PARTEN, no se superponen: si el mismo hecho apareciera como verdadero y
    # como alterado, el par se delata solo por contradiccion.
    n_hechos = 2 * args.objetivos + MARGEN
    hechos, recortada = pedir_afirmaciones(gen, video["transcript"], n_hechos, pausa)
    print(f"      generados: {len(hechos)} hechos de {n_hechos} pedidos"
          + ("  (transcripcion recortada)" if recortada else ""))
    if len(hechos) < 2 * 4:
        raise ValueError(f"solo {len(hechos)} hechos utilizables; no alcanza para partir")

    rng.shuffle(hechos)
    mitad = len(hechos) // 2
    base_obj, base_alt = hechos[:mitad], hechos[mitad:2 * mitad]

    alteradas = alterar(gen, base_alt, args.sutileza, pausa)
    print(f"      alteradas: {len(alteradas)} (sutileza {args.sutileza})")

    # Verificacion cruzada, mezcladas: el control no sabe cual es cual.
    todas = [(t, "objetivo") for t in base_obj] + [(t, "senuelo") for t in alteradas]
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
            # Una alterada que el control SI encuentra sigue siendo verdadera:
            # la alteracion no funciono y seria una falsa alarma injusta.
            if respaldada:
                desc_sen += 1
            else:
                ok_sen.append(texto)
    print(f"      control: descarta {desc_obj} objetivos no respaldados y "
          f"{desc_sen} alteradas que siguen siendo verdaderas")

    # BALANCEADO. d' se calcula con la tasa de aciertos sobre objetivos y la de
    # falsas alarmas sobre senuelos; si hay 20 de una clase y 6 de la otra, esa
    # segunda tasa se estima con 6 datos y el error de medicion se dispara.
    n = min(len(ok_obj), len(ok_sen), args.objetivos)
    if n < args.objetivos:
        print(f"      AVISO quedan {len(ok_obj)} objetivos y {len(ok_sen)} senuelos; "
              f"se usan {n} de cada uno para que el par quede balanceado")
    if n < 4:
        raise ValueError(f"solo quedan {n} items por clase; el video no sirve")

    rng.shuffle(ok_obj)
    rng.shuffle(ok_sen)
    items = ([{"texto": t, "clase": "objetivo", "origen_video_id": video["id"]}
              for t in ok_obj[:n]]
             + [{"texto": t, "clase": "senuelo", "origen_video_id": video["id"]}
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
        "sutileza": args.sutileza,
        "n_objetivos": n,
        "n_senuelos": n,
        "descartes": {"objetivos_no_respaldados": desc_obj,
                      "alteradas_que_siguen_siendo_verdaderas": desc_sen},
        "items": items,
    }


# ---------------------------------------------------------------------------
# INFORME
# ---------------------------------------------------------------------------

MULETILLA = re.compile(
    r"\b(el video|el autor|el presentador|segun el|se menciona|se explica|el narrador|"
    r"se comenta|el conductor|el entrevistado)\b", re.I)


def revisar(etiqueta):
    """Informe de calidad del lote, SIN mostrar una sola afirmacion."""
    import statistics as st
    ruta = SALIDA / f"items_{etiqueta}.json"
    if not ruta.exists():
        print(f"No existe {ruta}")
        return 1
    d = json.loads(ruta.read_text(encoding="utf-8"))
    print(f"{ruta.name} · {d['generado_at'][:19]} · {d.get('version', '?')}")
    print(f"generador {d['modelo_generador']} · control {d['modelo_control']}\n")
    for v in d["videos"]:
        it = [i for i in v["items"] if i["clase"] != "control_atencion"]
        de = v["descartes"]
        o = [i["texto"] for i in it if i["clase"] == "objetivo"]
        s = [i["texto"] for i in it if i["clase"] == "senuelo"]
        print(f"[{v['content_item_id']}] {v['titulo'][:58]}  (sutileza {v.get('sutileza','?')})")
        print(f"  quedaron {len(o)} objetivos + {len(s)} senuelos + "
              f"{len(v['items']) - len(it)} controles de atencion")
        print(f"  DESCARTADOS POR EL CONTROL:")
        print(f"    {de.get('objetivos_no_respaldados', 0):3d} objetivos que no encontro en la transcripcion")
        print(f"       (muchos = el generador esta inventando cosas que el video no dice)")
        print(f"    {de.get('alteradas_que_siguen_siendo_verdaderas', 0):3d} alteradas que siguen siendo verdaderas")
        print(f"       (cero = la alteracion no esta cambiando el contenido de verdad)")
        print(f"  PISTAS DE ESTILO (objetivo | senuelo) -- tienen que parecerse:")
        if o and s:
            lo, ls = st.median(len(t.split()) for t in o), st.median(len(t.split()) for t in s)
            mo, ms = sum(1 for t in o if MULETILLA.search(t)), sum(1 for t in s if MULETILLA.search(t))
            print(f"    largo mediano   {lo:4.0f} | {ls:<4.0f} palabras"
                  + ("   <- OJO: se diferencian por largo" if abs(lo - ls) > 3 else ""))
            print(f"    'el video/...'  {mo:4d} | {ms:<4d}"
                  + ("   <- OJO: concentrada en una clase, es una pista"
                     if (mo == 0) != (ms == 0) and mo + ms >= 3 else ""))
        dup = [t for t, n in collections.Counter(i["texto"] for i in it).items() if n > 1]
        if dup:
            print(f"    {len(dup)} afirmaciones duplicadas  <- OJO")
        print()
    print("Recorda el objetivo de calibracion: acierto ~0,75 y falsas alarmas ~0,25.")
    print("Si al puntuar el acierto pasa de 0,90, subi --sutileza; si baja de 0,60, bajala.")
    return 0


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max", type=int, default=8, help="cuantos videos (0 = todos)")
    ap.add_argument("--ids", default="", help="ids separados por coma; ignora --max")
    ap.add_argument("--objetivos", type=int, default=N_OBJETIVOS,
                    help="objetivos por video; se usa el mismo numero de senuelos")
    ap.add_argument("--control-atencion", type=int, default=N_CONTROL_ATENCION)
    ap.add_argument("--min-palabras", type=int, default=MIN_PALABRAS)
    ap.add_argument("--sutileza", default="media", choices=list(SUTILEZA),
                    help="cuan fina es la alteracion. Mas sutileza = mas dificil = "
                         "menos acierto y mas falsas alarmas (defecto: media)")
    ap.add_argument("--incluir-con-quiz", action="store_true",
                    help="tambien los videos que ya tienen quiz de opcion multiple "
                         "(rendir una prueba es en si mismo un evento de memoria)")
    ap.add_argument("--proveedor", default="gemini", choices=["gemini", "groq"])
    ap.add_argument("--modelo", default=None)
    ap.add_argument("--proveedor-control", default=None, choices=["gemini", "groq"])
    ap.add_argument("--modelo-control", default=None)
    ap.add_argument("--semilla", type=int, default=20260925)
    ap.add_argument("--etiqueta", default="piloto2")
    ap.add_argument("--esfuerzo", default="none",
                    choices=["none", "low", "medium", "high"],
                    help="razonamiento del generador. 'none' por defecto: el razonamiento "
                         "come del mismo techo de salida que el texto")
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

    ruta = SALIDA / f"items_{args.etiqueta}.json"
    previos, ya_hechos = [], set()
    if args.reanudar and ruta.exists():
        previos = json.loads(ruta.read_text(encoding="utf-8")).get("videos", [])
        ya_hechos = {v["content_item_id"] for v in previos}
        if args.rehacer and args.ids:
            rehacer = {int(x) for x in args.ids.split(",") if x.strip()}
            previos = [v for v in previos if v["content_item_id"] not in rehacer]
            ya_hechos -= rehacer
            print(f"--rehacer: se regeneran {sorted(rehacer)}")
        print(f"--reanudar: ya estan {sorted(ya_hechos)}; se generan solo los que faltan")

    candidatos = traer(dsn, CONSULTA_OBJETIVOS,
                       {"min_palabras": args.min_palabras,
                        "incluir_con_quiz": args.incluir_con_quiz})
    if args.ids:
        pedidos = {int(x) for x in args.ids.split(",") if x.strip()}
        candidatos = [v for v in candidatos if v["id"] in pedidos]
    else:
        # Estratificado por duracion: elegir los mas cortos para ahorrar tiempo
        # colapsaria el rango de log(duracion), que es la linea de base del estudio.
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

    if args.dry_run:
        print("\n--dry-run: no se hizo ninguna llamada al modelo.")
        return 0

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
            print("AVISO  sin clave para el control; lo hace el mismo modelo que genera.")
    elif args.modelo_control and args.modelo_control != gen.modelo:
        control = fijar_esfuerzo(ClienteLLM(api_key, cfg, args.modelo_control),
                                 "none", args.proveedor)
        print(f"Control: {control.modelo} ({args.proveedor}) "
              f"· razonamiento {control.esfuerzo}")
    else:
        print("AVISO  el control es el MISMO modelo que genera. Usa --proveedor-control "
              "para separarlos.")

    # PRECHEQUEO DEL CUPO DEL CONTROL: la verificacion le manda la transcripcion
    # ENTERA. Con el cupo de 8.000/min del nivel gratis de Groq no entra nunca, y
    # descubrirlo despues de gastar las llamadas de generacion es tirar creditos.
    peor = max(candidatos, key=lambda v: v.get("transcript_word_count") or 0)
    texto_peor, _ = recortar_transcripcion(peor["transcript"], MAX_PALABRAS_PROMPT)
    n_peor = 2 * args.objetivos + MARGEN
    lista_ficticia = "\n".join(f"{i+1}. " + "palabra " * 22 for i in range(n_peor))
    msg_peor = [{"role": "user", "content": PROMPT_VERIFICACION.format(
        n=n_peor, transcripcion=texto_peor, lista=lista_ficticia)}]
    necesita = ClienteLLM.estimar_tokens(msg_peor) + MARGEN_TPM + MIN_SALIDA
    print(f"\nChequeo de cupo del control: la verificacion mas grande pide ~{necesita} tokens; "
          f"{control.modelo} tiene {control.tpm}/min")
    if necesita > control.tpm:
        print(f"\nNO ENTRA. El control recibe la transcripcion entera, no una pregunta suelta.")
        print(f"  Opciones, de mejor a peor:")
        print(f"    1) --proveedor-control gemini --modelo-control gemini-2.5-flash-lite")
        print(f"    2) sacar del lote los videos mas largos con --ids")
        print(f"    3) bajar MAX_PALABRAS_PROMPT, a costa de que el control juzgue contra una")
        print(f"       transcripcion recortada y descarte objetivos validos por no encontrarlos")
        return 2

    SALIDA.mkdir(parents=True, exist_ok=True)
    salida = {"version": VERSION,
              "generado_at": datetime.now(timezone.utc).isoformat(),
              "semilla": args.semilla,
              "sutileza": args.sutileza,
              "modelo_generador": gen.modelo,
              "modelo_control": control.modelo,
              "videos": list(previos)}

    t0 = time.time()
    fallados = []
    for i, v in enumerate(candidatos, 1):
        print(f"\n({i}/{len(candidatos)})")
        try:
            salida["videos"].append(procesar(v, gen, control, rng, args, pausa))
        except Exception as e:
            print(f"      ERROR  {type(e).__name__}: {e}  -- se saltea este video")
            fallados.append((v["id"], f"{type(e).__name__}: {str(e)[:110]}"))
            continue
        # Se guarda despues de cada video: una corrida cortada no se pierde.
        ruta.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nListo en {time.time()-t0:.0f} s · {len(salida['videos'])} videos en el archivo · {ruta}")
    if fallados:
        print(f"\nFALLARON {len(fallados)} de {len(candidatos)}:")
        for vid, motivo in fallados:
            print(f"  [{vid}] {motivo}")
        print(f"\nPara reintentar SOLO esos, sin volver a pagar los que salieron:")
        print(f"  --ids {','.join(str(v) for v, _ in fallados)} --etiqueta {args.etiqueta} --reanudar")
    print("\nNO ABRAS ESE ARCHIVO: tiene la clave. Mira el lote con --revisar y segui con "
          "armar_reconocimiento_html.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

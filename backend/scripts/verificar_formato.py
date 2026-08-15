#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verificar_formato.py (v0.1) -- comprueba si la etiqueta de formato coincide
con lo que de verdad dice el video, y SENALA los desacuerdos sin corregirlos.

EL PROBLEMA
    La etiqueta `formato` (informativo / practico_personal / entretenimiento /
    deporte_gaming) se calcula asi, en build_reference_scale.py:

        d["stratum_format"] = d["category_id"].apply(brc.bucket_formato)

    Es decir: sale UNICAMENTE de la categoria que el canal se autodeclara en
    YouTube. No mira el titulo, ni la duracion, ni los capitulos, ni una sola
    palabra de la transcripcion. Es una etiqueta del CANAL, no del VIDEO.

    Caso que lo destapo: una entrevista de 129 minutos quedo como
    "informativo" porque el canal se declara "News & Politics", y entro al
    piloto del quiz como si fuera una nota informativa.

POR QUE ESTE SCRIPT NO REETIQUETA NADA
    El 2026-08-05 se decidio que las etiquetas fueran 100 % deterministas,
    sin LLM, para no reintroducir la circularidad que marco el profesor. Un
    modelo que reescribe la etiqueta en silencio mete un instrumento sin
    validar en medio del pipeline y se lleva puesta esa garantia.

    Asi que aca el modelo SENALA y no decide:
      - la etiqueta oficial sigue siendo la de la regla;
      - el desacuerdo se guarda aparte, como "posible clasificacion diferente";
      - el quiz se salta los videos senalados, que es una decision de uso,
        no un cambio de dato;
      - y la CONCORDANCIA regla<->modelo se mide y se informa (acuerdo bruto
        y kappa de Cohen), con lo cual el modelo pasa a ser un evaluador mas
        medido contra el instrumento, nunca la verdad de referencia.

    Es la diferencia entre el inspector que te cambia la etiqueta del envase
    y el que le pega un sticker de "revisar esto".

DOS CAPAS
    Capa 1 (gratis, cero tokens): marca los videos cuya etiqueta gruesa no
    tiene NINGUN respaldo del contenido -- los que son "informativo" solo
    porque el canal se declara asi, mientras su formato editorial apunta a
    otra cosa (conversacion larga, directo, opinion, resumen de evento).
    Ojo: `formato` es un eje de TEMA y `et_formato` de FORMA. No se
    contradicen por definicion; lo que dice esta capa es que la etiqueta
    descansa entera en la autodeclaracion del canal.

    Capa 2 (con Groq): el modelo ve titulo, canal, categoria declarada y ~300
    palabras muestreadas de la transcripcion, y dice que formato observa.
    No se le manda la transcripcion entera a proposito: para distinguir una
    entrevista de dos horas de una nota informativa alcanza y sobra, y son
    ~600 tokens por video en vez de ~4.500.

USO
    .venv\\Scripts\\python verificar_formato.py --dry-run     # capa 1 sola, gratis
    .venv\\Scripts\\python verificar_formato.py               # las dos capas
    .venv\\Scripts\\python verificar_formato.py --corpus historial

SALIDA (en docs/)
    formato_verificado.json     una entrada por video; la lee generar_quiz.py
    formato_verificado.md       concordancia, kappa, tabla cruzada y casos
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Se reutiliza el cliente y la normalizacion de generar_quiz en vez de
# copiarlos: dos copias del mismo cliente derivan, y este proyecto ya decidio
# que no quiere logica duplicada.
from generar_quiz import (Groq, normalizar, recortar_transcripcion, RAIZ, DOCS)

VERSION = "verificar-formato-0.1"

FORMATOS = ["informativo", "practico_personal", "entretenimiento", "deporte_gaming"]

# Formatos editoriales que NO respaldan por si mismos la etiqueta "informativo":
# en estos, si la etiqueta gruesa dice informativo, lo dice solo porque el canal
# se autodeclaro asi en YouTube.
SIN_RESPALDO = {"conversacion_larga", "directo", "opinion_review",
                "resumen_evento", "sin_clasificar", None}

PALABRAS_MUESTRA = 300

SISTEMA = """Clasificas videos de YouTube por el TIPO DE CONTENIDO que son, no por el canal que los publica.

Las cuatro categorias posibles son:
- "informativo": noticias, actualidad, analisis, divulgacion, explicaciones. El proposito principal es que el espectador se entere o entienda algo.
- "practico_personal": tutoriales, guias, consejos aplicables, desarrollo personal, salud, finanzas personales. El proposito es que el espectador HAGA algo.
- "entretenimiento": entrevistas y charlas largas de tono distendido, humor, reacciones, streams, vlogs, ficcion. El proposito principal es pasar el rato, aunque por el camino se hable de temas serios.
- "deporte_gaming": deporte, esports, videojuegos, resumenes de partidos.

Criterio central: pregunta cual es el PROPOSITO PRINCIPAL, no el tema. Una charla de dos horas entre amigos que comenta la actualidad politica es "entretenimiento", no "informativo": el formato es la conversacion, no la noticia. Un noticiero de 20 minutos sobre deporte es "deporte_gaming".

Se te da una MUESTRA de la transcripcion, no el video entero. Si la muestra no alcanza para decidir, dilo con confianza "baja" en vez de inventar.

Devuelve SOLO un objeto json con esta forma:
{"formato": "informativo|practico_personal|entretenimiento|deporte_gaming", "confianza": "alta|media|baja", "motivo": "una frase corta"}"""


def prompt(video: dict, muestra: str) -> list:
    return [
        {"role": "system", "content": SISTEMA},
        {"role": "user", "content": (
            f"TITULO: {video['title']}\n"
            f"CANAL: {video['channel']}\n"
            f"CATEGORIA QUE EL CANAL SE DECLARA EN YOUTUBE: {video.get('category_name')}\n"
            f"DURACION: {round((video.get('duration_seconds') or 0) / 60)} minutos\n"
            f"CAPITULOS: {video.get('n_chapters') or 0}\n\n"
            f"MUESTRA DE LA TRANSCRIPCION (principio, medio y final):\n{muestra}"
        )},
    ]


CONSULTA = """
select ci.id, ci.external_id, ci.title, ci.channel, ci.category_name,
       ci.duration_seconds, ci.n_chapters, ci.transcript,
       ci.transcript_word_count, ci.corpus,
       f.formato, f.etiquetas->>'et_formato' as et_formato
from content_items ci
join content_features f on f.content_item_id = ci.id
where ci.transcript is not null
  and (%(corpus)s = 'todos' or ci.corpus = %(corpus)s)
order by ci.id
"""


def traer(dsn: str, corpus: str) -> list:
    import psycopg2
    import psycopg2.extras
    with psycopg2.connect(dsn, connect_timeout=20) as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(CONSULTA, {"corpus": corpus})
            return [dict(r) for r in cur.fetchall()]


def kappa_cohen(pares: list) -> float:
    """Kappa de Cohen entre dos clasificadores sobre las mismas unidades.

    Se implementa a mano (son quince lineas) para no arrastrar sklearn al
    entorno por una sola formula.

    El acuerdo bruto enganía cuando una categoria domina: si el 60 % de los
    videos son "informativo", dos clasificadores que dijeran siempre
    "informativo" acordarian el 100 % sin saber nada. Kappa descuenta el
    acuerdo que se esperaria por puro azar dadas las frecuencias de cada uno.
    """
    n = len(pares)
    if not n:
        return float("nan")
    etiquetas = sorted({x for p in pares for x in p})
    obs = sum(1 for a, b in pares if a == b) / n
    fa = {e: sum(1 for a, _ in pares if a == e) / n for e in etiquetas}
    fb = {e: sum(1 for _, b in pares if b == e) / n for e in etiquetas}
    esp = sum(fa[e] * fb[e] for e in etiquetas)
    return (obs - esp) / (1 - esp) if esp < 1 else float("nan")


def interpretar_kappa(k: float) -> str:
    if k != k:
        return "no calculable"
    if k < 0.20:
        return "pobre"
    if k < 0.40:
        return "debil"
    if k < 0.60:
        return "moderado"
    if k < 0.80:
        return "sustancial"
    return "casi perfecto"


def informe(datos: list, ruta: Path, modelo: str) -> None:
    verificados = [d for d in datos if d.get("formato_observado")]
    pares = [(d["formato"], d["formato_observado"]) for d in verificados]
    acuerdos = [d for d in verificados if d["formato"] == d["formato_observado"]]
    desacuerdos = [d for d in verificados if d["formato"] != d["formato_observado"]]
    firmes = [d for d in desacuerdos if d["confianza"] == "alta"]
    sin_respaldo = [d for d in datos if d["sin_respaldo"]]
    k = kappa_cohen(pares)

    def pct(a, b):
        return f"{100.0 * a / b:.0f} %" if b else "n/d"

    L = [
        "# Verificacion de la etiqueta de formato",
        "",
        f"Generado {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · modelo `{modelo}` · "
        f"version `{VERSION}`",
        "",
        "## 1. Que es esto y que NO es",
        "",
        "La etiqueta `formato` del proyecto se deriva **solo del `category_id` que el canal",
        "se autodeclara en YouTube**: no mira titulo, duracion, capitulos ni transcripcion.",
        "Es una etiqueta del canal, no del video.",
        "",
        "Este informe **no corrige ninguna etiqueta**. La etiqueta oficial sigue siendo la de",
        "la regla determinista. Lo que hace es medir cuanto se parece a lo que un modelo",
        "observa en el contenido, y senalar los casos donde discrepan para no usarlos en el",
        "quiz. El modelo es un evaluador mas, medido contra el instrumento; nunca la verdad",
        "de referencia.",
        "",
        "## 2. Capa 1 — etiquetas sin respaldo del contenido (cero tokens)",
        "",
        f"{len(sin_respaldo)} de {len(datos)} videos son `informativo` unicamente porque el canal",
        "se declara asi, mientras su formato editorial (`et_formato`) apunta a conversacion",
        "larga, directo, opinion o resumen de evento. No es una contradiccion —`formato` es un",
        "eje de tema y `et_formato` de forma— pero si significa que la etiqueta no tiene",
        "ningun respaldo en el contenido.",
        "",
        "## 3. Capa 2 — concordancia entre la regla y el modelo",
        "",
        "| | n | |",
        "|---|---:|---:|",
        f"| Videos verificados | {len(verificados)} | |",
        f"| Coinciden | {len(acuerdos)} | {pct(len(acuerdos), len(verificados))} |",
        f"| Discrepan | {len(desacuerdos)} | {pct(len(desacuerdos), len(verificados))} |",
        f"| Discrepan con confianza alta | {len(firmes)} | {pct(len(firmes), len(verificados))} |",
        "",
        f"**Kappa de Cohen: {k:.2f}** ({interpretar_kappa(k)}).",
        "",
        "El acuerdo bruto solo no basta: si una categoria domina el corpus, dos clasificadores",
        "que la eligieran siempre acordarian mucho sin saber nada. Kappa descuenta ese acuerdo",
        "esperable por azar.",
        "",
        "### Tabla cruzada (filas: la regla · columnas: el modelo)",
        "",
        "| regla \\\\ modelo | " + " | ".join(FORMATOS) + " |",
        "|---|" + "---|" * len(FORMATOS),
    ]
    for fr in FORMATOS:
        fila = [str(sum(1 for d in verificados
                        if d["formato"] == fr and d["formato_observado"] == fc))
                for fc in FORMATOS]
        L.append(f"| **{fr}** | " + " | ".join(fila) + " |")

    L += ["", "## 4. Desacuerdos con confianza alta", ""]
    if not firmes:
        L.append("_Ninguno._")
    for d in firmes:
        L += [f"**{d['titulo'][:70]}**  ",
              f"regla: `{d['formato']}` · modelo: `{d['formato_observado']}` · "
              f"et_formato: `{d['et_formato']}` · {round((d['duracion'] or 0) / 60)} min  ",
              f"> {d['motivo']}", ""]

    L += [
        "## 5. Como se usa",
        "",
        "`generar_quiz.py` lee `formato_verificado.json` y **se salta** los videos donde el",
        "modelo discrepa con confianza alta, avisando por pantalla. Es una decision de uso",
        "del dato, no una correccion del dato.",
        "",
        "Si kappa es bajo, la conclusion NO es que el modelo tenga razon: es que la etiqueta",
        "derivada de la categoria de YouTube y el contenido observable miden cosas distintas,",
        "y eso hay que decirlo al presentar cualquier resultado partido por formato.",
    ]
    ruta.write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Verifica la etiqueta de formato sin corregirla")
    ap.add_argument("--corpus", default="historial", help="historial | referencia | todos")
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--modelo", default=None)
    ap.add_argument("--dry-run", action="store_true", help="solo la capa 1, sin gastar tokens")
    args = ap.parse_args()

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

    videos = traer(dsn, args.corpus)
    if args.max:
        videos = videos[:args.max]
    print(f"{len(videos)} videos con transcripcion y features (corpus={args.corpus})")

    datos = []
    for v in videos:
        datos.append({
            "content_item_id": v["id"],
            "external_id": v["external_id"],
            "titulo": v["title"],
            "canal": v["channel"],
            "categoria_yt": v["category_name"],
            "duracion": v["duration_seconds"],
            "formato": v["formato"],
            "et_formato": v["et_formato"],
            "sin_respaldo": bool(v["formato"] == "informativo"
                                 and v["et_formato"] in SIN_RESPALDO),
            "formato_observado": None,
            "confianza": None,
            "motivo": None,
        })

    sr = [d for d in datos if d["sin_respaldo"]]
    print(f"\nCAPA 1 (gratis): {len(sr)} videos son 'informativo' solo por la "
          f"autodeclaracion del canal")
    for d in sr:
        print(f"  [{d['content_item_id']:>4}] {round((d['duracion'] or 0)/60):>4} min  "
              f"et_formato={d['et_formato']:<20} {d['titulo'][:45]}")

    if args.dry_run:
        print(f"\nLa capa 2 serian ~{len(videos)} llamadas y ~{len(videos) * 600:,} tokens.")
        return 0

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print(f"No hay GROQ_API_KEY. Ponela en {env}")
        return 2

    groq = Groq(api_key, args.modelo)
    print(f"\nCAPA 2 con {groq.modelo}")

    for i, (v, d) in enumerate(zip(videos, datos), 1):
        muestra, _ = recortar_transcripcion(v["transcript"], PALABRAS_MUESTRA)
        try:
            r = json.loads(groq.pedir(prompt(v, muestra), temperatura=0.0))
            f = (r.get("formato") or "").strip()
            d["formato_observado"] = f if f in FORMATOS else None
            d["confianza"] = r.get("confianza")
            d["motivo"] = r.get("motivo")
        except Exception as e:
            d["motivo"] = f"fallo: {e}"
        marca = "  <-- DISCREPA" if (d["formato_observado"]
                                     and d["formato_observado"] != d["formato"]) else ""
        print(f"[{i}/{len(videos)}] regla={d['formato']:<18} modelo="
              f"{str(d['formato_observado']):<18} ({d['confianza']}){marca}")
        time.sleep(1.0)

    DOCS.mkdir(exist_ok=True)
    (DOCS / "formato_verificado.json").write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    informe(datos, DOCS / "formato_verificado.md", groq.modelo)

    ver = [d for d in datos if d["formato_observado"]]
    ac = sum(1 for d in ver if d["formato"] == d["formato_observado"])
    k = kappa_cohen([(d["formato"], d["formato_observado"]) for d in ver])
    print("\n" + "=" * 60)
    print(f"Acuerdo {ac}/{len(ver)} ({100.0*ac/len(ver):.0f} %) · kappa {k:.2f} "
          f"({interpretar_kappa(k)})")
    print(f"{groq.llamadas} llamadas, {groq.tokens_usados:,} tokens")
    print("Informe: docs/formato_verificado.md")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

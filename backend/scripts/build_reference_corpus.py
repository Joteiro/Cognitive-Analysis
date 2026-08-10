#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_reference_corpus.py  v1.3
Muestreador estratificado del corpus de referencia de YouTube en espanol.

POR QUE EXISTE
--------------
Los cortes bajo/medio/alto del panel se calculaban como tercios del historial
personal: 94 videos, 41 % de un solo canal, casi todo News & Politics. Eso no es
una escala de referencia, es un espejo. Este script construye la escala contra
un corpus publico, estratificado y con la procedencia de cada video guardada.

DISENO
------
- Poblacion objetivo: videos de YouTube en espanol (AR + ES), de 2 a 180 minutos.
- Diseno: estratificado 4 macroformatos x 3 duraciones = 12 celdas,
  asignacion IGUAL (~n/12 por celda), no proporcional. La asignacion igual da
  precision pareja en todas las celdas, que es lo que hace falta para publicar
  percentiles por estrato. Se pierde representatividad de la mezcla global de
  YouTube: para hablar de "YouTube en conjunto" hay que reponderar por el peso
  real de cada celda (se guarda en el CSV de auditoria).
- Dos fuentes, con la procedencia guardada en cada fila. La mezcla NO se fuerza
  al 50 %: sale del tamanio relativo de cada pool (en la corrida del 2026-08-10
  quedo 73 % B / 27 % A). Hay que declararla, no suponerla.
    A. chart_canal ....... canales que aparecen en mostPopular AR/ES; de cada
       canal se sortea un video cualquiera de sus ultimas subidas. Muestrea
       "canales que la gente mira", no "videos que son tendencia hoy": evita
       que todo el corpus quede fechado el dia del muestreo.
    B. busqueda_semilla .. search.list con un termino frecuente del espanol,
       ventana temporal aleatoria de 30 dias en los ultimos 5 anios y
       order=date. El order=date dentro de una ventana estrecha neutraliza el
       ranking de relevancia de YouTube, que es la principal via por la que un
       muestreo por busqueda se sesga hacia la cabeza.
- Tope de 2 videos por canal en todo el corpus. Se reporta el HHI de canal.

USO  (siempre con el Python del entorno: .venv\\Scripts\\python)
---
    --dry-run         muestrea, reporta y cachea. No toca la base. ~6.150 unidades.
    --commit          inserta en content_items. Con --cache, 0 unidades.
    --cache           reusa los candidatos ya descargados. Combinable con los dos de arriba.
    --informe         estado por celda: cuantos tienen texto, cuantos siguen en cola,
                      cuantos fallaron en firme. Solo lee la base.
    --rehacer-banco   reconstruye el banco de suplentes desde el cache. 0 unidades.
    --rellenar        repone las bajas confirmadas metiendo suplentes de la misma celda.

Flujo normal:  --dry-run  ->  revisar  ->  --commit --cache  ->  esperar la cola
               ->  --informe  ->  --rellenar  ->  --informe

Requiere en backend/.env: YOUTUBE_API_KEY (solo para --dry-run/--commit) y DATABASE_URL.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    # Solo hace falta para hablar con la API de YouTube. --informe y --rellenar
    # unicamente leen la base, y no tienen por que fallar por esto.
    requests = None

try:
    import psycopg
    from psycopg.rows import dict_row
    _PG = "psycopg3"
except ImportError:  # pragma: no cover
    try:
        import psycopg2 as psycopg  # type: ignore
        from psycopg2.extras import RealDictCursor  # type: ignore
        _PG = "psycopg2"
    except ImportError:
        # Que falte el driver no debe impedir ver --help. Se avisa al conectar.
        psycopg = None  # type: ignore
        _PG = None

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


VERSION = "1.3"
FRAME_VERSION = "mm-2026-08-v1"   # subir si cambian semillas, categorias o cortes
API = "https://www.googleapis.com/youtube/v3"

HERE = Path(__file__).resolve().parent
RESERVA_PATH = HERE / "corpus_reserva.json"
CACHE_PATH = HERE / "corpus_candidatos_cache.json"
AUDIT_PATH = HERE.parent.parent / "docs" / "corpus_referencia_auditoria.csv"


# ------------------------------------------------------------------ ESTRATOS

# Macroformato desde category_id de YouTube. Se asigna con metadatos, ANTES de
# enriquecer, porque el estrato tiene que ser conocido en el momento del sorteo.
FORMATO_POR_CATEGORIA = {
    # informativo
    "25": "informativo",          # News & Politics
    "27": "informativo",          # Education
    "28": "informativo",          # Science & Technology
    # practico / personal
    "26": "practico_personal",    # Howto & Style
    "22": "practico_personal",    # People & Blogs
    "19": "practico_personal",    # Travel & Events
    "15": "practico_personal",    # Pets & Animals
    "2":  "practico_personal",    # Autos & Vehicles
    # entretenimiento
    "24": "entretenimiento",      # Entertainment
    "23": "entretenimiento",      # Comedy
    "1":  "entretenimiento",      # Film & Animation
    "10": "entretenimiento",      # Music
    # deporte / gaming
    "17": "deporte_gaming",       # Sports
    "20": "deporte_gaming",       # Gaming
}

FORMATOS = ["informativo", "practico_personal", "entretenimiento", "deporte_gaming"]
DURACIONES = ["corto", "medio", "largo"]

# Los cortes de duracion se declaran aqui y no se tocan sin subir FRAME_VERSION.
DUR_MIN_S = 120        # < 2 min fuera: shorts y clips, sin texto suficiente
DUR_MAX_S = 180 * 60   # > 3 h fuera: streams que rompen cualquier normalizacion


def bucket_duracion(seg: int) -> str | None:
    if seg is None or seg < DUR_MIN_S or seg > DUR_MAX_S:
        return None
    if seg < 10 * 60:
        return "corto"
    if seg < 30 * 60:
        return "medio"
    return "largo"


def bucket_formato(cat_id: str | None) -> str | None:
    return FORMATO_POR_CATEGORIA.get(str(cat_id or ""))


# ------------------------------------------------------------------ SEMILLAS

# Lista fija y publica. Mitad palabras de altisima frecuencia del espanol
# hablado (aparecen en casi cualquier transcripcion o descripcion, asi que
# barren ancho), mitad sustantivos cotidianos sin tema propio. Se congela con
# FRAME_VERSION: cambiar esta lista cambia el marco muestral.
SEMILLAS = [
    # alta frecuencia
    "que", "porque", "entonces", "tambien", "cuando", "donde", "siempre",
    "nunca", "despues", "ahora", "todavia", "aunque", "mientras", "cualquier",
    "algo", "nada", "mucho", "poco", "bastante", "seguro", "claro", "obvio",
    "quiero", "puedo", "tengo", "vamos", "sabes", "mira", "escucha", "fijate",
    # sustantivos cotidianos
    "casa", "vida", "gente", "trabajo", "familia", "tiempo", "dinero", "ciudad",
    "noche", "agua", "comida", "musica", "juego", "amigos", "viaje", "escuela",
    "salud", "coche", "perro", "libro", "pelicula", "verano", "invierno",
    "manana", "semana", "barrio", "cocina", "camino", "puerta", "ventana",
    "historia", "problema", "pregunta", "respuesta", "cambio", "momento",
    "lugar", "forma", "parte", "final",
]

REGIONES = ["AR", "ES"]

STOPWORDS_ES = {
    "de", "la", "que", "el", "en", "y", "a", "los", "se", "del", "las", "un",
    "por", "con", "no", "una", "su", "para", "es", "al", "lo", "como", "mas",
    "o", "pero", "sus", "le", "ya", "este", "si", "porque", "esta", "entre",
    "cuando", "muy", "sin", "sobre", "tambien", "me", "hasta", "hay", "donde",
    "quien", "desde", "todo", "nos", "durante", "todos", "uno", "les", "ni",
    "contra", "otros", "ese", "eso", "ante", "ellos", "esto", "antes", "algunos",
    "que", "unos", "yo", "otro", "otras", "otra", "el", "tanto", "esa", "estos",
    "mucho", "quienes", "nada", "muchos", "cual", "poco", "ella", "estar",
    "estas", "algunas", "algo", "nosotros", "vos", "ustedes",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def parece_espanol(texto: str) -> bool:
    """Heuristica de stopwords. No pretende ser un detector de idioma serio:
    solo descarta lo que claramente no es espanol cuando la API no declara
    defaultAudioLanguage (que falta en la mayoria de los videos)."""
    toks = re.findall(r"[a-z]+", norm(texto))
    if len(toks) < 8:
        return False
    ratio = sum(1 for t in toks if t in STOPWORDS_ES) / len(toks)
    return ratio >= 0.12


# ------------------------------------------------------------------ API

class SinDatos(Exception):
    """La API contesto 404. No es un fallo: hay combinaciones region/categoria
    para las que YouTube simplemente no publica chart."""


class Quota:
    """La cuota diaria de la YouTube Data API son 10.000 unidades. search.list
    cuesta 100 y es lo unico caro aca; el resto cuesta 1. Se contabiliza para
    poder abortar antes de que la API empiece a devolver 403 quotaExceeded."""

    LIMITE = 10_000

    def __init__(self, limite: int = LIMITE):
        self.limite = limite
        self.usadas = 0
        self.detalle = Counter()

    def gastar(self, unidades: int, etiqueta: str) -> None:
        self.usadas += unidades
        self.detalle[etiqueta] += unidades

    def alcanza(self, unidades: int) -> bool:
        return self.usadas + unidades <= self.limite

    def resumen(self) -> str:
        partes = ", ".join(f"{k}={v}" for k, v in self.detalle.most_common())
        return f"{self.usadas}/{self.limite} unidades ({partes})"


class YT:
    def __init__(self, key: str, quota: Quota, verbose: bool = True):
        if requests is None:
            raise RuntimeError(
                "Falta el modulo 'requests'. Casi seguro estas usando el Python "
                "del sistema en vez del del entorno: corre\n"
                "    .venv\\Scripts\\python build_reference_corpus.py ...\n"
                "o instalalo con  pip install requests")
        self.key = key
        self.quota = quota
        self.verbose = verbose
        self.sess = requests.Session()

    def _get(self, endpoint: str, params: dict, coste: int) -> dict:
        if not self.quota.alcanza(coste):
            raise RuntimeError(
                f"Cuota agotada antes de llamar a {endpoint} "
                f"({self.quota.resumen()}). Volve manana o subi --max-busquedas."
            )
        params = {**params, "key": self.key}
        for intento in range(4):
            r = self.sess.get(f"{API}/{endpoint}", params=params, timeout=30)
            if r.status_code == 200:
                self.quota.gastar(coste, endpoint)
                return r.json()
            if r.status_code in (403, 429):
                cuerpo = r.text[:300]
                if "quotaExceeded" in cuerpo or "dailyLimitExceeded" in cuerpo:
                    raise RuntimeError(f"Cuota diaria agotada segun la API: {cuerpo}")
                time.sleep(2 ** intento)
                continue
            if 500 <= r.status_code < 600:
                time.sleep(2 ** intento)
                continue
            if r.status_code == 404:
                # Rutinario, no es un error: p.ej. una categoria sin chart en
                # esa region. Se corta el cuerpo para no vomitar JSON.
                raise SinDatos(f"{endpoint} 404")
            raise RuntimeError(f"{endpoint} -> HTTP {r.status_code}: {r.text[:300]}")
        raise RuntimeError(f"{endpoint} fallo tras 4 intentos")

    # -- capa A: canales populares ------------------------------------------

    def categorias_asignables(self, region: str) -> list[str]:
        data = self._get("videoCategories", {"part": "snippet", "regionCode": region}, 1)
        return [it["id"] for it in data.get("items", [])
                if it["snippet"].get("assignable") and it["id"] in FORMATO_POR_CATEGORIA]

    def canales_de_charts(self, region: str, categorias: list[str]):
        """Devuelve ({channel_id: 'chart:REGION/categoria'}, [categorias sin chart]).

        Un 404 aca es rutina, no un fallo: YouTube no publica chart para toda
        combinacion region/categoria (en AR y ES no lo hay para Travel & Events
        ni para Education, por ejemplo). Se cuentan y se reportan en una linea."""
        canales: dict[str, str] = {}
        sin_chart: list[str] = []
        for cat in categorias:
            try:
                data = self._get("videos", {
                    "part": "snippet", "chart": "mostPopular", "regionCode": region,
                    "videoCategoryId": cat, "maxResults": 50,
                }, 1)
            except SinDatos:
                sin_chart.append(cat)
                continue
            for it in data.get("items", []):
                cid = it["snippet"].get("channelId")
                if cid:
                    canales.setdefault(cid, f"chart:{region}/{cat}")
        return canales, sin_chart

    def subidas_del_canal(self, channel_id: str, n: int = 50) -> list[str]:
        """El id de la playlist de subidas de un canal es su channel_id con
        'UC' -> 'UU'. Es un atajo documentado que ahorra una llamada a
        channels.list por canal."""
        if not channel_id.startswith("UC"):
            return []
        pl = "UU" + channel_id[2:]
        try:
            data = self._get("playlistItems", {
                "part": "contentDetails", "playlistId": pl, "maxResults": n,
            }, 1)
        except (RuntimeError, SinDatos):
            return []
        return [it["contentDetails"]["videoId"] for it in data.get("items", [])
                if it.get("contentDetails", {}).get("videoId")]

    # -- capa B: busquedas semilla ------------------------------------------

    def buscar_semilla(self, termino: str, region: str, desde: datetime,
                       hasta: datetime) -> list[str]:
        data = self._get("search", {
            "part": "id", "type": "video", "q": termino,
            "relevanceLanguage": "es", "regionCode": region,
            "order": "date",                      # neutraliza el ranking de relevancia
            "publishedAfter": desde.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "publishedBefore": hasta.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "maxResults": 50,
        }, 100)
        return [it["id"]["videoId"] for it in data.get("items", [])
                if it.get("id", {}).get("videoId")]

    # -- hidratacion ---------------------------------------------------------

    def hidratar(self, ids: list[str]) -> list[dict]:
        out = []
        for i in range(0, len(ids), 50):
            lote = ids[i:i + 50]
            data = self._get("videos", {
                "part": "snippet,contentDetails,status",
                "id": ",".join(lote), "maxResults": 50,
            }, 1)
            out.extend(data.get("items", []))
        return out


ISO_DUR = re.compile(
    r"P(?:(?P<d>\d+)D)?T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?")


def dur_a_segundos(iso: str) -> int | None:
    m = ISO_DUR.fullmatch(iso or "")
    if not m:
        return None
    g = {k: int(v or 0) for k, v in m.groupdict().items()}
    return g["d"] * 86400 + g["h"] * 3600 + g["m"] * 60 + g["s"]


# ------------------------------------------------------------------ CANDIDATOS

def a_candidato(item: dict, fuente: str, semilla: str,
                motivos: Counter | None = None) -> dict | None:
    """Convierte un item de videos.list en un candidato con estrato asignado,
    o None si no pertenece a la poblacion objetivo.

    Si se le pasa un Counter, anota POR QUE se descarto cada video. Sin ese
    desglose, una tasa de supervivencia baja es indistinguible de un bug."""
    def no(motivo: str):
        if motivos is not None:
            motivos[motivo] += 1
        return None

    sn = item.get("snippet", {}) or {}
    cd = item.get("contentDetails", {}) or {}
    st = item.get("status", {}) or {}

    if st.get("privacyStatus") != "public":
        return no("no_publico")
    if cd.get("regionRestriction"):          # bloqueos por pais rompen el enriquecimiento
        return no("restringido_por_region")

    seg = dur_a_segundos(cd.get("duration", ""))
    if seg is None:
        return no("duracion_ilegible")
    if seg < DUR_MIN_S:
        return no("corto_menos_2min (Shorts y clips)")
    if seg > DUR_MAX_S:
        return no("largo_mas_3h (streams)")
    dur = bucket_duracion(seg)

    fmt = bucket_formato(sn.get("categoryId"))
    if fmt is None:
        return no(f"categoria_no_mapeada ({sn.get('categoryId')})")

    lang = (sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or "").lower()
    if lang:
        if not lang.startswith("es"):
            return no(f"idioma_declarado_no_es ({lang[:5]})")
    else:
        if not parece_espanol(f"{sn.get('title','')} {sn.get('description','')[:600]}"):
            return no("idioma_no_detectado_como_es")

    if motivos is not None:
        motivos["ACEPTADO"] += 1

    pub = sn.get("publishedAt", "")
    return {
        "external_id": item["id"],
        "url": f"https://www.youtube.com/watch?v={item['id']}",
        "title": sn.get("title") or "(sin titulo)",
        "channel": sn.get("channelTitle"),
        "channel_id": sn.get("channelId"),
        "description": sn.get("description") or "",
        "tags": sn.get("tags") or [],
        "category_id": sn.get("categoryId"),
        "duration_seconds": seg,
        "upload_date": pub[:10] if pub else None,
        "video_language": lang or "es?",
        "stratum_format": fmt,
        "stratum_duration": dur,
        "sampling_source": fuente,
        "sampling_seed": semilla,
    }


def ventana_aleatoria(rng: random.Random, anios: int = 5, dias: int = 30):
    fin = datetime.now(timezone.utc) - timedelta(days=rng.randint(1, 365 * anios))
    return fin - timedelta(days=dias), fin


def desglose(motivos: Counter, titulo: str) -> None:
    total = sum(motivos.values()) or 1
    ok = motivos.get("ACEPTADO", 0)
    print(f"    {titulo}: {ok}/{total} aceptados ({ok/total:.0%})")
    for motivo, n in motivos.most_common():
        if motivo == "ACEPTADO":
            continue
        print(f"      descartado {motivo:<38} {n:>5}  ({n/total:.0%})")


def recolectar(yt: YT, rng: random.Random, n_objetivo: int, max_busquedas: int,
               verbose: bool = True) -> list[dict]:
    candidatos: dict[str, dict] = {}
    motivos_a: Counter = Counter()
    motivos_b: Counter = Counter()

    # ---- capa A: canales de charts -> video cualquiera de sus subidas
    if verbose:
        print("\n[A] Canales populares AR/ES")
    canales: dict[str, str] = {}
    for region in REGIONES:
        cats = yt.categorias_asignables(region)
        nuevos, sin_chart = yt.canales_de_charts(region, cats)
        canales.update(nuevos)
        if verbose:
            aviso = (f"  ({len(sin_chart)} sin chart: {','.join(sin_chart)} "
                     f"- normal, no toda categoria tiene chart en cada region)"
                     if sin_chart else "")
            print(f"    {region}: {len(cats)} categorias -> {len(nuevos)} canales{aviso}")

    lista_canales = list(canales.items())
    rng.shuffle(lista_canales)
    ids_a = []
    for cid, origen in lista_canales:
        subidas = yt.subidas_del_canal(cid)
        if not subidas:
            continue
        # 3 al azar por canal; el tope real de 2 se aplica despues de hidratar,
        # porque recien ahi sabemos cuales sobreviven al filtro de poblacion.
        ids_a.extend((v, origen) for v in rng.sample(subidas, min(3, len(subidas))))
        if len(ids_a) >= n_objetivo * 4:
            break
    if verbose:
        print(f"    {len(ids_a)} videos candidatos de {len(lista_canales)} canales")

    origen_por_id = {v: o for v, o in ids_a}
    for item in yt.hidratar([v for v, _ in ids_a]):
        c = a_candidato(item, "chart_canal", origen_por_id.get(item["id"], "chart"),
                        motivos_a)
        if c:
            candidatos.setdefault(c["external_id"], c)

    if verbose:
        desglose(motivos_a, "capa A")

    # ---- capa B: busquedas semilla con ventana temporal aleatoria
    if verbose:
        print("\n[B] Busquedas semilla")
    semillas = SEMILLAS[:]
    rng.shuffle(semillas)
    ids_b: dict[str, str] = {}
    hechas = 0
    for termino in semillas:
        if hechas >= max_busquedas or not yt.quota.alcanza(100 + 40):
            break
        region = REGIONES[hechas % len(REGIONES)]
        desde, hasta = ventana_aleatoria(rng)
        try:
            for vid in yt.buscar_semilla(termino, region, desde, hasta):
                ids_b.setdefault(vid, f"{termino}@{region}@{desde:%Y-%m}")
        except RuntimeError as e:
            if verbose:
                print(f"    corte en '{termino}': {e}")
            break
        hechas += 1
        if verbose and hechas % 10 == 0:
            print(f"    {hechas} busquedas, {len(ids_b)} ids, {yt.quota.resumen()}")

    antes = len(candidatos)
    lista_b = [i for i in ids_b if i not in candidatos]
    for item in yt.hidratar(lista_b):
        c = a_candidato(item, "busqueda_semilla", ids_b.get(item["id"], ""), motivos_b)
        if c:
            candidatos.setdefault(c["external_id"], c)
    if verbose:
        print(f"    {hechas} busquedas -> {len(ids_b)} ids unicos")
        desglose(motivos_b, "capa B")
        print(f"    {len(candidatos) - antes} candidatos nuevos "
              f"(el resto ya venia de la capa A)")

    return list(candidatos.values())


# ------------------------------------------------------------------ SORTEO

def sortear(candidatos: list[dict], rng: random.Random, n_total: int,
            tope_canal: int = 2, reserva_por_celda: int = 20):
    """Asignacion igual por celda con tope por canal. Devuelve (muestra, reserva).

    El sorteo va por RONDAS, no celda por celda. Recorrer las celdas en orden
    fijo parece inocente y no lo es: el tope por canal es un presupuesto
    compartido, asi que las primeras celdas se lo gastan y las ultimas quedan
    vacias. Probado con 4000 candidatos sinteticos, el orden fijo dejaba
    deporte_gaming con 2 videos de 33 mientras informativo se llevaba 99.

    Ademas hay dos pasadas: la primera solo admite canales todavia no usados
    (limite 1), la segunda sube hasta el tope. Asi el corpus maximiza canales
    distintos antes de repetir ninguno."""
    celdas = [(f, d) for f in FORMATOS for d in DURACIONES]
    por_celda = max(1, n_total // len(celdas))

    pool: dict[tuple, list] = {c: [] for c in celdas}
    for c in candidatos:
        k = (c["stratum_format"], c["stratum_duration"])
        if k in pool:
            pool[k].append(c)
    for k in pool:
        rng.shuffle(pool[k])

    # Aviso de factibilidad: con C canales distintos y tope T, el corpus no
    # puede pasar de C*T por mucho candidato que haya.
    n_canales = len({c.get("channel_id") for c in candidatos})
    techo = n_canales * tope_canal
    if techo < n_total:
        print(f"\n  AVISO: {n_canales} canales distintos x tope {tope_canal} = {techo} "
              f"videos como maximo, por debajo del objetivo {n_total}.")
        print("  Subi --max-busquedas (mas canales) o --tope-canal (menos diversidad).")

    usados_canal: Counter = Counter()
    tomados: set[str] = set()
    elegidos: dict[tuple, list] = {c: [] for c in celdas}

    for limite in range(1, tope_canal + 1):
        while True:
            avance = False
            orden = celdas[:]
            rng.shuffle(orden)          # ninguna celda tiene prioridad estructural
            for celda in orden:
                if len(elegidos[celda]) >= por_celda:
                    continue
                for c in pool[celda]:
                    if c["external_id"] in tomados:
                        continue
                    cid = c.get("channel_id") or "?"
                    if usados_canal[cid] >= limite:
                        continue
                    usados_canal[cid] += 1
                    tomados.add(c["external_id"])
                    c["sample_rank"] = "principal"
                    elegidos[celda].append(c)
                    avance = True
                    break
            if not avance:
                break

    muestra = [c for celda in celdas for c in elegidos[celda]]

    reserva = []
    for celda in celdas:
        sobrantes = [c for c in pool[celda] if c["external_id"] not in tomados]
        for c in sobrantes[:reserva_por_celda]:
            c["sample_rank"] = "reserva"
            reserva.append(c)

    return muestra, reserva


def hhi(valores) -> float:
    """Indice Herfindahl-Hirschman de concentracion. 1 = un solo canal.
    En el historial personal daba 0,216 con Vorterix al 41 %."""
    c = Counter(valores)
    tot = sum(c.values()) or 1
    return sum((v / tot) ** 2 for v in c.values())


def reportar(muestra: list[dict], candidatos: list[dict], objetivo_celda: int) -> None:
    if not muestra:
        print("\nLa muestra quedo vacia: ningun candidato paso los filtros.")
        return
    print("\n" + "=" * 68)
    print("DISENO REALIZADO")
    print("=" * 68)
    print(f"{'formato':<20}{'corto':>9}{'medio':>9}{'largo':>9}{'total':>9}")
    faltantes = []
    for fmt in FORMATOS:
        fila = [sum(1 for c in muestra
                    if c["stratum_format"] == fmt and c["stratum_duration"] == d)
                for d in DURACIONES]
        for d, n in zip(DURACIONES, fila):
            if n < objetivo_celda:
                faltantes.append((fmt, d, objetivo_celda - n))
        print(f"{fmt:<20}" + "".join(f"{n:>9}" for n in fila) + f"{sum(fila):>9}")
    print(f"{'TOTAL':<20}{'':>27}{len(muestra):>9}")

    disponibles = Counter((c["stratum_format"], c["stratum_duration"]) for c in candidatos)
    if faltantes:
        print("\nCeldas por debajo del objetivo:")
        for fmt, dur, falta in faltantes:
            print(f"  - {fmt}/{dur}: faltan {falta} "
                  f"(habia {disponibles[(fmt, dur)]} candidatos)")
        print("  Subi --max-busquedas o afloja --tope-canal para llenarlas.")

    canales = [c.get("channel") or "?" for c in muestra]
    h = hhi(canales)
    top = Counter(canales).most_common(5)
    print(f"\nConcentracion de canal: HHI = {h:.4f} sobre {len(set(canales))} canales")
    print(f"  (historial personal: 0,2160. Cuanto mas bajo, mas diverso.)")
    for nombre, n in top:
        print(f"  {n:>3}  {nombre}")

    fuentes = Counter(c["sampling_source"] for c in muestra)
    print("\nProcedencia:")
    for k, v in fuentes.most_common():
        print(f"  {k:<20}{v:>4}  ({v / max(1, len(muestra)):.0%})")

    anios = Counter((c.get("upload_date") or "????")[:4] for c in muestra)
    print("\nAnio de publicacion:")
    for k in sorted(anios):
        print(f"  {k}  {'#' * anios[k]} {anios[k]}")

    horas = sum(c["duration_seconds"] for c in muestra) / 3600
    print(f"\nDuracion total del corpus: {horas:.1f} h "
          f"(mediana {sorted(c['duration_seconds'] for c in muestra)[len(muestra)//2]/60:.1f} min)")
    print(f"Enriquecimiento a 10 videos/hora: ~{len(muestra)/10:.0f} h "
          f"(~{len(muestra)/10/24:.1f} dias de tandas horarias)")


def escribir_auditoria(muestra: list[dict], candidatos: list[dict], path: Path) -> None:
    """El CSV de auditoria es lo que permite reponderar despues: guarda cuantos
    candidatos habia por celda, que es el dato que falta para pasar de
    'percentiles por estrato' a 'percentiles de YouTube en conjunto'."""
    path.parent.mkdir(parents=True, exist_ok=True)
    disponibles = Counter((c["stratum_format"], c["stratum_duration"]) for c in candidatos)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frame_version", "formato", "duracion", "n_muestra",
                    "n_candidatos", "peso_reponderacion",
                    "n_chart_canal", "n_busqueda_semilla"])
        total_cand = sum(disponibles.values()) or 1
        for fmt in FORMATOS:
            for dur in DURACIONES:
                celda = [c for c in muestra if c["stratum_format"] == fmt
                         and c["stratum_duration"] == dur]
                n_m = len(celda)
                n_c = disponibles[(fmt, dur)]
                peso = (n_c / total_cand) / (n_m / len(muestra)) if n_m and muestra else ""
                n_a = sum(1 for c in celda if c["sampling_source"] == "chart_canal")
                w.writerow([FRAME_VERSION, fmt, dur, n_m, n_c,
                            f"{peso:.4f}" if peso != "" else "", n_a, n_m - n_a])
    print(f"\nAuditoria del diseno -> {path}")


# ------------------------------------------------------------------ BASE

def conectar(dsn: str):
    if psycopg is None:
        raise RuntimeError(
            "No hay driver de PostgreSQL. Casi seguro estas usando el Python del "
            "sistema en vez del del entorno:\n"
            "    .venv\\Scripts\\python build_reference_corpus.py ...")
    if _PG == "psycopg3":
        return psycopg.connect(dsn, row_factory=dict_row)
    return psycopg.connect(dsn)


def cursor(conn):
    if _PG == "psycopg3":
        return conn.cursor()
    return conn.cursor(cursor_factory=RealDictCursor)


INSERT = """
INSERT INTO content_items
    (source, external_id, url, title, channel, channel_id, description, tags,
     category_id, duration_seconds, upload_date, video_language,
     corpus, sampling_source, sampling_seed, stratum_format, stratum_duration,
     sampled_at, sampling_frame_version)
VALUES
    ('youtube', %(external_id)s, %(url)s, %(title)s, %(channel)s, %(channel_id)s,
     %(description)s, %(tags)s::jsonb, %(category_id)s, %(duration_seconds)s,
     %(upload_date)s, %(video_language)s,
     'referencia', %(sampling_source)s, %(sampling_seed)s,
     %(stratum_format)s, %(stratum_duration)s, now(), %(frame)s)
ON CONFLICT (external_id) DO NOTHING
"""


def ya_en_base(conn) -> set[str]:
    with cursor(conn) as cur:
        cur.execute("SELECT external_id FROM content_items WHERE source='youtube'")
        return {r["external_id"] for r in cur.fetchall()}


def insertar(conn, filas: list[dict]) -> int:
    n = 0
    with cursor(conn) as cur:
        for c in filas:
            cur.execute(INSERT, {**c,
                                 "tags": json.dumps(c.get("tags") or []),
                                 "frame": FRAME_VERSION})
            n += cur.rowcount or 0
    conn.commit()
    return n


# Estados de los que enrich_local.py ya no reintenta. Lo que no esta aca (o es
# NULL) sigue vivo en la cola.
ESTADOS_DEFINITIVOS = ["ok", "no_subs", "geo_blocked", "unavailable", "exhausted"]

# Se usa "= ANY(%s)" con una lista y no "IN %s" con una tupla: la segunda forma
# anda en psycopg2 pero psycopg3 adapta la tupla como registro compuesto y
# revienta. Este script acepta los dos drivers.
SQL_ESTADO = """
SELECT stratum_format AS fmt, stratum_duration AS dur,
       count(*)                                                      AS encolados,
       count(*) FILTER (WHERE coalesce(transcript_word_count,0) > 0)  AS con_texto,
       count(*) FILTER (WHERE enrichment_status IS NULL
                           OR NOT (enrichment_status = ANY(%(def)s))) AS pendientes,
       count(*) FILTER (WHERE enrichment_status = ANY(%(def)s)
                          AND coalesce(transcript_word_count,0) = 0)  AS fallidos
  FROM content_items
 WHERE corpus = 'referencia'
 GROUP BY 1, 2
"""


def estado_celdas(conn) -> dict:
    with cursor(conn) as cur:
        cur.execute(SQL_ESTADO, {"def": ESTADOS_DEFINITIVOS})
        return {(r["fmt"], r["dur"]): r for r in cur.fetchall()}


def informe(conn, objetivo_celda: int) -> None:
    est = estado_celdas(conn)
    if not est:
        print("Todavia no hay nada en el corpus de referencia. Corre --commit.")
        return

    print(f"{'formato':<20}{'duracion':<9}{'encol':>7}{'texto':>7}"
          f"{'cola':>7}{'fallo':>7}{'proyec':>8}")
    tot = Counter()
    en_riesgo = []
    for fmt in FORMATOS:
        for dur in DURACIONES:
            r = est.get((fmt, dur))
            if not r:
                continue
            # Proyeccion: lo que ya tiene texto mas lo que sigue vivo en la cola.
            # Es el numero honesto mientras el enriquecimiento no termino.
            proy = r["con_texto"] + r["pendientes"]
            marca = "" if proy >= objetivo_celda else f"  <- faltarian {objetivo_celda - proy}"
            if proy < objetivo_celda:
                en_riesgo.append((fmt, dur, objetivo_celda - proy))
            for k in ("encolados", "con_texto", "pendientes", "fallidos"):
                tot[k] += r[k]
            print(f"{fmt:<20}{dur:<9}{r['encolados']:>7}{r['con_texto']:>7}"
                  f"{r['pendientes']:>7}{r['fallidos']:>7}{proy:>8}{marca}")

    print(f"\n{'TOTAL':<29}{tot['encolados']:>7}{tot['con_texto']:>7}"
          f"{tot['pendientes']:>7}{tot['fallidos']:>7}")

    if tot["pendientes"]:
        print(f"\nQuedan {tot['pendientes']} en la cola "
              f"(~{tot['pendientes']/10:.0f} h a 10 por tanda horaria). "
              "Los numeros de 'texto' y 'fallo' son parciales.")
    else:
        print("\nCola vacia: el enriquecimiento termino.")

    with cursor(conn) as cur:
        cur.execute("""SELECT coalesce(enrichment_status,'(en cola)') AS estado,
                              count(*) AS n
                         FROM content_items WHERE corpus='referencia'
                        GROUP BY 1 ORDER BY 2 DESC""")
        print("\nPor estado:")
        for r in cur.fetchall():
            print(f"  {r['estado']:<16}{r['n']:>5}")

    if en_riesgo:
        print(f"\n{len(en_riesgo)} celdas quedarian por debajo de {objetivo_celda} "
              "aun si todo lo pendiente saliera bien.")
        print("Cuando la cola este vacia, corre --rellenar para reponerlas.")
    print("\nLos percentiles se calculan SOLO sobre corpus='referencia'. "
          "El historial personal no entra en la escala.")


def rehacer_banco(conn, por_celda: int, rng: random.Random) -> None:
    """Reconstruye el banco de suplentes desde el cache, mas grande, sin gastar
    cuota y sin tocar la muestra ya commiteada.

    No hay que volver a sortear nada: los suplentes son, por definicion, los
    candidatos del cache que no quedaron en la base. Se agrupan por celda y se
    toman hasta `por_celda`."""
    if not CACHE_PATH.exists():
        print(f"No hay cache en {CACHE_PATH}.")
        return
    cands = json.loads(CACHE_PATH.read_text(encoding="utf-8"))["candidatos"]
    en_base = ya_en_base(conn)
    libres: dict[tuple, list] = defaultdict(list)
    for c in cands:
        if c["external_id"] not in en_base:
            libres[(c["stratum_format"], c["stratum_duration"])].append(c)

    banco, flacas = [], []
    print(f"{'formato':<20}{'duracion':<9}{'libres':>8}{'al banco':>10}")
    for fmt in FORMATOS:
        for dur in DURACIONES:
            disp = libres.get((fmt, dur), [])
            rng.shuffle(disp)
            elegidos = disp[:por_celda]
            for c in elegidos:
                c["sample_rank"] = "reserva"
            banco.extend(elegidos)
            if len(elegidos) < por_celda:
                flacas.append((fmt, dur, len(elegidos)))
            print(f"{fmt:<20}{dur:<9}{len(disp):>8}{len(elegidos):>10}")

    RESERVA_PATH.write_text(json.dumps(banco, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(f"\nBanco de {len(banco)} suplentes -> {RESERVA_PATH.name} "
          f"(objetivo {por_celda} por celda). Cero unidades de cuota.")
    if flacas:
        print("\nCeldas con banco corto (no habia mas candidatos en el cache):")
        for fmt, dur, n in flacas:
            print(f"  {fmt}/{dur}: {n}")


def rellenar(conn, objetivo_celda: int) -> None:
    """Repone las bajas confirmadas del corpus desde el banco de suplentes.

    Al muestrear se eligieron 33 por celda, pero no todos van a llegar: algunos
    volveran sin subtitulos, bloqueados por pais o borrados. Esta funcion mira
    que celdas quedaron cortas POR BAJAS CONFIRMADAS y mete tantos suplentes
    como haga falta, de la misma celda, para volver a 33.

    La cuenta es  faltan = objetivo - (con_texto + todavia_en_cola).
    Contar lo pendiente como si fuera a salir bien es lo que evita el error
    obvio: correr esto con la cola llena veria 0 videos con texto en todas las
    celdas y volcaria el banco entero de una."""
    if not RESERVA_PATH.exists():
        print(f"No hay banco de suplentes en {RESERVA_PATH}. Se escribe con --commit.")
        return
    reserva = json.loads(RESERVA_PATH.read_text(encoding="utf-8"))
    est = estado_celdas(conn)
    if not est:
        print("El corpus de referencia esta vacio. Corre --commit primero.")
        return

    pendientes_tot = sum(r["pendientes"] for r in est.values())
    if pendientes_tot:
        print(f"Aviso: quedan {pendientes_tot} videos en la cola. Solo se repone "
              f"lo que ya fallo en firme; el resto se cuenta como que va a salir "
              f"bien. Podes correr esto otra vez cuando la cola se vacie.\n")

    existentes = ya_en_base(conn)
    usados_ahora: set[str] = set()
    a_insertar, sin_banco = [], []

    for fmt in FORMATOS:
        for dur in DURACIONES:
            r = est.get((fmt, dur))
            if not r:
                continue
            proyeccion = r["con_texto"] + r["pendientes"]
            falta = objetivo_celda - proyeccion
            if falta <= 0:
                continue
            disponibles = [c for c in reserva
                           if c["stratum_format"] == fmt
                           and c["stratum_duration"] == dur
                           and c["external_id"] not in existentes
                           and c["external_id"] not in usados_ahora]
            elegidos = disponibles[:falta]
            usados_ahora.update(c["external_id"] for c in elegidos)
            a_insertar.extend(elegidos)
            estado = f"{len(elegidos)} repuestos"
            if len(elegidos) < falta:
                sin_banco.append((fmt, dur, falta - len(elegidos)))
                estado += f", {falta - len(elegidos)} SIN SUPLENTE"
            print(f"  {fmt}/{dur}: {r['fallidos']} bajas, faltan {falta} -> {estado}")

    if a_insertar:
        n = insertar(conn, a_insertar)
        print(f"\n{n} suplentes encolados (~{n/10:.0f} h de enriquecimiento).")
    else:
        print("\nNada que reponer: todas las celdas llegan a "
              f"{objetivo_celda} con lo que ya tienen o lo que sigue en cola.")

    if sin_banco:
        print("\nEl banco se quedo corto en:")
        for fmt, dur, n in sin_banco:
            print(f"  {fmt}/{dur}: {n} sin cubrir")
        print("Esas celdas quedan por debajo del objetivo. Opciones: aceptarlo y "
              "declararlo, o volver a muestrear con --dry-run (cuesta cuota).")


# ------------------------------------------------------------------ MAIN

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="muestrea y reporta sin tocar la base")
    g.add_argument("--commit", action="store_true",
                   help="muestrea e inserta en content_items")
    g.add_argument("--informe", action="store_true",
                   help="estado de llenado por celda")
    g.add_argument("--rellenar", action="store_true",
                   help="repone celdas cortas desde corpus_reserva.json")
    g.add_argument("--rehacer-banco", action="store_true",
                   help="reconstruye el banco de suplentes desde el cache (0 cuota)")
    p.add_argument("--por-celda", type=int, default=20,
                   help="suplentes por celda al usar --rehacer-banco")
    p.add_argument("-n", "--total", type=int, default=400,
                   help="tamanio objetivo del corpus (default 400 = 33 por celda)")
    p.add_argument("--max-busquedas", type=int, default=55,
                   help="llamadas a search.list; cada una cuesta 100 unidades de 10.000")
    p.add_argument("--tope-canal", type=int, default=2,
                   help="maximo de videos por canal en todo el corpus")
    p.add_argument("--seed", type=int, default=20260810,
                   help="semilla del sorteo; fijarla hace el muestreo reproducible")
    p.add_argument("--cache", action="store_true",
                   help="reusa los candidatos ya descargados (0 unidades de cuota)")
    args = p.parse_args()

    # Sin esto, si el script muere a mitad la consola de Windows puede quedarse
    # con lineas en el buffer y parecer que "termino sin decir nada".
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    env = HERE.parent / ".env"
    if load_dotenv and env.exists():
        load_dotenv(env)

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("Falta DATABASE_URL en backend/.env", file=sys.stderr)
        return 2

    objetivo_celda = max(1, args.total // 12)

    if args.informe:
        with conectar(dsn) as conn:
            informe(conn, objetivo_celda)
        return 0

    if args.rellenar:
        with conectar(dsn) as conn:
            rellenar(conn, objetivo_celda)
        return 0

    if args.rehacer_banco:
        with conectar(dsn) as conn:
            rehacer_banco(conn, args.por_celda, random.Random(args.seed ^ 0xBA9C0))
        return 0

    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        print("Falta YOUTUBE_API_KEY en backend/.env", file=sys.stderr)
        return 2

    # Dos generadores independientes, a proposito. Si el sorteo compartiera el
    # generador con la recoleccion, su estado dependeria de cuantas veces tiro
    # el dado la recoleccion, y entonces --cache daria una muestra DISTINTA a la
    # de la corrida que genero el cache: revisar un dry-run y despues commitear
    # dejaria de garantizar que se commitea lo revisado.
    rng = random.Random(args.seed)                    # recoleccion
    rng_sorteo = random.Random(args.seed ^ 0x5EED)    # sorteo
    quota = Quota()
    yt = YT(key, quota)

    print("=" * 68)
    print(f"CORPUS DE REFERENCIA  v{VERSION}   marco {FRAME_VERSION}")
    print(f"objetivo {args.total} videos = {objetivo_celda} por celda x 12 celdas")
    print(f"semilla del sorteo: {args.seed} (fija: el muestreo es reproducible)")
    print("=" * 68)

    if args.cache:
        if not CACHE_PATH.exists():
            print(f"No hay cache en {CACHE_PATH}. Corre sin --cache primero.",
                  file=sys.stderr)
            return 2
        blob = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        candidatos = blob["candidatos"]
        print(f"\nCACHE: {len(candidatos)} candidatos de {blob.get('fecha')} "
              f"(marco {blob.get('frame')}). Cero unidades de cuota gastadas.")
        if blob.get("frame") != FRAME_VERSION:
            print(f"  AVISO: el cache es del marco {blob.get('frame')} y estas "
                  f"en {FRAME_VERSION}. Los estratos pueden no coincidir.")
    else:
        candidatos = recolectar(yt, rng, args.total, args.max_busquedas)
        print(f"\nCuota consumida: {quota.resumen()}")
        # Se guarda ANTES de sortear: recolectar cuesta ~6.000 de las 10.000
        # unidades diarias, y no tiene sentido volver a pagarlas si algo falla
        # mas abajo o si solo se quiere reprobar el sorteo con otra semilla.
        if candidatos:
            CACHE_PATH.write_text(json.dumps({
                "frame": FRAME_VERSION,
                "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "cuota": quota.usadas,
                "candidatos": candidatos,
            }, ensure_ascii=False), encoding="utf-8")
            print(f"Candidatos cacheados en {CACHE_PATH.name} "
                  f"(reusalos con --cache, sin gastar cuota)")

    if not candidatos:
        print("Sin candidatos. Revisa la API key.", file=sys.stderr)
        return 1

    # No repetir lo que ya esta en la base (el historial personal, sobre todo).
    with conectar(dsn) as conn:
        existentes = ya_en_base(conn)
    solapan = [c for c in candidatos if c["external_id"] in existentes]
    candidatos = [c for c in candidatos if c["external_id"] not in existentes]
    if solapan:
        print(f"{len(solapan)} candidatos ya estaban en la base (historial): descartados")

    try:
        muestra, reserva = sortear(candidatos, rng_sorteo, args.total, args.tope_canal)
        reportar(muestra, candidatos, objetivo_celda)
        escribir_auditoria(muestra, candidatos, AUDIT_PATH)
    except Exception:
        import traceback
        print("\n" + "!" * 68)
        print("FALLO EL SORTEO O EL REPORTE. Los candidatos estan a salvo en")
        print(f"{CACHE_PATH}: volve a correr con --cache, no gastas cuota.")
        print("!" * 68)
        traceback.print_exc()
        return 1

    if args.dry_run:
        print("\n--dry-run: no se inserto nada. Volve a correr con --commit.")
        return 0

    RESERVA_PATH.write_text(json.dumps(reserva, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(f"Reserva de {len(reserva)} videos -> {RESERVA_PATH}")

    with conectar(dsn) as conn:
        n = insertar(conn, muestra)
    print(f"\n{n} videos insertados en content_items con corpus='referencia'.")
    print("Quedan encolados: el worker horario (run_enrich.bat, 10 por tanda) "
          "los va a ir enriqueciendo.")
    print(f"Estimado: ~{n/10:.0f} h. Segui el avance con --informe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

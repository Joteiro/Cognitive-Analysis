# app/routes/admin.py
"""
admin.py -- la mitad de servidor del sitio (docs/index.html en GitHub Pages).

POR QUE EXISTE
    GitHub Pages sirve archivos estaticos: no puede guardar secretos ni leer la
    base con privilegios. Dos secciones del sitio necesitan justamente eso:
      - el dashboard EN VIVO (docs/dieta.html), que lee el historial;
      - la GENERACION de quizzes (docs/generar.html), que llama a Gemini con
        una clave de API que no puede viajar al navegador.
    Este router hace esas dos cosas y nada mas.

LA CLAVE
    Todo exige la cabecera X-Clave-Admin igual a la variable de entorno
    ADMIN_KEY. Sin ADMIN_KEY (o con una de menos de 16 caracteres) responde
    503: el modo admin queda APAGADO, nunca abierto. La comparacion es de
    tiempo constante (hmac.compare_digest).

CERO LOGICA DUPLICADA
    Nada se reimplementa aca; se importan las mismas funciones que usan los
    scripts locales:
      - filas del dashboard: build_dashboard.SQL + fila_compacta + cargar_meta
      - candidatos: generar_quiz.CONSULTA + discrepancias_formato
      - generacion: generar_quiz.procesar_video (3 filtros + linea de base)
      - guardado: cargar_quiz.cargar_preguntas (tambien las descartadas)
    Si el criterio cambia en un script, la web cambia con el.

LO QUE NO DEVUELVE A PROPOSITO
    El resultado de una generacion NO trae el texto de las preguntas ni la
    respuesta correcta: solo cuantas sobrevivieron y por que cayeron las
    otras. Quien genera es quien despues contesta; si viera las preguntas,
    su respuesta mediria lectura, no retencion.
"""
from __future__ import annotations

import hmac
import logging
import os
import random
import sys
import threading
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from ..database import engine
from .panel import CANDIDATOS_ESCALA

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# La persona dueña del historial. Sus videos YA los vio (content_items.watched_at
# es su reloj), asi que al sumarlos a su cola el visionado se registra con esa
# fecha: los dias hasta la respuesta salen contra cuando lo vio de verdad, no
# contra cuando se genero el quiz.
PERSONA = os.getenv("PERSONA_PROPIA", "juan-01")

# Mismos valores por defecto que generar_quiz.py en la consola.
CORPUS = "historial"
MIN_PALABRAS = 400            # --min-palabras
SEMILLA = 20260814            # --semilla (aca se le suma el id: una por video)
FORMATOS = ("todos", "informativo", "entretenimiento", "deporte_gaming",
            "practico_personal")

# Control por defecto: Gemini 2.5 Flash-Lite. Es la salida operativa desde el
# 403 de Groq (2026-08-30): mismo proveedor que el generador pero modelo
# distinto y mas chico. Si Groq vuelve: QUIZ_PROVEEDOR_CONTROL=groq.
CONTROL_POR_DEFECTO = {"gemini": "gemini-2.5-flash-lite", "groq": "openai/gpt-oss-20b"}

CLAVE_MINIMA = 16


# ------------------------------------------------------------------ utilidades

@lru_cache(maxsize=None)
def _script(nombre: str):
    """Importa un script de backend/scripts, igual que panel.py."""
    ruta = Path(__file__).resolve().parents[2] / "scripts"
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))
    return __import__(nombre)


def exigir_clave(x_clave_admin: Optional[str] = Header(default=None)) -> None:
    esperada = os.getenv("ADMIN_KEY", "")
    if len(esperada) < CLAVE_MINIMA:
        raise HTTPException(503, "El modo admin esta apagado en el servidor: falta "
                                 f"ADMIN_KEY (o tiene menos de {CLAVE_MINIMA} caracteres).")
    if not x_clave_admin or not hmac.compare_digest(x_clave_admin.encode("utf-8"),
                                                    esperada.encode("utf-8")):
        raise HTTPException(401, "Clave incorrecta.")


@contextmanager
def _cursor(commit: bool = False):
    """Cursor psycopg2 crudo: los scripts usan parametros %(nombre)s y
    RealDictCursor, y asi se reutilizan sus consultas tal cual."""
    import psycopg2.extras
    conn = engine.raw_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        if commit:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fecha(dt) -> Optional[str]:
    if dt is None:
        return None
    return _script("build_dashboard").a_local(dt).strftime("%Y-%m-%d")


def _escala() -> Path:
    for p in CANDIDATOS_ESCALA:
        if p and p.exists():
            return p
    raise HTTPException(500, "No se encontro escala_referencia.json en el servidor.")


# ------------------------------------------------------------------ ping

@router.get("/ping", dependencies=[Depends(exigir_clave)])
def ping():
    """Para que la pagina valide la clave antes de guardarla."""
    return {"ok": True, "persona": PERSONA, "generacion": _config_generacion()[0] is None}


# ------------------------------------------------------------------ dieta

@router.get("/dieta", dependencies=[Depends(exigir_clave)])
def dieta():
    """Las filas del dashboard, leidas ahora. Mismas que la foto local."""
    bd = _script("build_dashboard")
    with _cursor() as cur:
        cur.execute(bd.SQL)
        crudas = cur.fetchall()
        cur.execute(bd.SQL_PENDIENTES)
        pend = cur.fetchone()
    try:
        filas = [bd.fila_compacta(r) for r in crudas]
    except ValueError as e:
        # fila_compacta aborta si un panel no trae los 8 descriptores: reindexar
        # por posicion correria los percentiles sin avisar. Se dice cual.
        raise HTTPException(500, str(e))
    return {
        "filas": filas,
        "meta": bd.cargar_meta(_escala()),
        "afuera": {"sin_panel": pend["sin_panel"],
                   "sin_transcripcion": pend["sin_transcripcion"]},
        "leido_at": _ahora(),
    }


# ------------------------------------------------------------------ candidatos

def _consulta_candidatos(columnas: str = "c.*", extra: str = "") -> str:
    """La consulta de generar_quiz.py envuelta, sin copiar su WHERE.

    Afuera se piden solo las columnas que hacen falta: para listar, la
    transcripcion no viaja por la red.
    """
    gq = _script("generar_quiz")
    return (f"select {columnas}, ci.watched_at from ({gq.CONSULTA}) c "
            f"join content_items ci on ci.id = c.id {extra}")


def _params(formato: str) -> dict:
    return {"formato": formato, "corpus": CORPUS, "min_palabras": MIN_PALABRAS,
            "saltar_con_quiz": True}


@router.get("/quiz/candidatos", dependencies=[Depends(exigir_clave)])
def candidatos(formato: str = Query("todos")):
    if formato not in FORMATOS:
        raise HTTPException(422, f"formato debe ser uno de {FORMATOS}")
    gq = _script("generar_quiz")
    sql = _consulta_candidatos(
        "c.id, c.title, c.channel, c.formato, c.transcript_word_count, c.duration_seconds",
        "order by ci.watched_at desc nulls last")
    with _cursor() as cur:
        cur.execute(sql, _params(formato))
        filas = cur.fetchall()
    marcados = gq.discrepancias_formato()
    videos = [{
        "id": r["id"], "titulo": r["title"], "canal": r["channel"],
        "formato": r["formato"], "palabras": r["transcript_word_count"],
        "minutos": round((r["duration_seconds"] or 0) / 60.0, 1),
        "visto": _fecha(r["watched_at"]),
    } for r in filas if r["id"] not in marcados]
    return {"videos": videos, "excluidos_por_formato": len(filas) - len(videos)}


# ------------------------------------------------------------------ generacion

_TRABAJOS: dict = {}
_UNO_A_LA_VEZ = threading.Lock()


def _config_generacion():
    """(error, config). No toca la red: sirve para contestar 503 al instante."""
    gq = _script("generar_quiz")
    prov = os.getenv("QUIZ_PROVEEDOR", "gemini")
    prov_c = os.getenv("QUIZ_PROVEEDOR_CONTROL", "gemini")
    if prov not in gq.PROVEEDORES or prov_c not in gq.PROVEEDORES:
        return f"Proveedor desconocido: {prov}/{prov_c}", None
    clave = next((os.getenv(k) for k in gq.PROVEEDORES[prov]["claves"] if os.getenv(k)), None)
    clave_c = next((os.getenv(k) for k in gq.PROVEEDORES[prov_c]["claves"] if os.getenv(k)), None)
    if not clave:
        return f"Falta {' o '.join(gq.PROVEEDORES[prov]['claves'])} en el servidor.", None
    if not clave_c:
        return f"Falta {' o '.join(gq.PROVEEDORES[prov_c]['claves'])} en el servidor.", None
    return None, {
        "prov": prov, "clave": clave, "modelo": os.getenv("QUIZ_MODELO") or None,
        "prov_c": prov_c, "clave_c": clave_c,
        "modelo_c": os.getenv("QUIZ_MODELO_CONTROL") or CONTROL_POR_DEFECTO.get(prov_c),
    }


def _clientes(cfg: dict):
    """Generador y control, con las mismas reglas que main() de generar_quiz.py.

    Una diferencia deliberada: la consola AVISA si el control termina siendo el
    mismo modelo que genera; la web se NIEGA. Sin control independiente la
    linea de base mide de menos (el modelo reconoce sus propios tics), y desde
    una pagina nadie lee el aviso.
    """
    gq = _script("generar_quiz")
    cfg_g = gq.PROVEEDORES[cfg["prov"]]
    gen = gq.ClienteLLM(cfg["clave"], cfg_g, cfg["modelo"])
    if cfg_g["cabeceras_cupo"]:
        # Groq: la sonda aprende el cupo por minuto antes de la primera
        # generacion (misma sonda que main()).
        try:
            gen.pedir([{"role": "user", "content": "Responde solo con el json {\"ok\":1}"}],
                      temperatura=0.0, max_salida=gq.MIN_SALIDA)
        except Exception as e:
            logger.warning(f"sonda de cupo fallo: {e}")
    control = gq.ClienteLLM(cfg["clave_c"], gq.PROVEEDORES[cfg["prov_c"]], cfg["modelo_c"])
    control.esfuerzo = None
    if control.modelo == gen.modelo:
        raise RuntimeError(f"El control ({control.modelo}) es el mismo modelo que genera. "
                           "Cambia QUIZ_MODELO_CONTROL.")
    return gen, control, cfg_g


def _resumen(r: dict) -> dict:
    """Lo que se le muestra a quien genero: cantidades, nunca el texto."""
    ps = r["preguntas"]
    vivas = [p for p in ps if p.get("sobrevive")]
    return {
        "generadas": len(ps),
        "utilizables": len(vivas),
        "descartes": dict(Counter(p.get("descarte") or "?" for p in ps if not p.get("sobrevive"))),
        "tipos": dict(Counter(p.get("tipo") or "?" for p in vivas)),
        "linea_base": {
            "acerto": sum(1 for p in vivas if p.get("linea_base_acerto") is True),
            "fallo": sum(1 for p in vivas if p.get("linea_base_acerto") is False),
            "sin_dato": sum(1 for p in vivas if p.get("linea_base_acerto") is None),
        },
        "modelo": r.get("modelo"), "modelo_control": r.get("modelo_control"),
        "version": r.get("version"),
        "transcripcion_recortada": r.get("transcripcion_recortada"),
    }


def _correr(tid: str, video: dict, sumar: bool, cfg: dict) -> None:
    t = _TRABAJOS[tid]
    try:
        gq = _script("generar_quiz")
        cq = _script("cargar_quiz")
        gen, control, cfg_g = _clientes(cfg)
        # Igual que main(): la pausa sale del proveedor que genera y en Gemini
        # la transcripcion va entera (el recorte sesgaba las preguntas).
        gq.PAUSA_SEGUNDOS = cfg_g["pausa"]
        max_palabras = 1_000_000 if cfg["prov"] == "gemini" else gq.MAX_PALABRAS
        t["fase"] = "generando"
        r = gq.procesar_video(gen, video, random.Random(SEMILLA + video["id"]),
                              max_palabras, control)
        t["llamadas"] = gen.llamadas + control.llamadas
        if r.get("error"):
            t.update(estado="error", error=r["error"], fin=time.time())
            return
        t["fase"] = "guardando"
        resumen = _resumen(r)
        with _cursor(commit=True) as cur:
            cq.cargar_preguntas(cur, [r])
            resumen["sumado_a_cola"] = False
            if sumar and resumen["utilizables"]:
                _asegurar_persona(cur)
                resumen["sumado_a_cola"] = _sumar_a_cola(cur, [video["id"]]) > 0
        t.update(estado="listo", resumen=resumen, fin=time.time())
    except Exception as e:
        logger.exception(f"generacion {tid} fallo")
        t.update(estado="error", error=f"{type(e).__name__}: {e}"[:600], fin=time.time())
    finally:
        _UNO_A_LA_VEZ.release()


class PedidoGenerar(BaseModel):
    content_item_id: int
    sumar_a_cola: bool = True


@router.post("/quiz/generar", status_code=202, dependencies=[Depends(exigir_clave)])
def generar(pedido: PedidoGenerar):
    error, cfg = _config_generacion()
    if error:
        raise HTTPException(503, error)
    gq = _script("generar_quiz")
    with _cursor() as cur:
        cur.execute(_consulta_candidatos(extra="where c.id = %(id)s"),
                    {**_params("todos"), "id": pedido.content_item_id})
        fila = cur.fetchone()
    if fila is None:
        raise HTTPException(404, "Ese video no es candidato: no existe, no es apto, "
                                 "tiene menos de 400 palabras o ya tiene quiz.")
    if fila["id"] in gq.discrepancias_formato():
        raise HTTPException(409, "El modelo ve otro formato para este video "
                                 "(formato_verificado.json): el script tambien lo salta.")
    if not _UNO_A_LA_VEZ.acquire(blocking=False):
        raise HTTPException(409, "Ya hay una generacion en curso. Espera a que termine.")
    try:
        # Se podan los trabajos viejos: viven en memoria y solo sirven un rato.
        for k in [k for k, v in _TRABAJOS.items() if time.time() - v["inicio"] > 3600]:
            _TRABAJOS.pop(k, None)
        tid = uuid.uuid4().hex[:12]
        _TRABAJOS[tid] = {"id": tid, "estado": "corriendo", "fase": "preparando",
                          "content_item_id": fila["id"], "titulo": fila["title"],
                          "inicio": time.time()}
        threading.Thread(target=_correr, args=(tid, dict(fila), pedido.sumar_a_cola, cfg),
                         daemon=True, name=f"quiz-{tid}").start()
    except Exception:
        _UNO_A_LA_VEZ.release()
        raise
    return {"trabajo": tid}


@router.get("/quiz/trabajo/{tid}", dependencies=[Depends(exigir_clave)])
def trabajo(tid: str):
    t = _TRABAJOS.get(tid)
    if t is None:
        raise HTTPException(404, "No encuentro ese trabajo. Si el servidor se reinicio "
                                 "(Render lo duerme y lo despierta), se perdio: "
                                 "fijate si el video sigue en la lista y volve a generarlo.")
    fin = t.get("fin") or time.time()
    return {**t, "segundos": round(fin - t["inicio"])}


# ------------------------------------------------------------------ cola propia

def _asegurar_persona(cur) -> dict:
    """Da de alta a la persona si no existe (alta_participante es idempotente)."""
    cur.execute("select seudonimo, token, enlace from alta_participante(%(p)s)", {"p": PERSONA})
    return cur.fetchone()


def _sumar_a_cola(cur, ids: List[int]) -> int:
    """Asigna videos del historial a PERSONA y registra que ya los vio.

    Solo videos con watched_at: es la fecha en que los vio. Si ya tenian un
    visionado registrado, no se toca (on conflict do nothing).
    """
    cur.execute("""
        insert into participante_asignacion (persona_id, content_item_id, orden)
        select %(p)s, ci.id, 0 from content_items ci
         where ci.id = any(%(ids)s) and ci.watched_at is not null
        on conflict (persona_id, content_item_id) do nothing""",
                {"p": PERSONA, "ids": list(ids)})
    n = cur.rowcount
    cur.execute("""
        insert into quiz_visionados (persona_id, content_item_id, visto_at)
        select %(p)s, ci.id, ci.watched_at from content_items ci
         where ci.id = any(%(ids)s) and ci.watched_at is not null
        on conflict (persona_id, content_item_id) do nothing""",
                {"p": PERSONA, "ids": list(ids)})
    return n


SQL_PENDIENTES_PERSONA = """
select ci.id, ci.title, ci.channel, ci.watched_at, count(q.id) as preguntas,
       exists (select 1 from participante_asignacion a
                where a.persona_id = %(p)s and a.content_item_id = ci.id) as en_cola
  from content_items ci
  join quiz_preguntas q on q.content_item_id = ci.id and q.utilizable
 where ci.watched_at is not null      -- solo lo que se puede sumar: videos de SU historial
   and not exists (select 1 from quiz_respuestas r
                    where r.pregunta_id = q.id and r.persona_id = %(p)s)
 group by ci.id
 order by ci.watched_at nulls last, ci.id
"""


def _estado_cola(cur) -> dict:
    alta = _asegurar_persona(cur)
    cur.execute(SQL_PENDIENTES_PERSONA, {"p": PERSONA})
    videos = [{"id": r["id"], "titulo": r["title"], "canal": r["channel"],
               "visto": _fecha(r["watched_at"]), "preguntas": r["preguntas"],
               "en_cola": r["en_cola"]} for r in cur.fetchall()]
    return {"persona": PERSONA, "enlace": alta["enlace"], "videos": videos,
            "en_cola": sum(1 for v in videos if v["en_cola"]),
            "fuera_de_cola": sum(1 for v in videos if not v["en_cola"])}


@router.get("/quiz/cola", dependencies=[Depends(exigir_clave)])
def cola():
    """Lo que PERSONA tiene para contestar, y su enlace. Commit porque la
    primera vez la da de alta."""
    with _cursor(commit=True) as cur:
        return _estado_cola(cur)


class PedidoCola(BaseModel):
    content_item_ids: Optional[List[int]] = None   # None = todos los pendientes


@router.post("/quiz/cola", dependencies=[Depends(exigir_clave)])
def sumar_a_cola(pedido: PedidoCola):
    with _cursor(commit=True) as cur:
        estado = _estado_cola(cur)
        ids = pedido.content_item_ids
        if ids is None:
            ids = [v["id"] for v in estado["videos"] if not v["en_cola"]]
        sumados = _sumar_a_cola(cur, ids) if ids else 0
        estado = _estado_cola(cur)
    return {"sumados": sumados, **estado}

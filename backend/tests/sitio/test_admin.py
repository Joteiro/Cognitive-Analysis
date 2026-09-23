"""Prueba del router /admin contra la app REAL y una base Postgres local.

Se simula solo la RED hacia Gemini (requests.Session dentro de generar_quiz),
no las clases: ClienteLLM se construye de verdad, procesar_video corre entero
con sus tres filtros y la linea de base, y cargar_preguntas escribe en la base.
"""
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import types

import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sembrar  # noqa: E402

CLAVE = "clave-de-prueba-larga-123"
os.environ.update({
    "DATABASE_URL": sembrar.DSN,
    "ADMIN_KEY": CLAVE,
    "GEMINI_API_KEY": "falsa",
})
sys.path.insert(0, str(sembrar.RAIZ / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
import requests  # noqa: E402

from app.main import app  # noqa: E402
from app.routes import admin  # noqa: E402

gq = admin._script("generar_quiz")

# ------------------------------------------------------------ red simulada

PREGUNTAS = [
    dict(pregunta="¿Cuántos rollos guardaba la biblioteca según el narrador?",
         opciones=["cuarenta mil", "diez mil", "noventa mil", "doce mil"], correcta=0,
         cita=sembrar.FRASES[0], tipo="dato"),
    dict(pregunta="¿Qué emperador ordenó el incendio?",
         opciones=["Julio César", "Nerón", "Augusto", "Calígula"], correcta=0,
         cita="el emperador ordeno quemar todos los rollos de la biblioteca en una sola noche",
         tipo="dato"),
    dict(pregunta="¿Con qué compara el incendio?",
         opciones=["con la perdida de un disco duro sin copia de seguridad en una oficina moderna "
                   "llena de ordenadores viejos", "un rayo", "una guerra", "un robo"],
         correcta=0, cita=sembrar.FRASES[1], tipo="relacion"),
    dict(pregunta="¿Cuál sostiene el narrador que fue la causa principal?",
         opciones=["el abandono presupuestario", "un unico gran incendio",
                   "una invasion militar", "un terremoto repentino"], correcta=0,
         cita=sembrar.FRASES[2], tipo="argumento"),
    dict(pregunta="¿A qué historiador cita para fechar el primer daño?",
         opciones=["Plutarco", "Herodoto", "Tucidides", "Polibio"], correcta=0,
         cita=sembrar.FRASES[3], tipo="dato"),
    dict(pregunta="¿Por qué dice que sobrevive el mito?",
         opciones=["es mas facil culpar a un villano", "porque lo enseñan en la escuela",
                   "porque hay pruebas del incendio", "porque lo dijo un emperador"],
         correcta=0, cita=sembrar.FRASES[5], tipo="argumento"),
]
CORRECTAS = {p["pregunta"]: p["opciones"][p["correcta"]] for p in PREGUNTAS}

LLAMADAS = {"models": 0, "gen": 0, "ctrl": 0, "modelos_pedidos": []}
PUERTA = threading.Event()
PUERTA.set()
DORMIDO = []


class Resp:
    def __init__(self, cuerpo, status=200):
        self.status_code = status
        self._c = cuerpo
        self.text = json.dumps(cuerpo)
        self.headers = {}

    def json(self):
        return self._c

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(self.status_code)


class SesionFalsa:
    def __init__(self):
        self.headers = {}

    def get(self, url, timeout=None):
        LLAMADAS["models"] += 1
        return Resp({"data": [{"id": "models/gemini-2.5-flash"},
                              {"id": "models/gemini-2.5-flash-lite"}]})

    def post(self, url, json=None, timeout=None):
        sistema = json["messages"][0]["content"]
        usuario = json["messages"][-1]["content"]
        LLAMADAS["modelos_pedidos"].append(json["model"])
        if sistema.startswith("Eres un disenador"):
            LLAMADAS["gen"] += 1
            PUERTA.wait(10)
            contenido = __import__("json").dumps({"preguntas": PREGUNTAS}, ensure_ascii=False)
        else:
            LLAMADAS["ctrl"] += 1
            preg = re.search(r"PREGUNTA: (.*)", usuario).group(1).strip()
            opciones = re.findall(r"^(\d)\. (.*)$", usuario, re.M)
            idx_ok = next(int(i) for i, o in opciones if o == CORRECTAS[preg])
            # el control "adivina" solo la de la biblioteca
            eleccion = idx_ok if "rollos" in preg else (idx_ok + 1) % 4
            contenido = __import__("json").dumps({"eleccion": eleccion, "seguridad": "media"})
        return Resp({"choices": [{"message": {"content": contenido}}],
                     "usage": {"total_tokens": 100}})


gq.requests = types.SimpleNamespace(Session=SesionFalsa,
                                    RequestException=requests.RequestException)
gq.time = types.SimpleNamespace(sleep=lambda s: DORMIDO.append(s), time=time.time)

# ------------------------------------------------------------ utilidades

cli = TestClient(app)
H = {"X-Clave-Admin": CLAVE}
FALLOS = []


def check(nombre, cond, detalle=""):
    print(("ok   " if cond else "FALLO") + f" {nombre}" + (f"  -> {detalle}" if not cond and detalle else ""))
    if not cond:
        FALLOS.append(nombre)


def sql(q, args=None):
    with psycopg2.connect(sembrar.DSN) as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(q, args)
        return cur.fetchall() if cur.description else None


def esperar(tid, limite=20):
    t0 = time.time()
    while time.time() - t0 < limite:
        r = cli.get(f"/admin/quiz/trabajo/{tid}", headers=H).json()
        if r["estado"] != "corriendo":
            return r
        time.sleep(0.05)
    raise TimeoutError(tid)


# ------------------------------------------------------------ pruebas

sembrar.sembrar()

# 1. La clave
os.environ["ADMIN_KEY"] = ""
check("sin ADMIN_KEY -> 503", cli.get("/admin/ping", headers=H).status_code == 503)
os.environ["ADMIN_KEY"] = "corta"
check("ADMIN_KEY corta -> 503", cli.get("/admin/ping", headers={"X-Clave-Admin": "corta"}).status_code == 503)
os.environ["ADMIN_KEY"] = CLAVE
check("sin cabecera -> 401", cli.get("/admin/ping").status_code == 401)
check("clave mala -> 401", cli.get("/admin/ping", headers={"X-Clave-Admin": CLAVE + "x"}).status_code == 401)
r = cli.get("/admin/ping", headers=H)
check("clave buena -> 200", r.status_code == 200 and r.json()["generacion"] is True, r.text)
check("todas las rutas /admin exigen clave",
      all(cli.request(m, p).status_code == 401 for m, p in [
          ("GET", "/admin/dieta"), ("GET", "/admin/quiz/candidatos"),
          ("POST", "/admin/quiz/generar"), ("GET", "/admin/quiz/trabajo/x"),
          ("GET", "/admin/quiz/cola"), ("POST", "/admin/quiz/cola")]))
pre = cli.options("/admin/dieta", headers={"Origin": "https://joteiro.github.io",
                                           "Access-Control-Request-Method": "GET",
                                           "Access-Control-Request-Headers": "x-clave-admin"})
check("preflight CORS acepta X-Clave-Admin", pre.status_code == 200 and
      "x-clave-admin" in pre.headers.get("access-control-allow-headers", "").lower(), dict(pre.headers))

# 2. Dieta en vivo == foto
r = cli.get("/admin/dieta", headers=H)
d = r.json()
foto = sembrar.foto()
check("dieta: 200", r.status_code == 200, r.text[:300])
check(f"dieta: mismas {len(foto)} filas que la foto (fecha local incluida)", d["filas"] == foto,
      next((f"{a} != {b}" for a, b in zip(d["filas"], foto) if a != b), len(d["filas"])))
check("dieta: afuera = 2 sin panel, 1 sin transcripcion",
      d["afuera"] == {"sin_panel": 2, "sin_transcripcion": 1}, d["afuera"])
check("dieta: meta con frame_version y 8 descriptores",
      "frame_version" in d["meta"] and len(d["meta"]["descriptores"]) == 8)
# panel incompleto -> 500 con el titulo, no filas corridas
sql("update content_features set panel = panel - 7 where content_item_id = 1000")
r = cli.get("/admin/dieta", headers=H)
check("dieta: panel incompleto -> 500 explicito", r.status_code == 500 and "no trae" in r.text, r.text[:200])
sembrar.sembrar()

# 3. Candidatos
r = cli.get("/admin/quiz/candidatos", headers=H).json()
ids = [v["id"] for v in r["videos"]]
check("candidatos: solo 3002 y 3001, mas reciente primero", ids == [3002, 3001], ids)
check("candidatos: 1 excluido por formato (id 2)", r["excluidos_por_formato"] == 1, r)
check("candidatos: filtro por formato",
      [v["id"] for v in cli.get("/admin/quiz/candidatos?formato=informativo", headers=H).json()["videos"]] == [3001])
check("candidatos: formato invalido -> 422",
      cli.get("/admin/quiz/candidatos?formato=x", headers=H).status_code == 422)
check("candidatos: no viaja la transcripcion", "transcript" not in json.dumps(r))

# 4. Generar: validaciones
check("generar: video inexistente -> 404",
      cli.post("/admin/quiz/generar", json={"content_item_id": 99999}, headers=H).status_code == 404)
check("generar: ya tiene quiz -> 404",
      cli.post("/admin/quiz/generar", json={"content_item_id": 3005}, headers=H).status_code == 404)
check("generar: discrepante -> 409",
      cli.post("/admin/quiz/generar", json={"content_item_id": 2}, headers=H).status_code == 409)
os.environ.pop("GEMINI_API_KEY")
r = cli.post("/admin/quiz/generar", json={"content_item_id": 3001}, headers=H)
check("generar: sin GEMINI_API_KEY -> 503 al instante", r.status_code == 503 and "GEMINI" in r.text, r.text)
os.environ["GEMINI_API_KEY"] = "falsa"

# 5. Generar de verdad (red simulada), con la puerta cerrada para probar el candado
PUERTA.clear()
r = cli.post("/admin/quiz/generar", json={"content_item_id": 3001}, headers=H)
check("generar: 202", r.status_code == 202, r.text)
tid = r.json()["trabajo"]
r2 = cli.post("/admin/quiz/generar", json={"content_item_id": 3002}, headers=H)
check("generar: segundo en paralelo -> 409", r2.status_code == 409, r2.text)
PUERTA.set()
t = esperar(tid)
check("generar: termina listo", t["estado"] == "listo", t)
res = t.get("resumen", {})
print("     resumen:", json.dumps(res, ensure_ascii=False))
check("generar: 6 generadas, 4 utilizables", (res.get("generadas"), res.get("utilizables")) == (6, 4))
check("generar: descartes por los filtros reales",
      res.get("descartes") == {"cita_no_verificable": 1, "opciones_desbalanceadas": 1}, res.get("descartes"))
check("generar: linea de base 1 acierto / 3 fallos",
      res.get("linea_base") == {"acerto": 1, "fallo": 3, "sin_dato": 0}, res.get("linea_base"))
check("generar: modelos = flash + flash-lite",
      (res.get("modelo"), res.get("modelo_control")) == ("gemini-2.5-flash", "gemini-2.5-flash-lite"))
check("generar: control con flash-lite de verdad",
      LLAMADAS["modelos_pedidos"].count("gemini-2.5-flash-lite") == 4, LLAMADAS)
check("generar: pausa de Gemini (6.5 s) antes de cada control", DORMIDO.count(6.5) == 4, DORMIDO)
dump = json.dumps(t, ensure_ascii=False)
check("generar: el resultado NO trae el texto de ninguna pregunta ni cita",
      not any(p["pregunta"] in dump or p["cita"] in dump or p["opciones"][0] in dump for p in PREGUNTAS))
filas = sql("select n_orden, utilizable, descarte, version, modelo, modelo_control, linea_base_acerto "
            "from quiz_preguntas where content_item_id = 3001 order by n_orden")
check("generar: 6 filas en quiz_preguntas (tambien las descartadas)", len(filas) == 6, filas)
check("generar: 4 utilizables en la base", sum(f["utilizable"] for f in filas) == 4)
check("generar: version del instrumento = la del script", {f["version"] for f in filas} == {gq.VERSION})
check("generar: sumado a la cola de juan-01", res.get("sumado_a_cola") is True)
vis = sql("select v.visto_at = ci.watched_at as igual from quiz_visionados v "
          "join content_items ci on ci.id = v.content_item_id "
          "where v.persona_id = 'juan-01' and v.content_item_id = 3001")
check("generar: visionado registrado con la fecha del historial", vis == [{"igual": True}], vis)
check("generar: 3001 ya no es candidato",
      3001 not in [v["id"] for v in cli.get("/admin/quiz/candidatos", headers=H).json()["videos"]])
check("generar: trabajo inexistente -> 404",
      cli.get("/admin/quiz/trabajo/nada", headers=H).status_code == 404)

# 6. Control igual al generador -> la web se niega
os.environ["QUIZ_MODELO_CONTROL"] = "gemini-2.5-flash"
t = esperar(cli.post("/admin/quiz/generar", json={"content_item_id": 3002}, headers=H).json()["trabajo"])
check("generar: control = generador -> error, nada guardado",
      t["estado"] == "error" and "mismo modelo" in t["error"] and
      not sql("select 1 from quiz_preguntas where content_item_id = 3002"), t)
os.environ.pop("QUIZ_MODELO_CONTROL")
check("generar: el candado se libera tras un error",
      cli.post("/admin/quiz/generar", json={"content_item_id": 3002, "sumar_a_cola": False},
               headers=H).status_code == 202)
time.sleep(0.5)
check("generar: sumar_a_cola=False no asigna",
      not sql("select 1 from participante_asignacion where content_item_id = 3002"))

# 7. La cola propia
c = cli.get("/admin/quiz/cola", headers=H).json()
check("cola: persona juan-01 con enlace al sitio nuevo",
      c["persona"] == "juan-01" and "/Cognitive-Analysis/quiz.html?t=" in c["enlace"], c.get("enlace"))
por_id = {v["id"]: v for v in c["videos"]}
check("cola: 3001 en cola, 3002 fuera (no se sumo)",
      por_id.get(3001, {}).get("en_cola") is True and por_id.get(3002, {}).get("en_cola") is False, por_id)
check("cola: no lista lo que no se puede sumar (nucleo sin fecha de historial)",
      609 not in por_id, por_id)
r = cli.post("/admin/quiz/cola", json={}, headers=H).json()
check("cola: POST sin ids suma solo los que tienen fecha de historial (3002 y 3005, no el nucleo)",
      r["sumados"] == 2 and {v["id"] for v in r["videos"] if v["en_cola"]} == {3001, 3002, 3005}, r)
check("cola: idempotente", cli.post("/admin/quiz/cola", json={}, headers=H).json()["sumados"] == 0)

# 8. obtener_quiz v3 (la RPC que usa la pagina)
token = c["enlace"].split("t=")[1]
q = sql("select obtener_quiz(%s) as q", (token,))[0]["q"]
vids = {v["content_item_id"]: v for v in q["videos"]}
check("rpc: juan-01 ve sus asignados (3001, 3002, 3005), no el nucleo", set(vids) == {3001, 3002, 3005}, set(vids))
check("rpc: trae visto_at y la hora del servidor", vids[3001]["visto_at"] is not None and "ahora" in q)
check("rpc: sin respuesta correcta ni cita",
      all(set(p) == {"id", "pregunta", "opciones", "dificil"} for v in q["videos"] for p in v["preguntas"]))
ps = vids[3001]["preguntas"]
out = sql("select registrar_respuestas(%s, %s::jsonb) as r",
          (token, json.dumps([{"pregunta_id": p["id"], "eleccion": 0, "segundos": 3} for p in ps])))[0]["r"]
check("rpc: registrar_respuestas guarda las 4", out["n"] == 4, out)
dias = sql("select min(dias_transcurridos) d from quiz_respuestas where persona_id='juan-01'")[0]["d"]
check("rpc: dias contra la fecha del historial (>= 1)", dias is not None and float(dias) >= 1, dias)
q = sql("select obtener_quiz(%s) as q", (token,))[0]["q"]
check("rpc: lo contestado desaparece de la cola", {v["content_item_id"] for v in q["videos"]} == {3002, 3005})
q = sql("select obtener_quiz('tok-luna') as q")[0]["q"]
check("rpc: luna ve el nucleo SIN el 623 (no tiene preguntas utilizables)",
      [v["content_item_id"] for v in q["videos"]] == [609, 610, 94], q["videos"])
try:
    sql("select obtener_quiz('nada')")
    check("rpc: token invalido -> excepcion", False)
except psycopg2.Error as e:
    check("rpc: token invalido -> excepcion", "token invalido" in str(e))

print()
print("TODO OK" if not FALLOS else f"{len(FALLOS)} FALLOS: {FALLOS}")
sys.exit(1 if FALLOS else 0)

"""Pruebas del panel sin base de datos ni red.

METODO (segun lo aprendido el 2026-08-17)
Se simula la CAPA EXTERNA —sqlalchemy y el motor de base de datos— y se importa
el modulo de verdad. Nada de reimplementar leer_contra() aca para compararla
contra si misma: eso probaria la copia, no el codigo que se despliega.

Ademas se corre un chequeo de codigo muerto con ast, porque la edicion de este
archivo movio bloques dentro de funciones y ese es justo el sintoma que
py_compile no ve.
"""
import ast
import json
import sys
import types
from pathlib import Path

# backend/tests/ -> raiz del repositorio
RAIZ = Path(__file__).resolve().parents[2]
PANEL_PY = RAIZ / "backend/app/routes/panel.py"

fallos: list[str] = []


def check(cond, msg):
    print(("  ok   " if cond else "  FALLA ") + msg)
    if not cond:
        fallos.append(msg)


# ---------------------------------------------------------------- dobles
def instalar_dobles():
    """Sustituye lo que panel.py toca del mundo exterior, y nada mas."""
    sa = types.ModuleType("sqlalchemy")
    sa.text = lambda s: s
    sys.modules["sqlalchemy"] = sa

    db = types.ModuleType("app.database")
    class _Engine:
        def connect(self):
            raise AssertionError("ninguna prueba de aca deberia tocar la base")
    db.engine = _Engine()
    sys.modules["app.database"] = db

    app_pkg = types.ModuleType("app"); app_pkg.__path__ = []
    sys.modules.setdefault("app", app_pkg)
    routes_pkg = types.ModuleType("app.routes"); routes_pkg.__path__ = []
    sys.modules.setdefault("app.routes", routes_pkg)

    fa = types.ModuleType("fastapi")
    class _Router:
        def __init__(self, *a, **k): pass
        def get(self, *a, **k): return lambda f: f
        def post(self, *a, **k): return lambda f: f
    fa.APIRouter = _Router
    class HTTPException(Exception):
        def __init__(self, *a, **k): pass
    fa.HTTPException = HTTPException
    sys.modules["fastapi"] = fa


def cargar_panel():
    instalar_dobles()
    sys.path.insert(0, str(RAIZ / "backend"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("app.routes.panel", PANEL_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["app.routes.panel"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- codigo muerto
def codigo_muerto(ruta: Path) -> list[str]:
    """Sentencias que siguen a un return/raise/continue/break en el mismo bloque."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    encontrados = []
    corta = (ast.Return, ast.Raise, ast.Continue, ast.Break)
    for nodo in ast.walk(arbol):
        for campo in ("body", "orelse", "finalbody"):
            cuerpo = getattr(nodo, campo, None)
            if not isinstance(cuerpo, list):
                continue
            for i, st in enumerate(cuerpo[:-1]):
                if isinstance(st, corta):
                    encontrados.append(
                        f"{ruta.name}:{cuerpo[i+1].lineno} despues de "
                        f"{type(st).__name__.lower()} en linea {st.lineno}")
    return encontrados


# ---------------------------------------------------------------- pruebas
def main():
    print("\n== codigo muerto ==")
    muerto = codigo_muerto(PANEL_PY)
    check(not muerto, f"panel.py sin sentencias inalcanzables ({muerto or 'ninguna'})")

    panel = cargar_panel()
    print("\n== la escala carga y declara sus formatos ==")
    formatos = panel.formatos_de_la_escala()
    check(set(formatos) == {"informativo", "practico_personal",
                            "entretenimiento", "deporte_gaming"},
          f"formatos leidos de la escala: {formatos}")
    check("_todos" not in formatos, "_todos no se ofrece como formato elegible")

    escala = panel.cargar_escala()
    descs = escala["descriptores"]
    estratificados = [k for k, c in descs.items() if c.get("ambito") == "por_formato"]
    check(len(estratificados) == 5,
          f"5 descriptores estratificados: {estratificados}")

    print("\n== leer_contra() no cambio el comportamiento de ubicar() ==")
    # Valores reales del video a62HpQpVBh8 (Veritasium en espanol, informativo).
    v = {"ritmo_ppm": 162.0, "cifras_100w": 2.35, "atribucion_1000w": 2.52,
         "mattr_200": 0.63, "conectores_1000w": 8.15, "enlaces_externos": 1.0,
         "promocional_1000w": 0.24, "cobertura_titulo": 1.0}
    filas = panel.ubicar(v, "informativo")
    por_clave = {f["clave"]: f for f in filas}
    esperado = {"ritmo_ppm": 65, "cifras_100w": 60, "atribucion_1000w": 88,
                "mattr_200": 94, "conectores_1000w": 42, "enlaces_externos": 55,
                "promocional_1000w": 12, "cobertura_titulo": 100}
    for k, p in esperado.items():
        got = por_clave[k].get("percentil")
        check(got == p, f"{k}: percentil {got} (esperado {p})")

    print("\n== alternativas por formato ==")
    con_alt = panel.con_alternativas(filas)
    alt = {f["clave"]: f.get("alternativas") for f in con_alt}
    check(alt["ritmo_ppm"] is None,
          "un descriptor de escala global NO recibe alternativas")
    check(alt["cifras_100w"] is not None,
          "un descriptor estratificado SI recibe alternativas")
    check(set(alt["cifras_100w"]) == set(formatos),
          "hay una lectura por cada formato de la escala")

    print("\n== la alternativa del formato propio coincide con la lectura oficial ==")
    for k in estratificados:
        oficial = {x: y for x, y in por_clave[k].items()
                   if x in ("estado", "percentil", "p_ausencia", "n_presentes")}
        propia = {x: y for x, y in alt[k]["informativo"].items()
                  if x in ("estado", "percentil", "p_ausencia", "n_presentes")}
        check(oficial == propia, f"{k}: {propia}")

    print("\n== el margen que introduce la etiqueta de formato ==")
    for k in estratificados:
        ps = [a.get("percentil") for a in alt[k].values() if a.get("percentil") is not None]
        if not ps:
            continue
        print(f"     {k:<20} {min(ps):>5.0f} - {max(ps):<5.0f}  (ancho {max(ps)-min(ps):.0f})")
    ps_cifras = [a["percentil"] for a in alt["cifras_100w"].values()]
    check(max(ps_cifras) - min(ps_cifras) >= 20,
          "densidad de cifras se mueve >= 20 puntos segun el formato")
    ps_cob = [a["percentil"] for a in alt["cobertura_titulo"].values()]
    check(max(ps_cob) - min(ps_cob) == 0,
          "correspondencia con el titulo no se mueve: el margen no es un artefacto uniforme")

    print("\n== casos borde ==")
    filas_sin = panel.ubicar({k: None for k in descs}, "informativo")
    alt_sin = panel.con_alternativas(filas_sin)
    check(all(f["estado"] == "sin_dato" for f in alt_sin),
          "sin valores, todo queda en sin_dato y nada revienta")
    check(all(a["estado"] == "ausente"
              for a in panel.con_alternativas(
                  panel.ubicar({**v, "enlaces_externos": 0.0}, "informativo")
              )[5]["alternativas"].values()),
          "un rasgo ausente sigue ausente en los cuatro formatos")
    desconocido = panel.ubicar(v, "formato_que_no_existe")
    check({f["clave"]: f.get("percentil") for f in desconocido}["cifras_100w"] is not None,
          "un formato desconocido cae a _todos en vez de romper")

    print("\n== procedencia de la transcripcion ==")
    casos = [
        ({"transcript_source": "youtube_manual", "transcript_is_generated": None},
         "subtítulos publicados por el autor", False),
        ({"transcript_source": "youtube_auto", "transcript_is_generated": None},
         "subtítulos automáticos de YouTube", True),
        ({"transcript_source": "supadata", "transcript_is_generated": True},
         "transcripción automática (Supadata)", True),
        ({"transcript_source": None, "transcript_is_generated": None},
         "origen no registrado", None),
    ]
    for fila, texto, automatica in casos:
        p = panel.procedencia(fila)
        check(p["texto"] == texto and p["automatica"] is automatica,
              f"{fila.get('transcript_source')} -> {p['texto']} / automatica={p['automatica']}")

    print("\n== la respuesta completa, por los dos caminos ==")
    fila = {"transcript_lang": "es", "transcript_source": "youtube_auto",
            "transcript_is_generated": None, "transcript_word_count": 8342}
    for desde_guardado in (True, False):
        r = panel.armar_respuesta("a62HpQpVBh8", fila, filas, {}, "informativo",
                                  escala["frame_version"], desde_guardado)
        check(r["transcripcion"]["texto"] == "subtítulos automáticos de YouTube",
              f"desde_guardado={desde_guardado}: procedencia en la respuesta")
        check(len(r["descriptores"]) == 8 and
              sum(1 for d in r["descriptores"] if d.get("alternativas")) == 5,
              f"desde_guardado={desde_guardado}: 8 descriptores, 5 con alternativas")
        check(r["formatos_posibles"] == formatos,
              f"desde_guardado={desde_guardado}: la extension recibe los formatos elegibles")
        json.dumps(r)   # revienta si algo no es serializable
    check(True, "la respuesta es serializable a JSON")

    print("\n== la forma guardada no cambio ==")
    check(all("alternativas" not in f for f in filas),
          "ubicar() sigue devolviendo filas sin alternativas: content_features no cambia")

    print()
    if fallos:
        print(f"FALLARON {len(fallos)} comprobaciones:")
        for f in fallos:
            print("  -", f)
        return 1
    print("todo en verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())

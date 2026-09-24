"""La linea de procedencia del dashboard, sin base de datos y sin backend.

CORRE DESDE LA RAIZ DEL REPOSITORIO:

    python backend/tests/test_dashboard_procedencia.py

METODO
Arma el HTML con la MISMA plantilla que usa build_dashboard.py y lo abre en
Chromium. No reimplementa textos() aca: lee lo que la pagina dibuja en #proc,
que es lo que ve el usuario. (jsdom no sirve: la plantilla usa matchMedia para
el modo oscuro y el script muere antes de dibujar.)

QUE VERIFICA
Los tres escenarios que van a existir de verdad —datos nuevos con
transcript_source, la foto vieja sin el campo, y la mezcla de las dos— mas que
la linea se recalcula al filtrar. El caso de la foto vieja no es hipotetico:
`build_dashboard.py --fuente instantanea` arma el dashboard desde una foto que
puede ser anterior a este cambio.

Usa privado/dashboard_filas.json si esta a mano (esa carpeta esta fuera de git);
si no, se inventa un recorte del mismo tamano. Lo que se prueba es el dibujo, no
los datos.
"""
import asyncio
import json
import random
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]      # backend/tests/ -> raiz
PLANTILLA = RAIZ / "backend/scripts/plantilla_dashboard.html"
ESCALA = RAIZ / "docs/escala_referencia.json"
FOTO = RAIZ / "privado/dashboard_filas.json"

fallos: list[str] = []


def check(cond, msg):
    print(("  ok    " if cond else "  FALLA ") + msg)
    if not cond:
        fallos.append(msg)


def cargar_meta() -> str:
    """El mismo META que inyecta build_dashboard.py, calculado por el modulo real."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "bd", RAIZ / "backend/scripts/build_dashboard.py")
    bd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bd)
    return json.dumps(bd.cargar_meta(ESCALA), ensure_ascii=False)


def filas_base() -> list[list]:
    if FOTO.exists():
        print(f"  (usando {FOTO.relative_to(RAIZ)})")
        return json.loads(FOTO.read_text(encoding="utf-8"))
    print("  (sin la foto: se inventa un recorte equivalente)")
    rnd = random.Random(7)
    fmts = ["informativo", "entretenimiento", "practico_personal", "deporte_gaming"]
    return [[f"Video {i}", f"Canal {i % 12}", fmts[i % 4],
             f"2026-0{5 + i % 4}-{1 + i % 28:02d}", round(5 + rnd.random() * 60, 1),
             1000 + i * 7] + [rnd.randint(0, 100) for _ in range(8)]
            for i in range(79)]


FUENTES = ["youtube_auto", "youtube_manual", "supadata"]


async def main() -> int:
    from playwright.async_api import async_playwright

    meta = cargar_meta()
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    base = filas_base()
    n = len(base)
    con_origen = [f + [FUENTES[i % 3]] for i, f in enumerate(base)]
    mezcla = [f + (["youtube_manual"] if i < 5 else []) for i, f in enumerate(base)]
    tmp = Path(__file__).resolve().parent / "_tmp_dashboard.html"

    async def abrir(pg, filas):
        tmp.write_text(
            plantilla.replace("__DATOS__", json.dumps(filas, ensure_ascii=False))
                     .replace("__META__", meta), encoding="utf-8")
        errores: list[str] = []
        pg.on("pageerror", lambda e: errores.append(str(e)))
        await pg.goto(tmp.as_uri())
        await pg.wait_for_selector("#tiles .tile", timeout=10000)
        texto = re.sub(r"\s+", " ", await pg.inner_text("#proc")).strip()
        return texto, await pg.locator("#tiles .tile").count(), \
            await pg.locator("svg").count(), errores

    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1280, "height": 900})

        print("\n== 1. datos nuevos, con origen de la transcripcion ==")
        t, fichas, svgs, errs = await abrir(pg, con_origen)
        print("     →", t)
        check(not errs, f"la pagina no tira errores de JavaScript ({errs[:1]})")
        check(fichas == 4, f"las 4 fichas de arriba siguen dibujandose (hay {fichas})")
        check(svgs > 0, f"los graficos se dibujan ({svgs} svg)")
        check("Medido sobre" in t, "la linea de procedencia aparece")
        for esperado in ("subtítulos automáticos de YouTube", "subtítulos del autor", "Supadata"):
            check(esperado in t, f"nombra «{esperado}»")
        suma = sum(int(x) for x in re.findall(r"(\d+) con ", t))
        check(suma == n, f"los recuentos suman los {n} videos del recorte (suman {suma})")
        check("la puntuación la insertó el transcriptor" in t,
              "avisa que en las automaticas la puntuacion no es del hablante")

        print("\n== 2. una foto anterior al cambio, sin el campo ==")
        t2, _, _, errs2 = await abrir(pg, base)
        print("     →", t2)
        check(not errs2, "la pagina no tira errores de JavaScript")
        check("no registrado" in t2,
              "dice que el origen no esta registrado en vez de inventar uno")
        check("subtítulos" not in t2, "y no nombra ninguna fuente")

        print("\n== 3. mezcla: 5 con origen, el resto sin ==")
        t3, _, _, _ = await abrir(pg, mezcla)
        print("     →", t3)
        check("5 con subtítulos del autor" in t3, "cuenta las 5 que tienen origen")
        check(f"{n - 5} sin origen registrado" in t3, f"declara las {n - 5} sin origen")
        check("la puntuación la insertó" not in t3,
              "sin automaticas no aparece la advertencia de puntuacion")

        print("\n== 4. al filtrar, la linea se recalcula sobre el recorte ==")
        antes, _, _, _ = await abrir(pg, con_origen)
        await pg.select_option("#fFormato", "informativo")
        await pg.wait_for_timeout(400)
        despues = re.sub(r"\s+", " ", await pg.inner_text("#proc")).strip()
        print("     →", despues)
        check(despues != antes, "la procedencia cambia al cambiar el filtro")
        suma3 = sum(int(x) for x in re.findall(r"(\d+) con ", despues))
        visible = int(re.search(r"(\d+)", await pg.inner_text("#estado")).group(1))
        check(suma3 == visible,
              f"y suma los {visible} videos del recorte filtrado (suma {suma3})")

        await b.close()

    tmp.unlink(missing_ok=True)
    print()
    if fallos:
        print(f"FALLARON {len(fallos)} comprobaciones:")
        for f in fallos:
            print("  -", f)
        return 1
    print("todo en verde")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

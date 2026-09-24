"""comparar.html en Chromium, sin base y sin backend.

METODO
Sirve docs/ con un servidor estatico y CORTA la llamada a /admin/dieta con una
respuesta falsa, generada con la estructura real de fila_compacta(). Asi se
ejercita la pagina entera: Sitio.api, la clave, el catalogo, los dos modos y los
avisos. Lo unico simulado es la red.

QUE VERIFICA
  1. con ?a= sola: el panel de ese video
  2. con ?a=&b=: la comparacion, las diferencias y que no haya veredicto
  3. formatos distintos: el aviso de que los percentiles no son comparables
  4. transcripciones de distinto origen: el aviso lexico
  5. un id que no esta en el historial: lo dice y no rompe
  6. elegir por el buscador cambia la URL
"""
import asyncio
import json
import random
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]                 # backend/tests/ -> raiz del repositorio
DOCS = RAIZ / "docs"
FOTO = RAIZ / "privado" / "dashboard_filas.json"


def armar_fixture() -> dict:
    """La respuesta de /admin/dieta, con la estructura real de fila_compacta().

    NO se guarda un fixture en el repositorio: seria publicar el historial de
    visionado —titulos, canales y fechas— en un repo que es publico porque
    Pages lo exige. Se arma al vuelo desde privado/ si esta a mano, y si no con
    videos inventados. Lo que se prueba es el dibujo, no los datos.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "bd", RAIZ / "backend/scripts/build_dashboard.py")
    bd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bd)
    meta = bd.cargar_meta(RAIZ / "docs/escala_referencia.json")

    rnd = random.Random(11)
    fmts = ["informativo", "entretenimiento", "practico_personal", "deporte_gaming"]
    fuentes = ["youtube_auto", "youtube_manual", "supadata", None]
    base = (json.loads(FOTO.read_text(encoding="utf-8")) if FOTO.exists() else None)
    filas = []
    for i in range(len(base) if base else 40):
        if base:
            f = list(base[i])
        else:
            f = [f"Video de prueba {i}", f"Canal {i % 9}", fmts[i % 4],
                 f"2026-0{5 + i % 4}-{1 + i % 28:02d}", round(6 + rnd.random() * 70, 1),
                 900 + i * 11] + [rnd.choice([rnd.randint(0, 100), None]) for _ in range(8)]
        # Se fuerza variedad: hacen falta pares con formato distinto, con origen
        # distinto, y descriptores ausentes, que es donde la pagina decide.
        f[2] = fmts[i % 4]
        fuente = fuentes[i % 4]
        vals = [None if p is None else round(p / 10 + (i % 5) * 0.37, 3) for p in f[6:14]]
        if i % 7 == 0:           # algun rasgo ausente de verdad
            f[8] = None
            vals[2] = 0.0
        filas.append(f[:14] + [fuente, f"vid{i:04d}"] + vals)
    return {"filas": filas, "meta": meta,
            "afuera": {"sin_panel": 2, "sin_transcripcion": 17},
            "leido_at": "2026-09-24T12:00:00+00:00"}


FIXTURE = armar_fixture()

fallos: list[str] = []


def check(cond, msg):
    print(("  ok    " if cond else "  FALLA ") + msg)
    if not cond:
        fallos.append(msg)


def video(i):
    f = FIXTURE["filas"][i]
    return {"id": f[15], "titulo": f[0], "formato": f[2], "fuente": f[14],
            "vals": f[16:24], "p": f[6:14],
            # Un rasgo ausente no tiene percentil, asi que no lleva marcador.
            # Esperar siempre ocho seria esperar que la pagina dibuje una
            # posicion que no existe.
            "n_marcas": sum(1 for x in f[6:14] if x is not None)}


def buscar(**kw):
    """Primer video del fixture que cumple todo lo pedido."""
    for i in range(len(FIXTURE["filas"])):
        v = video(i)
        if all(v.get(k) == x for k, x in kw.items()):
            return v
    return None


async def main() -> int:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1180, "height": 1000})

        # La clave ya guardada: lo que se prueba aca no es el modal.
        await ctx.add_init_script(
            "try{localStorage.setItem('ca.claveAdmin','clave-de-prueba')}catch(e){}")
        # La red, cortada.
        await ctx.route("**/admin/dieta", lambda r: asyncio.ensure_future(
            r.fulfill(status=200, content_type="application/json",
                      body=json.dumps(FIXTURE))))

        pg = await ctx.new_page()
        errores: list[str] = []
        pg.on("pageerror", lambda e: errores.append(str(e)))

        base = (DOCS / "comparar.html").resolve().as_uri()

        async def abrir(q=""):
            await pg.goto(base + q)
            await pg.wait_for_selector("#selector:not([hidden])", timeout=10000)
            await pg.wait_for_timeout(250)

        a = buscar(formato="informativo", fuente="youtube_auto")
        otro_fmt = buscar(formato="entretenimiento")
        manual = buscar(fuente="youtube_manual")

        print("\n== 1. un solo video: su panel ==")
        await abrir(f"?a={a['id']}")
        check(not errores, f"sin errores de JavaScript ({errores[:1]})")
        filas = await pg.locator("#filas .d").count()
        check(filas == 8, f"ocho descriptores (hay {filas})")
        sub = await pg.inner_text("#subPanel")
        check("Elegí un segundo video" in sub, "invita a elegir el segundo")
        check("medido sobre" in sub, "declara la procedencia de la transcripcion")
        check(await pg.locator("#panel .eje .mk.a").count() == a["n_marcas"],
              f"un marcador A por descriptor con percentil ({a['n_marcas']} de 8; "
              "los ausentes no llevan)")
        check(await pg.locator("#panel .eje .mk.b").count() == 0,
              "y ningun marcador B todavia")

        print("\n== 2. los dos: la comparacion ==")
        await abrir(f"?a={a['id']}&b={otro_fmt['id']}")
        check(not errores, "sin errores de JavaScript")
        check(await pg.locator("#filas .d").count() == 8, "ocho filas")
        check(await pg.locator("#panel .eje .mk.b").count() == otro_fmt["n_marcas"],
              f"un marcador B por descriptor con percentil ({otro_fmt['n_marcas']} de 8)")
        txt = re.sub(r"\s+", " ", await pg.inner_text("#filas"))
        check("más en A" in txt or "más en B" in txt or "Iguales" in txt,
              "cada fila dice cuanto y de quien")
        sin_p = 8 - a["n_marcas"]
        if sin_p:
            check("no tiene" in txt or "sin dato" in txt,
                  f"los {sin_p} rasgos sin percentil de A se dicen con palabras")
        for palabra in ("mejor", "peor", "gana", "recomend", "deberías"):
            check(palabra not in txt.lower(), f"no aparece «{palabra}»: no hay veredicto")

        print("\n== 3. avisos ==")
        check(not await pg.locator("#avisoFmt").is_hidden(),
              "con formatos distintos, avisa que los percentiles no son comparables")
        aviso = await pg.inner_text("#avisoFmt")
        check("valores crudos se comparan igual" in re.sub(r"\s+", " ", aviso),
              "y aclara que los valores crudos si")
        if manual and manual["id"] != a["id"]:
            await abrir(f"?a={a['id']}&b={manual['id']}")
            check(not await pg.locator("#avisoFuente").is_hidden(),
                  "con transcripciones de distinto origen, avisa")
        else:
            print("  (sin un par manual/automatico en el fixture: no se prueba)")

        print("\n== 4. mismo formato y mismo origen: sin avisos ==")
        pares = [video(i) for i in range(len(FIXTURE["filas"]))]
        igual = [v for v in pares
                 if v["formato"] == a["formato"] and v["fuente"] == a["fuente"]
                 and v["id"] != a["id"]]
        if igual:
            await abrir(f"?a={a['id']}&b={igual[0]['id']}")
            check(await pg.locator("#avisoFmt").is_hidden(), "no avisa de formato")
            check(await pg.locator("#avisoFuente").is_hidden(), "no avisa de origen")
        else:
            print("  (no hay par comparable en el fixture)")

        print("\n== 5. un id que no esta en el historial ==")
        await abrir("?a=noexiste123")
        estado = await pg.inner_text("#carga")
        check("todavía no está en" in estado, "lo dice con todas las letras")
        check(await pg.locator("#selector").is_visible(),
              "y deja el selector usable en vez de morir")
        check("noexiste123" not in (await pg.evaluate("location.search")),
              "y saca el id invalido de la URL")

        print("\n== 6. elegir con el buscador ==")
        await abrir("")
        etiqueta = await pg.evaluate(
            "() => document.querySelectorAll('#catalogo option').length")
        check(etiqueta == len([f for f in FIXTURE["filas"] if f[15]]),
              f"el catalogo trae los videos del historial ({etiqueta})")
        await pg.fill("#inA", a["titulo"][:25])
        await pg.dispatch_event("#inA", "change")
        await pg.wait_for_timeout(200)
        check(a["id"] in await pg.evaluate("location.search"),
              "escribir parte del titulo fija el video en la URL")
        check(await pg.locator("#filas .d").count() == 8, "y dibuja su panel")

        print("\n== 7. captura ==")
        await abrir(f"?a={a['id']}&b={otro_fmt['id']}")
        await pg.screenshot(path=str(AQUI / "_comparar.png"), full_page=True)
        print("     _comparar.png")

        await b.close()

    print()
    if fallos:
        print(f"FALLARON {len(fallos)}:")
        for f in fallos:
            print("  -", f)
        return 1
    print("todo en verde")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

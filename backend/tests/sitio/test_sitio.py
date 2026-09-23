"""El sitio en Chromium de verdad, contra la app real (uvicorn, base local) y
las RPC reales de la base local (las mismas funciones SQL que Supabase)."""
import json
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sembrar  # noqa: E402

BASE = "http://127.0.0.1:8766"
CLAVE = "clave-de-prueba-larga-123"
FOTOS = Path(os.getenv("FOTOS_PRUEBA", Path(__file__).resolve().parent / "fotos"))
FOTOS.mkdir(exist_ok=True)
FALLOS, ERRORES_JS = [], []

YT_FALSO = """
window.YT = { PlayerState: { ENDED: 0, PLAYING: 1 },
  Player: function (id, o) {
    var el = document.getElementById(id);
    el.style.cssText = 'display:flex;align-items:center;justify-content:center;color:#888;font:14px sans-serif';
    el.textContent = 'reproductor de YouTube (simulado en la prueba)';
    this.getDuration = function () { return 100; };
    this.getCurrentTime = function () { return 100; };
    setTimeout(function () { o.events.onStateChange({ data: 1 }); }, 50);
  } };
setTimeout(function () { window.onYouTubeIframeAPIReady && window.onYouTubeIframeAPIReady(); }, 10);
"""


def check(nombre, cond, detalle=""):
    print(("ok   " if cond else "FALLO") + f" {nombre}" + (f"  -> {detalle}" if not cond and detalle else ""))
    if not cond:
        FALLOS.append(nombre)


def rpc(route):
    fn = route.request.url.rsplit("/", 1)[1]
    a = json.loads(route.request.post_data or "{}")
    sql = {"obtener_quiz": ("select obtener_quiz(%s) as r", [a.get("p_token")]),
           "registrar_visionado": ("select registrar_visionado(%s,%s,%s,%s) as r",
                                   [a.get("p_token"), a.get("p_content_item_id"),
                                    a.get("p_reproduccion_pct"), a.get("p_completo")]),
           "registrar_respuestas": ("select registrar_respuestas(%s,%s::jsonb) as r",
                                    [a.get("p_token"), json.dumps(a.get("p_respuestas"))])}[fn]
    try:
        with psycopg2.connect(sembrar.DSN) as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(*sql)
            r = cur.fetchone()["r"]
        cuerpo = json.dumps(r, default=str)
        route.fulfill(status=200, body=cuerpo, headers={"content-type": "application/json",
                                                         "access-control-allow-origin": "*"})
    except psycopg2.Error as e:
        route.fulfill(status=400, body=json.dumps({"message": str(e)}),
                      headers={"content-type": "application/json", "access-control-allow-origin": "*"})


def render(route):
    url = route.request.url.replace("https://cognitive-analysis-gfpg.onrender.com", "http://127.0.0.1:8765")
    r = route.fetch(url=url)
    route.fulfill(response=r)


def preparar(ctx):
    ctx.route("https://cognitive-analysis-gfpg.onrender.com/**", render)
    ctx.route("https://hprttdautrltgueryysz.supabase.co/rest/v1/rpc/*", rpc)
    ctx.route("https://www.youtube.com/iframe_api",
              lambda r: r.fulfill(status=200, body=YT_FALSO, headers={"content-type": "text/javascript"}))


def pagina(ctx):
    p = ctx.new_page()
    p.on("pageerror", lambda e: ERRORES_JS.append(f"{p.url}: {e}"))
    p.on("console", lambda m: m.type == "error" and ERRORES_JS.append(f"{p.url}: {m.text}"))
    return p


sembrar.sembrar()
with sync_playwright() as pw:
    nav = pw.chromium.launch()

    # ── 1. Portada ────────────────────────────────────────────────────────
    ctx = nav.new_context(viewport={"width": 1280, "height": 900}, color_scheme="light")
    preparar(ctx)
    p = pagina(ctx)
    p.goto(BASE + "/index.html")
    check("portada: carga y muestra la barra", p.locator(".sitio-nav").count() == 1)
    check("portada: 4 secciones", p.locator("a.seccion").count() == 4)
    check("portada: sin clave, candado en Dieta y Generar", p.locator(".sitio-candado").count() == 2)
    p.screenshot(path=str(FOTOS / "01_portada.png"), full_page=True)

    # ── 2. Dieta: clave mala, clave buena, dibujo ─────────────────────────
    p.goto(BASE + "/dieta.html")
    p.wait_for_selector(".sitio-modal input")
    p.screenshot(path=str(FOTOS / "02_dieta_clave.png"))
    p.fill(".sitio-modal input", "una-clave-equivocada-xx")
    p.click(".sitio-modal button[type=submit]")
    p.wait_for_selector(".sitio-modal .sitio-error:has-text('incorrecta')")
    check("dieta: clave mala -> vuelve a pedirla con el motivo", True)
    p.fill(".sitio-modal input", CLAVE)
    p.click(".sitio-modal button[type=submit]")
    p.wait_for_selector(".viz-root:not([hidden]) #c1 rect, .viz-root:not([hidden]) #c1 circle", timeout=15000)
    check("dieta: el dashboard dibuja con datos en vivo", p.locator("#c1 *").count() > 20)
    check("dieta: aviso de lo que queda afuera",
          "Quedan afuera 3 videos" in p.inner_text("#dieta-afuera"), p.inner_text("#dieta-afuera"))
    check("dieta: pie con 79 videos del historial", "79 videos" in p.inner_text("#pie"))
    check("dieta: la barra ya no muestra candados", p.locator(".sitio-candado").count() == 0)
    p.select_option("#fFormato", "informativo")
    p.wait_for_timeout(300)
    check("dieta: los filtros del dashboard siguen andando", "informativo" in p.inner_text("#estado").lower(),
          p.inner_text("#estado"))
    p.screenshot(path=str(FOTOS / "03_dieta.png"), full_page=True)

    # ── 3. Generar ────────────────────────────────────────────────────────
    p.goto(BASE + "/generar.html")
    p.wait_for_selector("#lista .fila")
    check("generar: lista los 2 candidatos", p.locator("#lista .fila").count() == 2)
    check("generar: avisa el excluido por formato", "1 video queda fuera" in p.inner_text("#excluidos"))
    check("generar: cola vacia al principio", p.inner_text("#cola-n").startswith("0"))
    p.locator("#lista .fila", has_text="Alejandria").locator("button").click()
    p.wait_for_selector("#trabajo h2:has-text('Generando'), #trabajo h2:has-text('Preparando')")
    check("generar: los botones se bloquean mientras corre",
          p.locator("#lista button[data-id]:not([disabled])").count() == 0)
    p.screenshot(path=str(FOTOS / "04_generar_corriendo.png"))
    p.wait_for_selector("#trabajo h2:has-text('Listo')", timeout=30000)
    txt = p.inner_text("#trabajo")
    check("generar: resumen 4 de 6 y linea de base 1 de 4", "4 de 6" in txt and "1 de 4" in txt, txt)
    check("generar: no muestra el texto de las preguntas", "rollos" not in p.content())
    p.wait_for_function("document.querySelectorAll('#lista .fila').length === 1")
    check("generar: el video generado sale de la lista", p.locator("#lista .fila").count() == 1)
    check("generar: cola = 1", p.inner_text("#cola-n").startswith("1"), p.inner_text("#cola-n"))
    check("generar: avisa el video con quiz fuera de la cola (3005)", not p.locator("#fuera").is_hidden())
    colores = p.evaluate("""() => [...document.querySelectorAll('.sitio-boton')]
        .map(e => { const s = getComputedStyle(e); return [e.textContent.trim(), s.color, s.backgroundColor]; })""")
    check("botones: el texto nunca es del color del fondo",
          all(c[1] != c[2] and c[0] for c in colores), colores)
    p.screenshot(path=str(FOTOS / "05_generar_listo.png"), full_page=True)
    p.click("#sumar-fuera")
    p.wait_for_function("document.getElementById('cola-n').textContent.startsWith('2')")
    check("generar: Sumarlos lleva la cola a 2", True)

    # ── 4. Responder la cola propia ───────────────────────────────────────
    p.click("#responder")
    p.wait_for_selector("#aceptar", state="visible")
    p.click("#aceptar")
    p.wait_for_selector(".video")
    check("quiz: 2 videos en la cola", p.locator("section.video").count() == 2)
    check("quiz: ya vistos -> sin reproductor y con la fecha",
          p.locator(".marco").count() == 0 and p.locator(".ya-visto").count() == 2)
    check("quiz: preguntas visibles sin volver a ver", p.locator(".preguntas.oculto").count() == 0)
    p.screenshot(path=str(FOTOS / "06_quiz_cola.png"), full_page=True)
    for nombre in set(p.eval_on_selector_all("input[type=radio]", "els => els.map(e => e.name)")):
        p.locator(f"input[name={nombre}]").first.check()
    check("quiz: enviar habilitado con todo contestado", p.is_enabled("#enviar"))
    p.click("#enviar")
    p.wait_for_selector("#resultado:not(.oculto)")
    check("quiz: soluciones con cita", p.locator("#revision .cita").count() == 5)
    p.screenshot(path=str(FOTOS / "07_quiz_soluciones.png"), full_page=True)
    p.reload()
    p.wait_for_selector("#fatal h1")
    check("quiz: al volver, nada pendiente", "No tenés preguntas pendientes" in p.inner_text("#fatal"))

    # quiz.html sin token pero con clave -> va a la cola propia
    p.goto(BASE + "/quiz.html")
    p.wait_for_url("**/quiz.html?t=*")
    check("quiz: sin token y con clave, redirige a la cola propia", "?t=" in p.url)
    ctx.close()

    # ── 5. Participante externo por el ENLACE VIEJO, sin clave, en celular ──
    ctx = nav.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark",
                          is_mobile=True, has_touch=True)
    preparar(ctx)
    p = pagina(ctx)
    p.goto(BASE + "/quiz_piloto/formularios_web/quiz_web.html?t=tok-luna")
    p.wait_for_url("**/quiz.html?t=tok-luna")
    check("enlace viejo: redirige conservando el token", p.url.endswith("/quiz.html?t=tok-luna"), p.url)
    p.wait_for_selector("#aceptar", state="visible")
    check("participante: la barra no le muestra secciones con clave",
          p.locator(".sitio-links a").all_inner_texts() == ["Inicio", "Responder"],
          p.locator(".sitio-links a").all_inner_texts())
    p.click("#aceptar")
    p.wait_for_selector("#vi-609:not([disabled])", timeout=10000)
    check("participante: nucleo sin el video sin preguntas (623)", p.locator("section.video").count() == 3)
    check("participante: preguntas bloqueadas hasta ver", p.locator(".preguntas.oculto").count() == 3)
    p.screenshot(path=str(FOTOS / "08_participante_movil.png"), full_page=True)
    p.click("#vi-609"); p.click("#vi-610")
    p.locator("#v94 .novi-chk").check()
    p.wait_for_selector("#preg-609:not(.oculto)")
    for vid in (609, 610):
        for nombre in set(p.eval_on_selector_all(f"#v{vid} input[type=radio]", "els => els.map(e => e.name)")):
            p.locator(f"input[name={nombre}]").nth(1).check()
    p.click("#enviar")
    p.wait_for_selector("#resultado:not(.oculto)")
    check("participante: envia 6 respuestas", "Preguntas contestadas" in p.inner_text("#resultado")
          and ">6<" in p.inner_html("#resultado"), p.inner_text("#resultado"))
    p.screenshot(path=str(FOTOS / "09_participante_resultado.png"), full_page=True)
    p.reload()
    p.wait_for_selector("section.video")
    check("participante: al volver queda solo el que dejo para despues (94)",
          p.locator("section.video").count() == 1 and p.locator("#v94").count() == 1)

    # quiz.html sin token y sin clave -> pide el enlace
    p.goto(BASE + "/quiz.html")
    p.wait_for_selector("#form-enlace")
    p.fill("#enlace", BASE + "/quiz.html?t=tok-luna")
    p.click("#form-enlace button")
    p.wait_for_url("**/quiz.html?t=tok-luna")
    check("sin token: pegar el enlace entra", True)
    p.goto(BASE + "/index.html")
    p.screenshot(path=str(FOTOS / "10_portada_movil_oscuro.png"), full_page=True)
    ancho = p.evaluate("document.documentElement.scrollWidth")
    check("movil: sin scroll horizontal en la portada", ancho <= 390, ancho)
    p.goto(BASE + "/generar.html")
    p.wait_for_selector(".sitio-modal")
    p.click("[data-cancelar]")
    p.wait_for_selector("#carga button")
    check("sin clave: cancelar deja una salida clara", "necesita la clave" in p.inner_text("#carga"))
    ctx.close()
    nav.close()

# el 401 de la prueba de clave equivocada lo registra el navegador como error de consola
inesperados = [e for e in ERRORES_JS if "401 (Unauthorized)" not in e]
check("sin errores de JavaScript en ninguna pagina", not inesperados, inesperados[:5])
print()
print("TODO OK" if not FALLOS else f"{len(FALLOS)} FALLOS: {FALLOS}")
sys.exit(1 if FALLOS else 0)

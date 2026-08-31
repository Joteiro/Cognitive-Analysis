"""Captura el panel REAL, ejecutando content.js en Chromium.

No es un mockup: levanta un servidor minimo que responde en /watch, inyecta el
content.js que se instala en el navegador y una respuesta de /panel generada por
panel.py, y fotografia lo que el codigo dibuja.

    python captura_panel.py <content.js> <fixture.json> <salida.png>
"""
import asyncio
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

from playwright.async_api import async_playwright

CONTENT, FIXTURE, SALIDA = (Path(a) for a in sys.argv[1:4])

PAGINA = """<!doctype html><html lang="es"><meta charset="utf-8">
<style>
  html,body{margin:0;background:#0f0f0f;height:1150px}
  /* El panel es position:fixed abajo a la derecha; se lo trae al origen para
     poder recortarlo sin margenes muertos. */
  #cogana-panel{top:12px!important;left:12px!important;bottom:auto!important;right:auto!important}
</style>
<body>
<script>
  // Dobles de lo unico que el content.js necesita del navegador de verdad.
  const RESPUESTA = %(fixture)s;
  window.chrome = { runtime: { id: 'captura' },
                    storage: { local: { get: (k, cb) => cb({}), set: () => {} } } };
  const _fetch = window.fetch;
  window.fetch = (url, opts) => {
    if (String(url).includes('/panel/')) {
      return Promise.resolve({ ok: true, status: 200, json: async () => RESPUESTA });
    }
    return Promise.resolve({ ok: true, status: 200, text: async () => 'ok' });
  };
  // Titulo y canal, para que extractVideoData() no se quede sin nada.
  document.write('<h1 class="ytd-watch-metadata"><yt-formatted-string>'
    + 'Internet Estaba A Semanas Del Desastre y Nadie Lo Sabia</yt-formatted-string></h1>'
    + '<div id="channel-name"><a>Veritasium en espanol</a></div>');
</script>
<script src="/content.js"></script>
</body></html>"""


def servidor(puerto: int):
    pagina = PAGINA % {"fixture": FIXTURE.read_text(encoding="utf-8")}
    js = CONTENT.read_text(encoding="utf-8")

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            cuerpo, tipo = ((js, "application/javascript")
                            if self.path.startswith("/content.js")
                            else (pagina, "text/html"))
            datos = cuerpo.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", f"{tipo}; charset=utf-8")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        def log_message(self, *a):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", puerto), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


async def main():
    puerto = 8732
    srv = servidor(puerto)
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--font-render-hinting=none"])
        pg = await b.new_page(viewport={"width": 460, "height": 1150},
                              device_scale_factor=2)
        await pg.goto(f"http://127.0.0.1:{puerto}/watch?v=a62HpQpVBh8")
        # DELAY_MS del content.js son 2500 ms antes de pedir el panel.
        await pg.wait_for_selector("#cogana-panel .fila", timeout=15000)
        await pg.wait_for_timeout(400)
        await pg.locator("#cogana-panel").screenshot(path=str(SALIDA))
        alto = await pg.evaluate(
            "document.getElementById('cogana-panel').getBoundingClientRect().height")
        print(f"{SALIDA.name}: panel de {round(alto)} px de alto")
        await b.close()
    srv.shutdown()


asyncio.run(main())

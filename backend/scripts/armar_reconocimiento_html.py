#!/usr/bin/env python3
"""Arma el formulario HTML de la prueba de reconocimiento.

El HTML que sale NO contiene la clave: se le quita a cada afirmacion el campo
`clase` y el video de origen antes de incrustarla. Podes abrir el codigo
fuente sin quemarte la prueba. La clave vive solo en
docs/reconocimiento/clave_no_abrir/items_<etiqueta>.json, que no hay que abrir.

Tampoco pone el enlace al video, a proposito: la prueba mide lo que quedo en
la cabeza, y un clic de mas la invalida.

USO
    python armar_reconocimiento_html.py --etiqueta piloto --persona juan-01

SALIDA
    docs/reconocimiento/formularios/reconocimiento_<persona>_<etiqueta>.html
    Lo abris en el navegador, lo contestas, y al final baja un JSON a Descargas.
    Ese JSON va a docs/reconocimiento/respuestas/ y lo lee puntuar_reconocimiento.py
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generar_quiz import DOCS  # noqa: E402

BASE = DOCS / "reconocimiento"
CLAVE = BASE / "clave_no_abrir"
FORMULARIOS = BASE / "formularios"

PLANTILLA = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prueba de reconocimiento - Cognitive Analysis</title>
<style>
 :root{--tinta:#1b1b1f;--suave:#6b6b76;--linea:#e3e3e8;--fondo:#fbfbfd;--acento:#2f5eaa;--ok:#137a4b}
 *{box-sizing:border-box}
 body{margin:0;background:var(--fondo);color:var(--tinta);
      font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
 .env{max-width:760px;margin:0 auto;padding:24px 16px 120px}
 h1{font-size:22px;margin:0 0 4px} h2{font-size:17px;margin:0 0 2px}
 .sub{color:var(--suave);font-size:14px}
 .intro{background:#fff;border:1px solid var(--linea);border-radius:12px;padding:18px;margin-bottom:22px}
 .intro ul{margin:10px 0 0;padding-left:20px} .intro li{margin:4px 0}
 .video{background:#fff;border:1px solid var(--linea);border-radius:12px;padding:18px;margin-bottom:22px}
 .cab{border-bottom:1px solid var(--linea);padding-bottom:12px;margin-bottom:6px}
 .memoria{margin:12px 0 4px;font-size:14px}
 .memoria label{margin-right:14px;cursor:pointer}
 .item{padding:14px 0;border-bottom:1px solid var(--linea)}
 .item:last-child{border-bottom:none}
 .txt{margin-bottom:9px}
 .fila{display:flex;flex-wrap:wrap;gap:18px;align-items:center;font-size:14px}
 .sn label{margin-right:10px;cursor:pointer;padding:3px 10px;border:1px solid var(--linea);
           border-radius:999px;background:#fff}
 .sn input{margin-right:5px}
 .conf{color:var(--suave)} .conf label{margin-right:7px;cursor:pointer}
 .hecho{opacity:.55}
 .barra{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid var(--linea);
        padding:12px 16px;display:flex;gap:14px;align-items:center;justify-content:center}
 .prog{flex:1;max-width:380px;height:8px;background:var(--linea);border-radius:999px;overflow:hidden}
 .prog i{display:block;height:100%;width:0;background:var(--acento);transition:width .25s}
 button{background:var(--acento);color:#fff;border:0;border-radius:9px;padding:10px 18px;
        font-size:15px;cursor:pointer}
 button[disabled]{background:#b9bcc4;cursor:not-allowed}
 .aviso{font-size:14px;color:var(--suave)}
 @media (prefers-color-scheme:dark){
  :root{--tinta:#ececf1;--suave:#9a9aa6;--linea:#33333c;--fondo:#161619;--acento:#7aa2e3}
  .intro,.video,.barra,.sn label{background:#1e1e23}
 }
</style></head><body><div class="env">

<h1>Prueba de reconocimiento</h1>
<p class="sub">__PERSONA__ · __NVIDEOS__ videos · __NITEMS__ afirmaciones</p>

<div class="intro">
 <strong>Qué hay que hacer</strong>
 <ul>
  <li>Para cada afirmación, decidí si <strong>apareció en ese video</strong>: Sí o No.</li>
  <li>Después marcá qué tan seguro estás, de 1 (adivinando) a 5 (seguro).</li>
  <li>Muchas afirmaciones son ciertas en el mundo pero <strong>salen de otro video</strong>.
      Que algo sea verdad no significa que haya aparecido acá.</li>
  <li>No busques el video ni lo vuelvas a mirar. No pasa nada si no te acordás:
      esa también es una respuesta válida y es justamente lo que se está midiendo.</li>
  <li>Se guarda solo en este navegador a medida que avanzás. Podés cerrar y seguir después.</li>
 </ul>
</div>

<div id="quiz"></div>

<div class="barra">
 <span class="aviso" id="cuenta">0 / 0</span>
 <span class="prog"><i id="pi"></i></span>
 <button id="bajar" disabled>Descargar respuestas</button>
</div>
</div>
<script>
const DATOS = __DATOS__;
const PERSONA = "__PERSONA__";
const ETIQUETA = "__ETIQUETA__";
const LLAVE = "reconocimiento_" + PERSONA + "_" + ETIQUETA;
let estado = {};
try { estado = JSON.parse(localStorage.getItem(LLAVE) || "{}"); } catch (e) { estado = {}; }
let ultimo = Date.now();

const TOTAL = DATOS.videos.reduce((a, v) => a + v.items.length, 0);
const cont = document.getElementById("quiz");

DATOS.videos.forEach(v => {
  const d = document.createElement("div");
  d.className = "video";
  let h = '<div class="cab"><h2>' + esc(v.titulo) + '</h2>'
        + '<div class="sub">' + esc(v.canal || "") + '</div>'
        + '<div class="memoria">¿Te acordás de haber visto este video?'
        + ' <label><input type="radio" name="mem' + v.id + '" value="si"> Sí</label>'
        + ' <label><input type="radio" name="mem' + v.id + '" value="vago"> Vagamente</label>'
        + ' <label><input type="radio" name="mem' + v.id + '" value="no"> No me acuerdo</label>'
        + '</div></div>';
  v.items.forEach(it => {
    const k = v.id + "_" + it.n;
    h += '<div class="item" id="i' + k + '">'
       + '<div class="txt">' + esc(it.texto) + '</div>'
       + '<div class="fila"><span class="sn">'
       + '<label><input type="radio" name="r' + k + '" value="1"> Apareció</label>'
       + '<label><input type="radio" name="r' + k + '" value="0"> No apareció</label>'
       + '</span><span class="conf">seguridad: ';
    for (let c = 1; c <= 5; c++) {
      h += '<label><input type="radio" name="c' + k + '" value="' + c + '">' + c + '</label>';
    }
    h += '</span></div></div>';
  });
  d.innerHTML = h;
  cont.appendChild(d);
});

document.querySelectorAll('input[type=radio]').forEach(r => {
  r.addEventListener('change', () => {
    const n = r.name;
    if (n.startsWith('mem')) {
      estado['mem' + n.slice(3)] = r.value;
    } else {
      const k = n.slice(1);
      estado[k] = estado[k] || {};
      if (n[0] === 'r') { estado[k].si = r.value === '1'; }
      else { estado[k].conf = +r.value; }
      const ahora = Date.now();
      if (estado[k].seg === undefined) { estado[k].seg = Math.round((ahora - ultimo) / 100) / 10; }
      ultimo = ahora;
    }
    guardar();
    pintar();
  });
});

function guardar() {
  try { localStorage.setItem(LLAVE, JSON.stringify(estado)); } catch (e) {}
}

function completos() {
  let n = 0;
  DATOS.videos.forEach(v => v.items.forEach(it => {
    const e = estado[v.id + "_" + it.n];
    if (e && e.si !== undefined && e.conf) n++;
  }));
  return n;
}

// Un video cuenta solo si esta entero: todos sus items y la pregunta de si se
// acuerda de haberlo visto. Se exportan solo los enteros, asi podes cortar
// cuando quieras y puntuar lo hecho sin que un video a medias ensucie su d'.
function videosCompletos() {
  return DATOS.videos.filter(v =>
    estado['mem' + v.id] &&
    v.items.every(it => {
      const e = estado[v.id + "_" + it.n];
      return e && e.si !== undefined && e.conf;
    }));
}

function pintar() {
  const n = completos();
  const vc = videosCompletos().length;
  document.getElementById('cuenta').textContent =
    n + ' / ' + TOTAL + '  ·  ' + vc + ' de ' + DATOS.videos.length + ' videos enteros';
  document.getElementById('pi').style.width = (100 * n / TOTAL) + '%';
  const b = document.getElementById('bajar');
  b.disabled = vc === 0;
  b.textContent = vc ? 'Descargar ' + vc + (vc === 1 ? ' video' : ' videos') : 'Descargar respuestas';
  DATOS.videos.forEach(v => v.items.forEach(it => {
    const e = estado[v.id + "_" + it.n];
    const el = document.getElementById('i' + v.id + "_" + it.n);
    if (el) el.className = 'item' + (e && e.si !== undefined && e.conf ? ' hecho' : '');
  }));
}

function restaurar() {
  Object.keys(estado).forEach(k => {
    if (k.startsWith('mem')) {
      const r = document.querySelector('input[name=mem' + k.slice(3) + '][value="' + estado[k] + '"]');
      if (r) r.checked = true;
      return;
    }
    const e = estado[k];
    if (e && e.si !== undefined) {
      const r = document.querySelector('input[name=r' + k + '][value="' + (e.si ? 1 : 0) + '"]');
      if (r) r.checked = true;
    }
    if (e && e.conf) {
      const c = document.querySelector('input[name=c' + k + '][value="' + e.conf + '"]');
      if (c) c.checked = true;
    }
  });
}

document.getElementById('bajar').addEventListener('click', () => {
  const salida = {
    instrumento: DATOS.version, etiqueta: ETIQUETA, persona: PERSONA,
    respondido_at: new Date().toISOString(),
    videos: videosCompletos().map(v => ({
      content_item_id: v.id,
      recuerda_video: estado['mem' + v.id] || null,
      respuestas: v.items.map(it => {
        const e = estado[v.id + "_" + it.n] || {};
        return { n: it.n, si: !!e.si, confianza: e.conf || null, segundos: e.seg || null };
      })
    }))
  };
  const b = new Blob([JSON.stringify(salida, null, 1)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(b);
  a.download = 'reconocimiento_' + PERSONA + '_' + ETIQUETA + '.json';
  a.click();
});

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

restaurar();
pintar();
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--etiqueta", default="piloto")
    ap.add_argument("--persona", default="juan-01")
    ap.add_argument("--salida", default=None)
    args = ap.parse_args()

    ruta = CLAVE / f"items_{args.etiqueta}.json"
    if not ruta.exists():
        print(f"No existe {ruta}. Corre primero generar_reconocimiento.py --etiqueta {args.etiqueta}")
        return 1
    datos = json.loads(ruta.read_text(encoding="utf-8"))

    # Se incrusta el HTML SIN la clave: ni `clase` ni el video de origen.
    publico = {"version": datos["version"], "videos": []}
    total = 0
    for v in datos["videos"]:
        publico["videos"].append({
            "id": v["content_item_id"],
            "titulo": v["titulo"],
            "canal": v["canal"],
            "items": [{"n": i["n"], "texto": i["texto"]} for i in v["items"]],
        })
        total += len(v["items"])

    html = (PLANTILLA
            .replace("__DATOS__", json.dumps(publico, ensure_ascii=False))
            .replace("__PERSONA__", args.persona)
            .replace("__ETIQUETA__", args.etiqueta)
            .replace("__NVIDEOS__", str(len(publico["videos"])))
            .replace("__NITEMS__", str(total)))

    FORMULARIOS.mkdir(parents=True, exist_ok=True)
    destino = Path(args.salida) if args.salida else \
        FORMULARIOS / f"reconocimiento_{args.persona}_{args.etiqueta}.html"
    destino.write_text(html, encoding="utf-8")
    print(f"{destino}\n{len(publico['videos'])} videos · {total} afirmaciones "
          f"· ~{total * 5 // 60} min estimados")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
armar_quiz_html.py -- genera un quiz en un unico archivo HTML para recoger las
respuestas humanas, que es lo unico que hoy le falta a la variable objetivo.

POR QUE UN HTML SUELTO Y NO LA EXTENSION
    El flujo del producto --notificacion a los x dias, panel, guardado-- es
    semanas de trabajo. Un HTML autocontenido que se abre con doble clic
    consigue el MISMO dato en un dia, y ese dato es el que convierte el
    proyecto de "instrumento disenado" en "instrumento con datos". La
    extension puede venir despues; el trabajo de campo no espera.

DECISIONES DE MEDICION (importan mas que el codigo)
    - NO se puede dejar una pregunta sin contestar. La linea de base del
      modelo tampoco podia abstenerse, y si las personas pudieran, las dos
      tasas dejarian de ser comparables y la correccion por adivinacion no
      valdria.
    - Cada video tiene un "no vi este video". Alguien que contesta sobre un
      video que no vio no aporta ruido: aporta sesgo. Esas respuestas se
      marcan y se excluyen.
    - No se muestra si la respuesta fue correcta hasta el final. Saberlo a
      mitad de camino cambia como se contesta lo que queda.
    - No se muestran los dias transcurridos, para no dar una pista sobre
      cuanto deberia acordarse.
    - Se cronometra cada pregunta MIDIENDO DESDE LA ANTERIOR, no desde que se
      abrio la pagina: un tiempo altisimo suele delatar que la persona fue a
      buscar la respuesta. (En la primera version el cronometro arrancaba a la
      vez para todas y el numero era el tiempo acumulado: no medía nada.)
    - Se autoguarda en el navegador a cada respuesta. Un cuestionario de 128
      preguntas no se contesta de una sentada, y perder el avance al cerrar la
      pestana garantizaba que nadie lo terminara.

USO
    .venv\\Scripts\\python armar_quiz_html.py
    .venv\\Scripts\\python armar_quiz_html.py --max-videos 10 --salida tanda1.html

    Se abre el archivo, se contesta, se descarga el json y se carga con:
    .venv\\Scripts\\python cargar_quiz.py --respuestas <archivo descargado>
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
DOCS = RAIZ / "docs"
QUIZ = DOCS / "quiz_piloto"
SALIDA = QUIZ / "formularios"   # aqui van los .html que se contestan

# Se excluyen los videos que ESA persona ya contesto. Asi las tandas salen
# solas: cada vez que se genera el quiz con el mismo seudonimo aparecen los
# siguientes, sin llevar la cuenta a mano ni arriesgarse a contestar dos veces
# lo mismo. Sin esto, `--max-videos 10` devolvia siempre los MISMOS 10.
CONSULTA = """
select q.id, q.content_item_id, q.pregunta, q.opciones, q.correcta, q.tipo,
       q.dificil, q.cita,
       ci.title, ci.channel, ci.watched_at, ci.url
from quiz_preguntas q
join content_items ci on ci.id = q.content_item_id
where q.utilizable
  and (%(persona)s = '' or q.content_item_id not in (
        select q2.content_item_id
        from quiz_respuestas r2
        join quiz_preguntas q2 on q2.id = r2.pregunta_id
        where r2.persona_id = %(persona)s))
order by ci.watched_at desc nulls last, q.content_item_id, q.n_orden
"""


DIAGNOSTICO = """
select
  (select count(distinct content_item_id) from quiz_preguntas where utilizable)
    as total_utilizables,
  (select count(distinct q.content_item_id)
     from quiz_respuestas r join quiz_preguntas q on q.id = r.pregunta_id
     where r.persona_id = %(persona)s) as ya_contestados
"""


def traer(dsn: str, max_videos: int, persona: str = "") -> tuple:
    import psycopg2
    import psycopg2.extras
    with psycopg2.connect(dsn, connect_timeout=20) as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(DIAGNOSTICO, {"persona": persona})
            info = dict(cur.fetchone())
            cur.execute(CONSULTA, {"persona": persona})
            filas = [dict(r) for r in cur.fetchall()]

    videos, orden = {}, []
    for f in filas:
        vid = f["content_item_id"]
        if vid not in videos:
            if max_videos and len(orden) >= max_videos:
                continue
            videos[vid] = {
                "content_item_id": vid,
                "titulo": f["title"],
                "canal": f["channel"],
                "url": f["url"],
                "watched_at": f["watched_at"].isoformat() if f["watched_at"] else None,
                "preguntas": [],
            }
            orden.append(vid)
        videos[vid]["preguntas"].append({
            "id": f["id"],
            "pregunta": f["pregunta"],
            "opciones": f["opciones"] if isinstance(f["opciones"], list)
                        else json.loads(f["opciones"]),
            "correcta": f["correcta"],
            "tipo": f["tipo"],
            "dificil": f["dificil"],
        })
    return [videos[v] for v in orden], info


PLANTILLA = """<!doctype html>
<html lang="es">
<meta charset="utf-8">
<title>Quiz de retencion - Nutri-Score de Contenidos</title>
<style>
  :root { --tinta:#1a1a1a; --suave:#666; --linea:#e2e2e2; --fondo:#fbfbfa;
          --acento:#2f5d50; --acento-claro:#eaf1ee; }
  * { box-sizing:border-box; }
  body { margin:0; padding:0 1rem 6rem; background:var(--fondo); color:var(--tinta);
         font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  .env { max-width:44rem; margin:0 auto; }
  header { padding:2.5rem 0 1.5rem; border-bottom:1px solid var(--linea); margin-bottom:2rem; }
  h1 { font-size:1.5rem; margin:0 0 .5rem; letter-spacing:-.01em; }
  .sub { color:var(--suave); font-size:.95rem; margin:0; }
  .aviso { background:var(--acento-claro); border-left:3px solid var(--acento);
           padding:.9rem 1.1rem; margin:1.5rem 0; font-size:.92rem; border-radius:0 4px 4px 0; }
  .video { background:#fff; border:1px solid var(--linea); border-radius:8px;
           padding:1.5rem; margin-bottom:1.5rem; }
  .video h2 { font-size:1.05rem; margin:0 0 .2rem; line-height:1.4; }
  .canal { color:var(--suave); font-size:.85rem; margin:0 0 .5rem; }
  .novi { font-size:.88rem; color:var(--suave); display:flex; align-items:center;
          gap:.5rem; padding:.6rem 0; border-top:1px solid var(--linea); margin-top:.8rem; }
  .video.excluido .preguntas { opacity:.35; pointer-events:none; }
  .p { padding:1.1rem 0; border-top:1px solid var(--linea); }
  .p .txt { font-weight:500; margin-bottom:.7rem; }
  label { display:block; padding:.55rem .8rem; margin:.3rem 0; border:1px solid var(--linea);
          border-radius:6px; cursor:pointer; background:#fff; transition:.12s; }
  label:hover { border-color:var(--acento); background:var(--acento-claro); }
  input[type=radio] { margin-right:.6rem; }
  input:checked + span { font-weight:600; }
  .barra { position:fixed; left:0; right:0; bottom:0; background:#fff;
           border-top:1px solid var(--linea); padding:.9rem 1rem; }
  .barra .env { display:flex; align-items:center; gap:1rem; justify-content:space-between; }
  .prog { font-size:.9rem; color:var(--suave); }
  button { background:var(--acento); color:#fff; border:0; border-radius:6px;
           padding:.65rem 1.4rem; font-size:.95rem; cursor:pointer; font-weight:500; }
  button:disabled { background:#bbb; cursor:not-allowed; }
  #resultado { background:#fff; border:1px solid var(--linea); border-radius:8px;
               padding:1.5rem; margin-bottom:1.5rem; display:none; }
  table { border-collapse:collapse; width:100%; font-size:.92rem; margin-top:.8rem; }
  td,th { text-align:left; padding:.4rem .6rem; border-bottom:1px solid var(--linea); }
  td:last-child,th:last-child { text-align:right; font-variant-numeric:tabular-nums; }
  .id { font-size:.85rem; color:var(--suave); }
  input[type=text] { padding:.5rem .7rem; border:1px solid var(--linea);
                     border-radius:6px; font-size:.95rem; width:14rem; }
</style>
<div class="env">
<header>
  <h1>Quiz de retencion</h1>
  <p class="sub">Sobre videos que viste hace un tiempo. Generado el __FECHA__ ·
     __NVIDEOS__ videos · __NPREGUNTAS__ preguntas</p>
</header>

<div class="aviso">
  <strong>Antes de empezar.</strong> Contesta de memoria: no busques, no abras el video.
  Si no te acuerdas, <strong>elige igual la que te parezca mas probable</strong> — hace falta
  que contestes todas para que el resultado se pueda comparar con la linea de base.
  Si un video no lo viste, marcalo con la casilla y sus preguntas quedan fuera.
  No vas a ver si acertaste hasta el final.
</div>

<p class="id">Identificador (un seudonimo, no tu nombre):
  <input type="text" id="persona" placeholder="p.ej. juan-01" value="__PERSONA__"></p>

<div id="resultado"></div>
<div id="quiz"></div>
</div>

<div class="barra"><div class="env">
  <span class="prog" id="prog">0 de 0 contestadas</span>
  <button id="enviar" disabled>Terminar y descargar</button>
</div></div>

<script>
const DATOS = __DATOS__;
// Clave de guardado atada al conjunto de preguntas: dos tandas distintas no se
// pisan, y si se regenera el quiz con otras preguntas no se restaura basura.
const CLAVE = 'quiz_' + DATOS.map(v => v.content_item_id).join('_');

let resp = {};               // id de pregunta -> {eleccion, segundos, respondido_at}
let excluidos = new Set();   // videos marcados como no vistos
// El cronometro mide desde la ULTIMA interaccion, no desde que se abrio la
// pagina. Antes se ponia el mismo instante de arranque para TODAS las
// preguntas, con lo cual "segundos" en la pregunta 50 era el tiempo acumulado
// desde que se abrio el archivo. No medía nada.
let ultimoEvento = Date.now();

function guardar() {
  try {
    localStorage.setItem(CLAVE, JSON.stringify({
      resp, excluidos: [...excluidos],
      persona: document.getElementById('persona').value || ''
    }));
  } catch (e) { /* modo privado o sin permiso: se sigue sin autoguardado */ }
}

function restaurar() {
  let g = null;
  try { g = JSON.parse(localStorage.getItem(CLAVE) || 'null'); } catch (e) {}
  if (!g) return false;
  resp = g.resp || {};
  excluidos = new Set(g.excluidos || []);
  if (g.persona) document.getElementById('persona').value = g.persona;
  return Object.keys(resp).length > 0 || excluidos.size > 0;
}

function pintar() {
  const cont = document.getElementById('quiz');
  DATOS.forEach(v => {
    const d = document.createElement('div');
    d.className = 'video'; d.id = 'v' + v.content_item_id;
    let html = `<h2>${esc(v.titulo)}</h2><p class="canal">${esc(v.canal || '')}</p>
      <div class="preguntas">`;
    v.preguntas.forEach(p => {
      html += `<div class="p"><div class="txt">${esc(p.pregunta)}</div>`;
      p.opciones.forEach((o, i) => {
        html += `<label><input type="radio" name="q${p.id}" value="${i}">
                 <span>${esc(o)}</span></label>`;
      });
      html += `</div>`;
    });
    html += `</div><label class="novi"><input type="checkbox" class="novi-chk">
             No vi este video (o no lo recuerdo en absoluto)</label>`;
    d.innerHTML = html;
    cont.appendChild(d);

    const chk = d.querySelector('.novi-chk');
    if (excluidos.has(v.content_item_id)) { chk.checked = true; d.classList.add('excluido'); }
    chk.addEventListener('change', e => {
      if (e.target.checked) { excluidos.add(v.content_item_id); d.classList.add('excluido'); }
      else { excluidos.delete(v.content_item_id); d.classList.remove('excluido'); }
      guardar();
      progreso();
    });
    v.preguntas.forEach(p => {
      // restaurar lo ya contestado
      if (resp[p.id] !== undefined) {
        const prev = d.querySelector(`input[name=q${p.id}][value="${resp[p.id].eleccion}"]`);
        if (prev) prev.checked = true;
      }
      d.querySelectorAll(`input[name=q${p.id}]`).forEach(r => {
        r.addEventListener('change', () => {
          const ahora = Date.now();
          resp[p.id] = { eleccion: +r.value,
                         segundos: Math.round((ahora - ultimoEvento) / 1000),
                         respondido_at: ahora };
          ultimoEvento = ahora;
          guardar();
          progreso();
        });
      });
    });
  });
  progreso();
}

function pendientes() {
  let n = 0;
  DATOS.forEach(v => {
    if (excluidos.has(v.content_item_id)) return;
    v.preguntas.forEach(p => { if (resp[p.id] === undefined) n++; });
  });
  return n;
}

function progreso() {
  const falta = pendientes();
  const activas = DATOS.reduce((a, v) =>
      a + (excluidos.has(v.content_item_id) ? 0 : v.preguntas.length), 0);
  document.getElementById('prog').textContent =
      `${activas - falta} de ${activas} contestadas` + (falta ? ` · faltan ${falta}` : '');
  document.getElementById('enviar').disabled = falta > 0 || activas === 0;
}

function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

document.getElementById('enviar').addEventListener('click', () => {
  const persona = (document.getElementById('persona').value || '').trim();
  if (!persona) { alert('Falta el identificador'); return; }
  const salida = { persona_id: persona,
                   completado_at: new Date().toISOString(),
                   videos_excluidos: [...excluidos], respuestas: [] };
  let ok = 0, okDif = 0, nDif = 0;
  DATOS.forEach(v => {
    if (excluidos.has(v.content_item_id)) return;
    v.preguntas.forEach(p => {
      const r = resp[p.id];
      // Los dias se calculan contra el instante en que se contesto ESA
      // pregunta, no contra la carga de la pagina: con autoguardado, una tanda
      // puede empezarse un dia y terminarse otro.
      const dias = v.watched_at
        ? ((r.respondido_at || Date.now()) - new Date(v.watched_at).getTime()) / 86400000
        : null;
      const acierto = r.eleccion === p.correcta;
      if (acierto) ok++;
      if (p.dificil) { nDif++; if (acierto) okDif++; }
      salida.respuestas.push({ pregunta_id: p.id, eleccion: r.eleccion, acierto,
                               segundos: r.segundos,
                               dias_transcurridos: dias === null ? null : +dias.toFixed(2) });
    });
  });
  const n = salida.respuestas.length;
  const caja = document.getElementById('resultado');
  caja.style.display = 'block';
  caja.innerHTML = `<h2 style="margin-top:0;font-size:1.05rem">Listo</h2>
    <table>
      <tr><th>Preguntas contestadas</th><td>${n}</td></tr>
      <tr><th>Aciertos</th><td>${ok} (${(100*ok/n).toFixed(0)} %)</td></tr>
      <tr><th>Aciertos en el subconjunto dificil</th>
          <td>${nDif ? `${okDif} de ${nDif} (${(100*okDif/nDif).toFixed(0)} %)` : 'sin items'}</td></tr>
      <tr><th>Videos excluidos por no haberlos visto</th><td>${excluidos.size}</td></tr>
    </table>
    <p class="id" style="margin-top:1rem">El archivo se descargo. Cargalo con
    <code>cargar_quiz.py --respuestas</code>. El porcentaje de aqui arriba es
    orientativo: la retencion corregida por la linea de base se calcula en la base
    de datos.</p>`;
  caja.scrollIntoView({ behavior: 'smooth' });
  try { localStorage.removeItem(CLAVE); } catch (e) {}

  const blob = new Blob([JSON.stringify(salida, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `respuestas_${persona}_${new Date().toISOString().slice(0,10)}.json`;
  a.click();
});

const habia = restaurar();
pintar();
document.getElementById('persona').addEventListener('input', guardar);
if (habia) {
  const a = document.createElement('div');
  a.className = 'aviso';
  a.innerHTML = '<strong>Se recupero tu avance.</strong> Podes cerrar y volver cuando quieras: ' +
                'se guarda en este navegador a medida que contestas.';
  document.querySelector('#quiz').before(a);
}
window.addEventListener('beforeunload', e => {
  if (pendientes() > 0 && Object.keys(resp).length > 0) { e.preventDefault(); e.returnValue = ''; }
});
</script>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Genera el quiz en un HTML autocontenido")
    ap.add_argument("--max-videos", type=int, default=0,
                    help="para partirlo en tandas (0 = todos)")
    ap.add_argument("--persona", default="",
                    help="seudonimo. SIN esto no se excluye lo ya contestado y salen "
                         "todos los videos otra vez: pasalo siempre para las tandas.")
    ap.add_argument("--salida", default=None,
                    help="por defecto quiz_<persona>_<tanda>.html, para no pisar tandas")
    args = ap.parse_args()

    env = RAIZ / "backend" / ".env"
    try:
        from dotenv import load_dotenv
        load_dotenv(env)
    except ImportError:
        pass
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print(f"No hay DATABASE_URL en {env}")
        return 2

    # Sin seudonimo no hay exclusion posible, y la tanda 2 saldria identica a la
    # 1. Se avisa fuerte en vez de generar en silencio una lista que ya se
    # contesto -- que es justo el error que se colo antes.
    if not args.persona:
        print("AVISO  --persona esta vacio: se incluyen TODOS los videos, sin excluir "
              "los ya contestados.\n"
              "       Para la segunda tanda y siguientes, pasa --persona <seudonimo>.")

    videos, info = traer(dsn, args.max_videos, args.persona)
    if not videos:
        if args.persona and info["ya_contestados"] >= info["total_utilizables"]:
            print(f"'{args.persona}' ya contesto los {info['total_utilizables']} videos "
                  f"disponibles. No queda nada por hacer.")
            return 0
        print("No hay preguntas utilizables en quiz_preguntas. Corre antes cargar_quiz.py")
        return 1

    # Diagnostico explicito: si esto dice "ya contesto 0" cuando esperabas otra
    # cosa, o la persona esta mal escrita, o todavia no cargaste sus respuestas
    # con cargar_quiz.py --respuestas.
    if args.persona:
        restantes = info["total_utilizables"] - info["ya_contestados"]
        print(f"'{args.persona}': ya contesto {info['ya_contestados']} de "
              f"{info['total_utilizables']} videos · quedan {restantes} · "
              f"esta tanda toma {len(videos)}")
        if info["ya_contestados"] == 0:
            print("       (si esperabas que hubiera contestado algo: revisa el seudonimo "
                  "o carga primero sus respuestas)")

    n_preg = sum(len(v["preguntas"]) for v in videos)
    n_dif = sum(1 for v in videos for p in v["preguntas"] if p["dificil"])

    html = (PLANTILLA
            .replace("__DATOS__", json.dumps(videos, ensure_ascii=False))
            .replace("__FECHA__", f"{datetime.now(timezone.utc):%Y-%m-%d}")
            .replace("__NVIDEOS__", str(len(videos)))
            .replace("__NPREGUNTAS__", str(n_preg))
            .replace("__PERSONA__", args.persona))

    SALIDA.mkdir(parents=True, exist_ok=True)
    if args.salida:
        nombre = args.salida
    else:
        # La tanda se deduce de los archivos que ya hay: no hay que recordarla.
        base = f"quiz_{args.persona or 'anon'}"
        tanda = 1 + sum(1 for _ in SALIDA.glob(f"{base}_*.html"))
        nombre = f"{base}_{tanda}.html"
    ruta = SALIDA / nombre
    ruta.write_text(html, encoding="utf-8")
    print(f"{ruta}")
    print(f"  {len(videos)} videos · {n_preg} preguntas · {n_dif} del subconjunto dificil")
    print(f"  tiempo estimado: {n_preg * 0.5:.0f}-{n_preg * 0.75:.0f} minutos")
    return 0


if __name__ == "__main__":
    sys.exit(main())

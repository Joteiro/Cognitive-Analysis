#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
armar_quiz_web.py -- genera el quiz web self-service para participantes externos.

Hermano de armar_quiz_html.py, que sigue sirviendo para el flujo local de Juan.
Diferencias, todas al servicio del reclutamiento externo (docs/protocolo_reclutamiento.md):

  - Se HORNEA por persona: el token, la URL/clave publica y los videos asignados
    quedan dentro del HTML. Ese archivo ES el enlace personal.
  - El video va EMBEBIDO (YouTube IFrame API). Al terminar de verlo (o al pulsar
    "ya lo vi"), el navegador llama a la RPC registrar_visionado, que guarda el
    visto_at PROPIO de esa persona. Las preguntas de un video quedan bloqueadas
    hasta que se lo vio (o se marca "no vi este video").
  - El envio NO descarga un JSON: llama a la RPC registrar_respuestas, que valida
    el token, calcula el acierto contra la respuesta correcta EN EL SERVIDOR y
    los dias contra el visto_at. El cliente nunca puntua ni necesita mandar el
    acierto.

La clave que se hornea es la PUBLICA (anon / publishable). NUNCA la de servicio.

USO
    # da de alta (o actualiza) al participante y hornea su nucleo
    python armar_quiz_web.py --persona ana-02 --token <token> --email ana@correo.com
    # nucleo por defecto: 609,610,94,623 ; se puede cambiar con --videos
    python armar_quiz_web.py --persona ana-02 --token <token> --videos 609,610,94,623

    # modo sin base (para probar): hornea desde un JSON ya armado
    python armar_quiz_web.py --persona demo-01 --token tok --datos-json datos.json
"""
import argparse
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
SALIDA = RAIZ / "docs" / "quiz_piloto" / "formularios_web"

NUCLEO_POR_DEFECTO = "609,610,94,623"

# URL y clave PUBLICA del proyecto. La publica es publica por diseno (va en el
# HTML); la seguridad la dan las policies RLS y las funciones RPC, no ocultarla.
# Se usa la clave anon legacy (JWT): es la via probada para las llamadas REST
# directas a /rest/v1/rpc y mapea al rol `anon`, al que se le dio execute sobre
# las dos funciones. La publishable (sb_publishable_...) es mas nueva; si se
# prefiere, exportar SUPABASE_ANON_KEY antes de generar.
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://hprttdautrltgueryysz.supabase.co")
SUPABASE_ANON = os.getenv(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhwcnR0ZGF1dHJsdGd1ZXJ5eXN6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIxNDA0MDgsImV4cCI6MjA4NzcxNjQwOH0."
    "eTnJqms6REWlT2nZBR6zZZzo1_iJnvJgIPb_cVyt098")

# Trae los videos asignados (en el orden pedido) con su external_id de YouTube y
# sus preguntas utilizables. Ojo: incluye 'correcta' y 'cita' porque el HTML
# muestra las soluciones al final; el PUNTAJE, en cambio, lo calcula el servidor.
CONSULTA = """
select ci.id as content_item_id, ci.title as titulo, ci.channel as canal,
       ci.external_id,
       q.id, q.n_orden, q.pregunta, q.opciones, q.correcta, q.tipo,
       q.dificil, q.cita
from content_items ci
join quiz_preguntas q on q.content_item_id = ci.id and q.utilizable
where ci.id = any(%(ids)s)
order by array_position(%(ids)s, ci.id), q.n_orden
"""


def traer_de_db(dsn: str, ids: list) -> list:
    import psycopg2
    import psycopg2.extras
    with psycopg2.connect(dsn, connect_timeout=20) as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(CONSULTA, {"ids": ids})
            filas = [dict(r) for r in cur.fetchall()]
    return agrupar(filas, ids)


def agrupar(filas: list, ids: list) -> list:
    videos = {}
    for f in filas:
        vid = f["content_item_id"]
        if vid not in videos:
            videos[vid] = {
                "content_item_id": vid,
                "titulo": f["titulo"],
                "canal": f["canal"],
                "external_id": f["external_id"],
                "preguntas": [],
            }
        videos[vid]["preguntas"].append({
            "id": f["id"],
            "pregunta": f["pregunta"],
            "opciones": f["opciones"] if isinstance(f["opciones"], list)
                        else json.loads(f["opciones"]),
            "correcta": f["correcta"],
            "dificil": f["dificil"],
            "cita": f.get("cita"),
        })
    # respeta el orden pedido en --videos
    return [videos[i] for i in ids if i in videos]


def alta_participante(dsn: str, persona: str, token: str, email: str = "", nota: str = "") -> None:
    """Registra (o actualiza) al participante y, si hay correo, lo guarda aparte."""
    import psycopg2
    with psycopg2.connect(dsn, connect_timeout=20) as c:
        with c.cursor() as cur:
            cur.execute(
                """insert into participantes (persona_id, token, nota)
                   values (%s, %s, %s)
                   on conflict (persona_id) do update set token = excluded.token""",
                (persona, token, nota or None))
            if email:
                cur.execute(
                    "insert into participante_contacto (token, email) values (%s, %s)",
                    (token, email))
        c.commit()


def build_html(videos: list, persona: str, token: str, url: str, key: str) -> str:
    n_preg = sum(len(v["preguntas"]) for v in videos)
    return (PLANTILLA
            .replace("__DATOS__", json.dumps(videos, ensure_ascii=False))
            .replace("__PERSONA__", persona)
            .replace("__TOKEN__", token)
            .replace("__SUPA_URL__", url)
            .replace("__SUPA_KEY__", key)
            .replace("__FECHA__", f"{datetime.now(timezone.utc):%Y-%m-%d}")
            .replace("__NVIDEOS__", str(len(videos)))
            .replace("__NPREGUNTAS__", str(n_preg)))


PLANTILLA = r"""<!doctype html>
<html lang="es">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Quiz de retencion - Nutri-Score de Contenidos</title>
<style>
  :root { --tinta:#1a1a1a; --suave:#666; --linea:#e2e2e2; --fondo:#fbfbfa;
          --acento:#2f5d50; --acento-claro:#eaf1ee; --rojo:#b23b3b; }
  * { box-sizing:border-box; }
  body { margin:0; padding:0 1rem 7rem; background:var(--fondo); color:var(--tinta);
         font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  .env { max-width:44rem; margin:0 auto; }
  header { padding:2.2rem 0 1.3rem; border-bottom:1px solid var(--linea); margin-bottom:1.5rem; }
  h1 { font-size:1.5rem; margin:0 0 .4rem; letter-spacing:-.01em; }
  .sub { color:var(--suave); font-size:.95rem; margin:0; }
  .aviso { background:var(--acento-claro); border-left:3px solid var(--acento);
           padding:.9rem 1.1rem; margin:1.2rem 0; font-size:.92rem; border-radius:0 4px 4px 0; }
  .video { background:#fff; border:1px solid var(--linea); border-radius:8px;
           padding:1.4rem; margin-bottom:1.4rem; }
  .video h2 { font-size:1.05rem; margin:0 0 .2rem; line-height:1.4; }
  .canal { color:var(--suave); font-size:.85rem; margin:0 0 .9rem; }
  .marco { position:relative; width:100%; aspect-ratio:16/9; background:#000;
           border-radius:6px; overflow:hidden; margin-bottom:.7rem; }
  .marco iframe { position:absolute; inset:0; width:100%; height:100%; border:0; }
  .estado { display:flex; align-items:center; gap:.8rem; flex-wrap:wrap;
            font-size:.9rem; color:var(--suave); }
  .btnvi { background:var(--acento); color:#fff; border:0; border-radius:6px;
           padding:.5rem 1rem; font-size:.9rem; cursor:pointer; }
  .btnvi:disabled { background:#bbb; cursor:not-allowed; }
  .visto-ok { color:var(--acento); font-weight:600; }
  .novi { font-size:.88rem; color:var(--suave); display:flex; align-items:center;
          gap:.5rem; padding:.6rem 0 0; margin-top:.6rem; border-top:1px solid var(--linea); }
  .preguntas { margin-top:1rem; }
  .bloqueo { margin-top:1rem; padding:.8rem 1rem; background:#f4f4f2; border:1px dashed var(--linea);
             border-radius:6px; font-size:.9rem; color:var(--suave); }
  .video.excluido .preguntas, .video.excluido .bloqueo { opacity:.35; pointer-events:none; }
  .video.excluido .marco { opacity:.5; }
  .p { padding:1.05rem 0; border-top:1px solid var(--linea); }
  .p .txt { font-weight:500; margin-bottom:.6rem; }
  label.op { display:block; padding:.55rem .8rem; margin:.3rem 0; border:1px solid var(--linea);
          border-radius:6px; cursor:pointer; background:#fff; transition:.12s; }
  label.op:hover { border-color:var(--acento); background:var(--acento-claro); }
  input[type=radio] { margin-right:.6rem; }
  .barra { position:fixed; left:0; right:0; bottom:0; background:#fff;
           border-top:1px solid var(--linea); padding:.9rem 1rem; }
  .barra .env { display:flex; align-items:center; gap:1rem; justify-content:space-between; }
  .prog { font-size:.9rem; color:var(--suave); }
  button.enviar { background:var(--acento); color:#fff; border:0; border-radius:6px;
           padding:.65rem 1.4rem; font-size:.95rem; cursor:pointer; font-weight:500; }
  button.enviar:disabled { background:#bbb; cursor:not-allowed; }
  #resultado { background:#fff; border:1px solid var(--linea); border-radius:8px;
               padding:1.5rem; margin-bottom:1.5rem; display:none; }
  table { border-collapse:collapse; width:100%; font-size:.92rem; margin-top:.8rem; }
  td,th { text-align:left; padding:.4rem .6rem; border-bottom:1px solid var(--linea); }
  td:last-child,th:last-child { text-align:right; font-variant-numeric:tabular-nums; }
  .id { font-size:.85rem; color:var(--suave); }
  #revision .video { margin-bottom:1rem; }
  .rev-p { padding:.8rem 0; border-top:1px solid var(--linea); }
  .rev-p .txt { font-weight:500; margin-bottom:.5rem; }
  .rop { padding:.4rem .7rem; margin:.2rem 0; border-radius:6px; font-size:.93rem;
        border:1px solid var(--linea); display:flex; gap:.5rem; align-items:baseline; }
  .rop .marca { flex:0 0 1.1rem; font-weight:700; }
  .rop.correcta { background:#e7f4ec; border-color:#8fc7a6; }
  .rop.correcta .marca { color:#1f7a45; }
  .rop.elegida-mal { background:#fbeaea; border-color:#e0a3a3; }
  .rop.elegida-mal .marca { color:var(--rojo); }
  .cita { font-size:.85rem; color:var(--suave); margin:.4rem 0 0; font-style:italic;
          border-left:2px solid var(--linea); padding-left:.7rem; }
  .badge { display:inline-block; font-size:.75rem; padding:.1rem .5rem; border-radius:10px;
           background:var(--acento-claro); color:var(--acento); margin-left:.5rem; }
  /* consentimiento */
  #consent { position:fixed; inset:0; background:rgba(20,20,20,.55); display:flex;
             align-items:center; justify-content:center; padding:1rem; z-index:50; }
  .tarjeta { background:#fff; max-width:34rem; border-radius:10px; padding:1.8rem;
             max-height:90vh; overflow:auto; }
  .tarjeta h2 { margin:0 0 .8rem; font-size:1.2rem; }
  .tarjeta p { font-size:.93rem; }
  .tarjeta button { background:var(--acento); color:#fff; border:0; border-radius:6px;
             padding:.6rem 1.3rem; font-size:.95rem; cursor:pointer; margin-top:.6rem; }
  .oculto { display:none !important; }
  .err { color:var(--rojo); font-size:.9rem; }
</style>

<!-- Consentimiento: bloquea todo hasta que se acepta -->
<div id="consent">
  <div class="tarjeta">
    <h2>Antes de empezar</h2>
    <p>Este cuestionario es parte de un estudio (un trabajo de fin de master) sobre
       <strong>cuanto recordamos de los videos que vemos</strong>. Vas a ver unos videos
       cortos y despues responder algunas preguntas de memoria.</p>
    <p>Se guardan tus respuestas, el tiempo que tardas y cuando viste cada video, de forma
       <strong>anonima</strong> (bajo un seudonimo, sin tu nombre). Los datos se usan solo
       de forma agregada para el estudio. Es <strong>voluntario</strong> y podes dejarlo
       cuando quieras cerrando la pagina.</p>
    <p class="id">Participas como: <strong>__PERSONA__</strong></p>
    <button id="aceptar">Acepto y quiero empezar</button>
  </div>
</div>

<div class="env" id="app" class="oculto">
<header>
  <h1>Quiz de retencion</h1>
  <p class="sub">__NVIDEOS__ videos · __NPREGUNTAS__ preguntas · generado el __FECHA__</p>
</header>

<div class="aviso">
  <strong>Como funciona.</strong> Para cada video: miralo, y cuando termines se desbloquean
  sus preguntas. Contesta <strong>de memoria</strong> — no vuelvas a mirar el video ni busques.
  Si no te acordas, elegi igual la que te parezca mas probable. Si un video no lo llegaste a ver,
  marca la casilla y sus preguntas quedan fuera. No vas a ver si acertaste hasta el final, y podes
  cerrar y volver cuando quieras: se guarda el avance en este navegador.
</div>

<div id="resultado"></div>
<div id="quiz"></div>
<div id="revision"></div>
</div>

<div class="barra oculto" id="barra-inferior"><div class="env">
  <span class="prog" id="prog">0 de 0 contestadas</span>
  <div>
    <span class="err oculto" id="err"></span>
    <button class="enviar" id="enviar" disabled>Enviar respuestas</button>
  </div>
</div></div>

<script src="https://www.youtube.com/iframe_api"></script>
<script>
const DATOS   = __DATOS__;
const PERSONA = "__PERSONA__";
const TOKEN   = "__TOKEN__";
const SUPA_URL = "__SUPA_URL__";
const SUPA_KEY = "__SUPA_KEY__";
const CLAVE = 'quizweb_' + PERSONA + '_' + DATOS.map(v => v.content_item_id).join('_');

let resp = {};                 // pregunta_id -> {eleccion, segundos}
let excluidos = new Set();     // videos "no vi"
let vistos = {};               // content_item_id -> pct maximo visto
let ultimoEvento = Date.now();
let players = {};              // content_item_id -> YT.Player
let maxpct = {};               // content_item_id -> % maximo reproducido

function esc(s){ const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }

function guardar(){
  try{ localStorage.setItem(CLAVE, JSON.stringify({
    resp, excluidos:[...excluidos], vistos, consent:true })); }catch(e){}
}
function restaurar(){
  let g=null; try{ g=JSON.parse(localStorage.getItem(CLAVE)||'null'); }catch(e){}
  if(!g) return null;
  resp=g.resp||{}; excluidos=new Set(g.excluidos||[]); vistos=g.vistos||{};
  return g;
}

// --- RPC a Supabase (PostgREST). Solo POST a /rpc/<fn>; la clave es la publica. ---
async function rpc(fn, args){
  const r = await fetch(SUPA_URL + '/rest/v1/rpc/' + fn, {
    method:'POST',
    headers:{ 'apikey':SUPA_KEY, 'Authorization':'Bearer '+SUPA_KEY,
              'Content-Type':'application/json' },
    body: JSON.stringify(args)
  });
  if(!r.ok){ throw new Error('RPC '+fn+' HTTP '+r.status+' '+(await r.text())); }
  return r.json();
}

// --- YouTube IFrame API: crea un reproductor por video ---
window.onYouTubeIframeAPIReady = function(){
  DATOS.forEach(v => {
    players[v.content_item_id] = new YT.Player('yt-'+v.content_item_id, {
      videoId: v.external_id,
      playerVars: { rel:0, modestbranding:1 },
      events: {
        onStateChange: e => onEstado(v.content_item_id, e)
      }
    });
  });
};

function onEstado(vid, e){
  if(e.data === YT.PlayerState.PLAYING){
    if(!maxpct._timer){ maxpct._timer = setInterval(muestrear, 1000); }
  }
  if(e.data === YT.PlayerState.ENDED){
    maxpct[vid] = 100;
    marcarVisto(vid, 100, true);
  }
}
function muestrear(){
  DATOS.forEach(v => {
    const p = players[v.content_item_id];
    if(p && p.getDuration){
      const d = p.getDuration()||0, t = p.getCurrentTime()||0;
      if(d>0){ const pct = Math.min(100, Math.round(100*t/d));
               maxpct[v.content_item_id] = Math.max(maxpct[v.content_item_id]||0, pct);
               const b = document.getElementById('vi-'+v.content_item_id);
               if(b && maxpct[v.content_item_id] >= 5) b.disabled = false; }
    }
  });
}

async function marcarVisto(vid, pct, completo){
  if(vistos[vid] !== undefined && vistos[vid] >= (pct||0) && !completo) return;
  try{
    await rpc('registrar_visionado', { p_token:TOKEN, p_content_item_id:vid,
              p_reproduccion_pct:pct, p_completo:!!completo });
    vistos[vid] = Math.max(vistos[vid]||0, pct||0);
    guardar(); pintarEstado(vid); progreso();
  }catch(err){ mostrarError('No se pudo registrar el visionado. Revisa tu conexion.'); }
}

function pintarEstado(vid){
  const cont = document.getElementById('estado-'+vid);
  const preg = document.getElementById('preg-'+vid);
  const blq  = document.getElementById('blq-'+vid);
  if(vistos[vid] !== undefined){
    cont.innerHTML = '<span class="visto-ok">✓ Video registrado</span>';
    if(preg) preg.classList.remove('oculto');
    if(blq)  blq.classList.add('oculto');
  }
}

function pintar(){
  const cont = document.getElementById('quiz');
  DATOS.forEach(v => {
    const d = document.createElement('div');
    d.className='video'; d.id='v'+v.content_item_id;
    let html = `<h2>${esc(v.titulo)}</h2><p class="canal">${esc(v.canal||'')}</p>
      <div class="marco"><div id="yt-${v.content_item_id}"></div></div>
      <div class="estado">
        <button class="btnvi" id="vi-${v.content_item_id}" disabled>Ya termine de verlo</button>
        <span id="estado-${v.content_item_id}">Mira el video para desbloquear las preguntas.</span>
      </div>
      <label class="novi"><input type="checkbox" class="novi-chk">
        No vi este video (o no lo recuerdo en absoluto)</label>
      <div class="bloqueo" id="blq-${v.content_item_id}">Las preguntas aparecen cuando marques el video como visto.</div>
      <div class="preguntas oculto" id="preg-${v.content_item_id}">`;
    v.preguntas.forEach(p => {
      html += `<div class="p"><div class="txt">${esc(p.pregunta)}</div>`;
      p.opciones.forEach((o,i)=>{
        html += `<label class="op"><input type="radio" name="q${p.id}" value="${i}">
                 <span>${esc(o)}</span></label>`;
      });
      html += `</div>`;
    });
    html += `</div>`;
    d.innerHTML = html;
    cont.appendChild(d);

    // boton "ya lo vi"
    d.querySelector('#vi-'+v.content_item_id).addEventListener('click', ()=>{
      const pct = maxpct[v.content_item_id]||0;
      marcarVisto(v.content_item_id, pct, pct>=90);
    });
    // "no vi este video"
    const chk = d.querySelector('.novi-chk');
    if(excluidos.has(v.content_item_id)){ chk.checked=true; d.classList.add('excluido'); }
    chk.addEventListener('change', e=>{
      if(e.target.checked){ excluidos.add(v.content_item_id); d.classList.add('excluido'); }
      else { excluidos.delete(v.content_item_id); d.classList.remove('excluido'); }
      guardar(); progreso();
    });
    // preguntas: restaurar y escuchar
    v.preguntas.forEach(p=>{
      if(resp[p.id]!==undefined){
        const prev=d.querySelector(`input[name=q${p.id}][value="${resp[p.id].eleccion}"]`);
        if(prev) prev.checked=true;
      }
      d.querySelectorAll(`input[name=q${p.id}]`).forEach(r=>{
        r.addEventListener('change', ()=>{
          const ahora=Date.now();
          resp[p.id]={ eleccion:+r.value, segundos:Math.round((ahora-ultimoEvento)/1000) };
          ultimoEvento=ahora; guardar(); progreso();
        });
      });
    });
    if(vistos[v.content_item_id]!==undefined) pintarEstado(v.content_item_id);
  });
  progreso();
}

function pendientes(){
  let n=0;
  DATOS.forEach(v=>{
    if(excluidos.has(v.content_item_id)) return;
    if(vistos[v.content_item_id]===undefined){ n+=v.preguntas.length; return; }
    v.preguntas.forEach(p=>{ if(resp[p.id]===undefined) n++; });
  });
  return n;
}
function progreso(){
  const falta=pendientes();
  const activas=DATOS.reduce((a,v)=> a+(excluidos.has(v.content_item_id)?0:v.preguntas.length),0);
  document.getElementById('prog').textContent =
    `${activas-falta} de ${activas} contestadas`+(falta?` · faltan ${falta}`:'');
  document.getElementById('enviar').disabled = falta>0 || activas===0;
}

function mostrarError(msg){
  const e=document.getElementById('err'); e.textContent=msg; e.classList.remove('oculto');
  setTimeout(()=>e.classList.add('oculto'), 6000);
}

function pintarRevision(){
  const cont=document.getElementById('revision');
  let html='<h2 style="font-size:1.1rem">Soluciones</h2>';
  DATOS.forEach(v=>{
    if(excluidos.has(v.content_item_id)) return;
    html+=`<div class="video"><h2>${esc(v.titulo)}</h2>`;
    v.preguntas.forEach(p=>{
      const elegida = resp[p.id]?resp[p.id].eleccion:null;
      const bien = elegida===p.correcta;
      html+=`<div class="rev-p"><div class="txt">${esc(p.pregunta)}`+
            (bien?'<span class="badge">acertaste</span>'
                 :'<span class="badge" style="background:#fbeaea;color:#b23b3b">fallaste</span>')+`</div>`;
      p.opciones.forEach((o,i)=>{
        let cls='rop', marca='';
        if(i===p.correcta){ cls+=' correcta'; marca='✓'; }
        else if(i===elegida){ cls+=' elegida-mal'; marca='✗'; }
        html+=`<div class="${cls}"><span class="marca">${marca}</span><span>${esc(o)}</span></div>`;
      });
      if(p.cita) html+=`<p class="cita">En el video: «${esc(p.cita)}»</p>`;
      html+=`</div>`;
    });
    html+=`</div>`;
  });
  cont.innerHTML=html;
}

document.getElementById('enviar').addEventListener('click', async ()=>{
  const btn=document.getElementById('enviar'); btn.disabled=true;
  const payload=[];
  DATOS.forEach(v=>{
    if(excluidos.has(v.content_item_id)) return;
    v.preguntas.forEach(p=>{
      const r=resp[p.id];
      payload.push({ pregunta_id:p.id, eleccion:r.eleccion, segundos:r.segundos });
    });
  });
  try{
    await rpc('registrar_respuestas', { p_token:TOKEN, p_respuestas:payload });
  }catch(err){
    mostrarError('No se pudieron enviar las respuestas. Revisa tu conexion e intenta de nuevo.');
    btn.disabled=false; return;
  }
  // exito: puntaje orientativo + soluciones
  let ok=0, okDif=0, nDif=0;
  DATOS.forEach(v=>{ if(excluidos.has(v.content_item_id)) return;
    v.preguntas.forEach(p=>{ const bien=resp[p.id].eleccion===p.correcta;
      if(bien) ok++; if(p.dificil){ nDif++; if(bien) okDif++; } }); });
  const n=payload.length;
  const caja=document.getElementById('resultado'); caja.style.display='block';
  caja.innerHTML=`<h2 style="margin-top:0;font-size:1.05rem">¡Listo, gracias!</h2>
    <table>
      <tr><th>Preguntas contestadas</th><td>${n}</td></tr>
      <tr><th>Aciertos</th><td>${ok} (${n?(100*ok/n).toFixed(0):0} %)</td></tr>
      <tr><th>Aciertos en las mas dificiles</th><td>${nDif?`${okDif} de ${nDif}`:'sin items'}</td></tr>
      <tr><th>Videos que marcaste no haber visto</th><td>${excluidos.size}</td></tr>
    </table>
    <p class="id" style="margin-top:1rem">Tus respuestas se guardaron. El porcentaje es orientativo.
       Abajo estan las soluciones de todo lo que contestaste.</p>`;
  document.getElementById('quiz').classList.add('oculto');
  document.querySelectorAll('.aviso').forEach(a=>a.classList.add('oculto'));
  document.getElementById('barra-inferior').classList.add('oculto');
  pintarRevision();
  caja.scrollIntoView({behavior:'smooth'});
  try{ localStorage.setItem(CLAVE, JSON.stringify({done:true})); }catch(e){}
});

// --- arranque ---
function iniciar(){
  document.getElementById('app').classList.remove('oculto');
  document.getElementById('barra-inferior').classList.remove('oculto');
  pintar();
  const g = JSON.parse(localStorage.getItem(CLAVE)||'null');
  if(g && (Object.keys(resp).length || excluidos.size || Object.keys(vistos).length)){
    const a=document.createElement('div'); a.className='aviso';
    a.innerHTML='<strong>Se recupero tu avance.</strong> Podes seguir donde lo dejaste.';
    document.getElementById('quiz').before(a);
  }
}

(function(){
  const g = restaurar();
  if(g && g.done){
    document.body.innerHTML='<div class="env"><header><h1>Ya completaste este cuestionario</h1>'+
      '<p class="sub">Gracias por participar. Podes cerrar la pagina.</p></header></div>';
    return;
  }
  document.getElementById('aceptar').addEventListener('click', ()=>{
    document.getElementById('consent').classList.add('oculto');
    guardar(); iniciar();
  });
  // si ya habia aceptado antes, saltar el consentimiento
  if(g && g.consent){ document.getElementById('consent').classList.add('oculto'); iniciar(); }
})();
</script>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Genera el quiz web self-service (uno por persona)")
    ap.add_argument("--persona", required=True, help="seudonimo del participante")
    ap.add_argument("--token", default=None, help="token del enlace personal (se genera si falta)")
    ap.add_argument("--videos", default=NUCLEO_POR_DEFECTO,
                    help=f"ids separados por coma (defecto: nucleo {NUCLEO_POR_DEFECTO})")
    ap.add_argument("--email", default="", help="correo para el recordatorio del diferido (opcional)")
    ap.add_argument("--datos-json", default=None,
                    help="modo sin base: hornea desde un JSON [{content_item_id,titulo,canal,external_id,preguntas:[...]}]")
    ap.add_argument("--salida", default=None)
    args = ap.parse_args()

    ids = [int(x) for x in args.videos.split(",") if x.strip()]
    token = args.token or ("tok-" + secrets.token_urlsafe(12))

    if args.datos_json:
        videos = json.loads(Path(args.datos_json).read_text(encoding="utf-8"))
        videos = [v for v in videos if v["content_item_id"] in ids] or videos
    else:
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
        alta_participante(dsn, args.persona, token, args.email, nota="reclutamiento externo")
        videos = traer_de_db(dsn, ids)

    if not videos:
        print("No hay videos con preguntas utilizables para esos ids.")
        return 1

    url = os.getenv("SUPABASE_URL", SUPABASE_URL)
    key = os.getenv("SUPABASE_ANON_KEY", SUPABASE_ANON)
    html = build_html(videos, args.persona, token, url, key)

    SALIDA.mkdir(parents=True, exist_ok=True)
    nombre = args.salida or f"quiz_web_{args.persona}.html"
    ruta = SALIDA / nombre
    ruta.write_text(html, encoding="utf-8")

    n_preg = sum(len(v["preguntas"]) for v in videos)
    print(f"{ruta}")
    print(f"  persona: {args.persona} · token: {token}")
    print(f"  {len(videos)} videos · {n_preg} preguntas")
    if not args.datos_json:
        print(f"  participante dado de alta en la base" + (f" · correo guardado" if args.email else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

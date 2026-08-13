// content.js — Cognitive Analysis
//
// Registra el video que se esta viendo y muestra el panel de descriptores.
//
// QUE CAMBIO RESPECTO DE LA VERSION ANTERIOR
// El badge mostraba una letra A-E. Se saco entera: una letra agregada sobre
// ocho medidas subjetivamente ponderadas transmite una autoridad que el
// sistema no tiene. En su lugar va el percentil de cada descriptor por
// separado, sin combinarlos y sin adjetivos.
//
// DECISION DE DISENO: NO HAY COLORES DE SEMAFORO
// Verde y rojo volverian a meter el juicio por la puerta de atras. Un ritmo
// alto no es bueno ni malo; depende de para que estes mirando el video. Todas
// las barras usan el mismo tono y lo unico que informa es la POSICION del
// marcador. La etiqueta de un alimento tampoco pinta de rojo las calorias.

const API_BASE      = 'https://cognitive-analysis-gfpg.onrender.com';
const BACKEND_URL   = `${API_BASE}/videos`;
const PANEL_URL     = `${API_BASE}/panel`;
const DELAY_MS      = 2500;
const POLL_INTERVAL = 4000;   // Render se duerme; el arranque en frio tarda
const POLL_MAX      = 20;     // ~80 s de tolerancia

// Nombres legibles. La clave tecnica queda visible al pasar el mouse, para que
// se pueda rastrear hasta el glosario.
const ETIQUETAS = {
  ritmo_ppm:         'Ritmo del habla',
  cifras_100w:       'Densidad de cifras',
  atribucion_1000w:  'Menciones de fuente',
  mattr_200:         'Variedad de vocabulario',
  conectores_1000w:  'Conectores lógicos',
  enlaces_externos:  'Enlaces externos',
  promocional_1000w: 'Contenido promocional',
  cobertura_titulo:  'Correspondencia con el título',
};

const ID = 'cogana-panel';

// ─── PANEL ────────────────────────────────────────────────────────────────────

function quitarPanel() {
  document.getElementById(ID)?.remove();
}

function contenedor() {
  quitarPanel();
  const host = document.createElement('div');
  host.id = ID;
  Object.assign(host.style, {
    position: 'fixed', bottom: '20px', right: '20px', zIndex: 99999,
  });
  // Shadow DOM: aisla del CSS de YouTube, que si no pisa todo.
  const sh = host.attachShadow({ mode: 'open' });
  sh.innerHTML = `<style>
    :host, * { box-sizing: border-box; }
    .caja {
      width: 330px; max-height: 78vh; overflow-y: auto;
      background: #12141a; color: #e8eaf0;
      border: 1px solid #2a2e3a; border-radius: 12px;
      font: 13px/1.45 -apple-system, "Segoe UI", Roboto, sans-serif;
      box-shadow: 0 8px 28px rgba(0,0,0,.45);
    }
    .cab { display:flex; align-items:baseline; gap:8px;
           padding:12px 14px 8px; border-bottom:1px solid #2a2e3a; }
    .tit { font-weight:600; font-size:13px; flex:1; }
    .fmt { font-size:11px; color:#8b93a7; }
    .x { cursor:pointer; color:#6b7280; font-size:16px; line-height:1;
         background:none; border:none; padding:0 2px; }
    .x:hover { color:#e8eaf0; }
    .cuerpo { padding: 6px 14px 12px; }
    .fila { padding: 9px 0; border-bottom: 1px solid #1c1f28; }
    .fila:last-child { border-bottom: none; }
    .lin1 { display:flex; justify-content:space-between; align-items:baseline; gap:8px; }
    .nom { font-size:12.5px; }
    .val { font-size:11px; color:#8b93a7; white-space:nowrap; }
    /* Un solo tono a proposito: el color no debe sugerir bueno ni malo. */
    .barra { position:relative; height:5px; margin-top:7px;
             background:#232733; border-radius:3px; }
    .marca { position:absolute; top:-3px; width:3px; height:11px;
             background:#7aa2f7; border-radius:2px; transform:translateX(-50%); }
    .mediana { position:absolute; top:-1px; width:1px; height:7px;
               background:#4b5263; transform:translateX(-50%); }
    .pie { font-size:10.5px; color:#8b93a7; margin-top:5px; }
    .aus { font-size:11.5px; color:#8b93a7; margin-top:5px; }
    .nota { padding:10px 14px; border-top:1px solid #2a2e3a;
            font-size:10.5px; color:#6b7280; }
    .vacio { padding:16px 14px; font-size:12.5px; color:#a8b0c2; }
    .cargando { padding:14px; font-size:12.5px; color:#8b93a7; }
  </style><div class="caja"></div>`;
  document.body.appendChild(host);
  return sh.querySelector('.caja');
}

function cabecera(caja, subtitulo) {
  caja.innerHTML = `<div class="cab">
      <span class="tit">Información del contenido</span>
      <span class="fmt">${subtitulo || ''}</span>
      <button class="x" title="Cerrar">×</button>
    </div>`;
  caja.querySelector('.x').addEventListener('click', quitarPanel);
}

function panelCargando() {
  const caja = contenedor();
  cabecera(caja, '');
  caja.insertAdjacentHTML('beforeend',
    '<div class="cargando">Analizando…</div>');
}

function panelSinDatos(d) {
  const caja = contenedor();
  cabecera(caja, '');
  const porque = d.cobertura != null
    ? `El video tiene muy poca habla para su duración (cobertura ${d.cobertura}).`
    : 'No se pudo obtener una transcripción de este video.';
  caja.insertAdjacentHTML('beforeend',
    `<div class="vacio"><b>Sin datos suficientes.</b><br>${porque}<br><br>
     No es una puntuación baja: estos descriptores miden el habla, y hay videos
     —música, tomas sin voz, partidas comentadas a medias— a los que sencillamente
     no les aplican.</div>`);
}

function fila(d) {
  const nombre = ETIQUETAS[d.clave] || d.clave;
  const val = d.valor == null ? '—'
            : `${(+d.valor).toLocaleString('es', { maximumFractionDigits: 2 })} ${d.unidad || ''}`;

  if (d.tipo === 'presencia') {
    const pctSin = Math.round((d.p_ausencia || 0) * 100);
    if (d.estado === 'ausente') {
      return `<div class="fila">
        <div class="lin1"><span class="nom" title="${d.clave}">${nombre}</span>
        <span class="val">no tiene</span></div>
        <div class="aus">El ${pctSin} % de los videos de este formato tampoco.</div>
      </div>`;
    }
    // Presente. Ojo con el percentil bajo: "presente pero p0" suena raro si no
    // se explica que la comparacion es solo contra los que TAMBIEN tienen.
    const p = d.percentil;
    const detalle = p == null ? ''
      : p <= 5  ? `Tiene, y menos que casi todos los ${d.n_presentes} que tienen.`
      : p >= 95 ? `Tiene, y más que casi todos los ${d.n_presentes} que tienen.`
      : `Más que el ${Math.round(p)} % de los ${d.n_presentes} que tienen.`;
    return `<div class="fila">
      <div class="lin1"><span class="nom" title="${d.clave}">${nombre}</span>
      <span class="val">${val}</span></div>
      ${p == null ? '' : `<div class="barra">
        <div class="marca" style="left:${Math.min(100, Math.max(0, p))}%"></div>
      </div>`}
      <div class="pie">${detalle} El ${pctSin} % no tiene ninguno.</div>
    </div>`;
  }

  if (d.estado !== 'medido' || d.percentil == null) {
    return `<div class="fila">
      <div class="lin1"><span class="nom" title="${d.clave}">${nombre}</span>
      <span class="val">sin dato</span></div></div>`;
  }

  const p = Math.min(100, Math.max(0, d.percentil));
  return `<div class="fila">
    <div class="lin1"><span class="nom" title="${d.clave}">${nombre}</span>
    <span class="val">${val}</span></div>
    <div class="barra">
      <div class="mediana" style="left:50%" title="mediana del corpus"></div>
      <div class="marca" style="left:${p}%"></div>
    </div>
    <div class="pie">Más que el ${Math.round(p)} % de los videos comparables.</div>
  </div>`;
}

function panelDatos(d) {
  const caja = contenedor();
  cabecera(caja, d.formato ? d.formato.replace('_', '/') : '');
  const filas = (d.descriptores || []).map(fila).join('');
  const fuente = d.origen_transcripcion === 'base' ? 'transcripción ya almacenada'
                                                   : 'transcripción obtenida ahora';
  caja.insertAdjacentHTML('beforeend',
    `<div class="cuerpo">${filas}</div>
     <div class="nota">Percentiles relativos al corpus de referencia de YouTube
     en español (${d.frame_version}), comparando contra videos del mismo formato
     cuando corresponde. <b>No es una calificación.</b><br>${fuente}.</div>`);
}

async function pedirPanel(videoId, intento = 0) {
  if (intento >= POLL_MAX) {
    console.warn('[CognitiveAnalysis] el panel no estuvo listo a tiempo.');
    quitarPanel();
    return;
  }
  if (new URLSearchParams(location.search).get('v') !== videoId) return;

  try {
    const res = await fetch(`${PANEL_URL}/${videoId}`);
    if (res.ok) {
      const d = await res.json();
      // apto === null es "todavia procesando": el enriquecimiento en background
      // no termino. Se sigue reintentando en vez de dar por perdido el panel.
      if (d.apto === null || d.estado === 'procesando') {
        setTimeout(() => pedirPanel(videoId, intento + 1), POLL_INTERVAL);
        return;
      }
      if (d.apto) panelDatos(d); else panelSinDatos(d);
      return;
    }
    // 404 = la ruta no existe en el servidor (deploy viejo). Conviene decirlo
    // en vez de desaparecer en silencio, que fue justo lo que costo diagnosticar.
    if (res.status === 404) {
      console.warn('[CognitiveAnalysis] /panel devolvio 404: el backend no tiene '
        + 'la ruta desplegada. Revisa /openapi.json en Render.');
      quitarPanel();
      return;
    }
  } catch (_) { /* Render dormido: se reintenta */ }

  setTimeout(() => pedirPanel(videoId, intento + 1), POLL_INTERVAL);
}

// ─── EXTRACCION ───────────────────────────────────────────────────────────────
function extractVideoData() {
  const videoId = new URLSearchParams(window.location.search).get('v');
  if (!videoId) return null;

  const title =
    document.querySelector('h1.ytd-watch-metadata yt-formatted-string')?.textContent?.trim()
    || document.title.replace(/\s*[-–]\s*YouTube\s*$/i, '').trim()
    || 'Unknown title';

  const channel =
    document.querySelector('ytd-channel-name yt-formatted-string a')?.textContent?.trim()
    || document.querySelector('#channel-name a')?.textContent?.trim()
    || document.querySelector('#owner-name a')?.textContent?.trim()
    || 'Unknown channel';

  const videoEl  = document.querySelector('video.html5-main-video');
  const duration = videoEl && isFinite(videoEl.duration) ? Math.round(videoEl.duration) : null;
  const viewsRaw = document.querySelector('#info .ytd-video-view-count-renderer')?.textContent?.trim() || null;

  return {
    video_id: videoId, title,
    url: `https://www.youtube.com/watch?v=${videoId}`,
    channel, duration_seconds: duration, view_count_raw: viewsRaw,
    tracked_at: new Date().toISOString(),
  };
}

// ─── ENVIO ────────────────────────────────────────────────────────────────────
async function sendToBackend(payload) {
  try {
    const res = await fetch(BACKEND_URL, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      console.log(`%c[CognitiveAnalysis] ✓ tracked: "${payload.title}"`, 'color:#4ade80');
      return true;
    }
    console.warn(`[CognitiveAnalysis] Backend respondió ${res.status}:`, await res.text());
  } catch (err) {
    console.error('[CognitiveAnalysis] No se pudo alcanzar el backend.', err);
  }
  return false;
}

// ─── NAVEGACION ───────────────────────────────────────────────────────────────
const trackedThisSession = new Set();

function getDurationWhenReady(videoEl, timeoutMs = 5000) {
  return new Promise((resolve) => {
    if (videoEl && isFinite(videoEl.duration) && videoEl.duration > 0) {
      return resolve(Math.round(videoEl.duration));
    }
    if (!videoEl) return resolve(null);
    const onLoaded = () => {
      clearTimeout(timer);
      resolve(isFinite(videoEl.duration) ? Math.round(videoEl.duration) : null);
    };
    const timer = setTimeout(() => {
      videoEl.removeEventListener('loadedmetadata', onLoaded);
      resolve(null);
    }, timeoutMs);
    videoEl.addEventListener('loadedmetadata', onLoaded, { once: true });
  });
}

function handleNavigation() {
  if (window.location.pathname !== '/watch') return;
  quitarPanel();

  setTimeout(async () => {
    const data = extractVideoData();
    if (!data) return;
    panelCargando();

    // El panel no depende del registro: se pide igual aunque el POST falle.
    // Son dos cosas distintas y no tienen por que caerse juntas.
    pedirPanel(data.video_id);

    if (trackedThisSession.has(data.video_id)) return;
    if (data.duration_seconds === null) {
      data.duration_seconds = await getDurationWhenReady(
        document.querySelector('video.html5-main-video'));
    }
    if (await sendToBackend(data)) trackedThisSession.add(data.video_id);
  }, DELAY_MS);
}

if (window.location.pathname === '/watch') handleNavigation();
window.addEventListener('yt-navigate-finish', handleNavigation);

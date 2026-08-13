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
const POLL_MAX      = 24;

// Espera progresiva: rapido al principio, mas lento despues. En total ~5 min.
//
// Los 80 s de la version anterior alcanzaban para un video ya procesado y no
// para uno nuevo. La cadena completa en el plan gratuito de Render es:
// despertar el servicio (hasta 60 s) + pedir la transcripcion a Supadata
// (10-20 s) + cargar pandas la primera vez que se pide un panel (10-20 s).
// Darse por vencido a los 80 s es rendirse justo antes de que llegue.
//
// Sube la espera en vez de repetir cada 4 s porque los primeros intentos son
// los que valen: si a los dos minutos no esta, tampoco va a estar al
// siguiente parpadeo, y machacar el servidor no lo apura.
function esperaMs(intento) {
  return Math.min(3000 + intento * 1000, 15000);
}

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
    /* Ambar, no rojo: es una advertencia de alcance, no un error. */
    .aviso { margin:10px 14px 0; padding:8px 10px; border-radius:6px;
             background:#2a2416; border:1px solid #4a3f1e; color:#d9c98a;
             font-size:11px; line-height:1.4; }
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

  // El backend ahora explica POR QUE no hay panel (sin subtitulos, sin credito,
  // enriquecimiento incompleto). Si mando un motivo, se muestra ese: es mas
  // preciso que cualquier texto generico que se pueda escribir aca.
  const porque = d.mensaje
    || (d.cobertura != null
        ? `El video tiene muy poca habla para su duración (cobertura ${d.cobertura}).`
        : 'No se pudo obtener una transcripción de este video.');

  // La aclaracion de "no es una nota baja" solo aplica cuando el video
  // efectivamente se midio y no alcanzo. Si el problema fue tecnico —no habia
  // subtitulos, se acabo el credito— ponerla confunde: sugiere que el video
  // tiene algo raro cuando el que fallo fue el sistema.
  const esTecnico = ['sin_creditos', 'error_de_transcripcion', 'limite_de_ritmo',
                     'enriquecimiento_incompleto', 'sin_respuesta'].includes(d.motivo);
  const matiz = esTecnico ? '' : `<br><br>
     No es una puntuación baja: estos descriptores miden el habla, y hay videos
     —música, tomas sin voz, partidas comentadas a medias— a los que sencillamente
     no les aplican.`;

  const titulo = esTecnico ? 'No se pudo analizar.' : 'Sin datos suficientes.';
  caja.insertAdjacentHTML('beforeend',
    `<div class="vacio"><b>${titulo}</b><br>${porque}${matiz}</div>`);
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
  const aviso = d.aviso_idioma
    ? `<div class="aviso">⚠ ${d.aviso_idioma}</div>` : '';
  caja.insertAdjacentHTML('beforeend',
    `${aviso}<div class="cuerpo">${filas}</div>
     <div class="nota">Percentiles relativos al corpus de referencia de YouTube
     en español (${d.frame_version}), comparando contra videos del mismo formato
     cuando corresponde. <b>No es una calificación.</b><br>${fuente}.</div>`);
}

// ¿Sigue vivo el script?
//
// Cuando se recarga la extension desde chrome://extensions, las pestanas que
// ya estaban abiertas se quedan corriendo el script VIEJO, desconectado. Ese
// script sigue pudiendo tocar el DOM —dibuja el recuadro, muestra
// "Analizando"— pero cualquier fetch suyo falla. Desde afuera se ve como un
// servidor lento, y no lo es: es un fantasma.
//
// chrome.runtime.id es la forma limpia de detectarlo: en un script huerfano
// queda undefined, o el propio acceso tira.
function contextoVivo() {
  try {
    return Boolean(chrome && chrome.runtime && chrome.runtime.id);
  } catch (_) {
    return false;
  }
}

function avisarHuerfano() {
  console.error('[CognitiveAnalysis] esta pestaña quedó con el script viejo '
    + '(la extensión se recargó después de abrirla). Recargá la página.');
  panelSinDatos({
    motivo: 'sin_respuesta',
    mensaje: 'La extensión se recargó después de abrir esta pestaña, así que '
           + 'quedó desconectada. Recargá la página (F5).',
  });
}

async function pedirPanel(videoId, intento = 0) {
  // Se comprueba en cada vuelta y no una sola vez al principio: la extension
  // se puede recargar en cualquier momento, incluso en medio del sondeo.
  if (!contextoVivo()) {
    avisarHuerfano();
    return;
  }
  if (intento >= POLL_MAX) {
    // Antes esto hacia quitarPanel(): la etiqueta giraba ~80 s y despues
    // desaparecia sin decir nada. Desde afuera es indistinguible de que la
    // extension este rota, y es exactamente lo que mas cuesta diagnosticar.
    console.warn('[CognitiveAnalysis] el panel no estuvo listo a tiempo.');
    panelSinDatos({
      motivo: 'sin_respuesta',
      mensaje: 'El análisis está tardando más de lo normal. Recargá la página: '
             + 'la primera consulta del día despierta el servidor y puede '
             + 'demorar un par de minutos.',
    });
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
        // El backend dice que el video NO esta en la base. O sea que el POST
        // de registro se perdio, y esperar no lo va a arreglar: seguiriamos
        // preguntando por algo que nadie mando. Se reintenta el registro una
        // sola vez, para no entrar en un bucle de POSTs.
        // Se permiten dos rondas y no una: la primera puede haberse agotado
        // entera mientras Render todavia arrancaba.
        if (d.registrado === false && ultimoPayload
            && ultimoPayload.video_id === videoId
            && reintentosRegistro < MAX_REINTENTOS_PANEL) {
          reintentosRegistro += 1;
          console.warn('[CognitiveAnalysis] el video no figura en la base; '
            + 'se reintenta el registro.');
          sendToBackend(ultimoPayload);
        }
        setTimeout(() => pedirPanel(videoId, intento + 1), esperaMs(intento));
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
      panelSinDatos({
        motivo: 'sin_respuesta',
        mensaje: 'El servidor no tiene la ruta /panel desplegada todavía.',
      });
      return;
    }
  } catch (err) {
    // Un fetch que falla puede ser Render dormido (se reintenta) o el script
    // huerfano (no tiene sentido reintentar: nunca va a salir).
    if (!contextoVivo() || String(err).includes('Extension context invalidated')) {
      avisarHuerfano();
      return;
    }
    console.warn(`[CognitiveAnalysis] /panel no respondió `
      + `(intento ${intento + 1}/${POLL_MAX}):`, err.message || err);
  }

  setTimeout(() => pedirPanel(videoId, intento + 1), esperaMs(intento));
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

// El ultimo payload armado, para poder reintentar el registro si el panel
// avisa que el video no llego a la base.
let ultimoPayload = null;

// Pausas entre intentos de registro, en segundos: 0, 5, 12, 25, 45.
// En total cubre ~90 s desde el primer intento.
//
// POR QUE TAN LARGO
// Los tres intentos anteriores (0, 3 y 9 s) se agotaban en diez segundos, y
// el arranque en frio de Render tarda unos cincuenta. O sea que los tres
// caian dentro de la ventana en la que el servidor todavia no existe, y los
// tres devolvian "Failed to fetch".
//
// Eso explica el sintoma que parecia imposible: el panel (GET) funcionaba y
// el registro (POST) no, contra el MISMO servidor. No era que el POST
// estuviera roto — era que el GET reintentaba durante cinco minutos y el
// POST se rendia a los diez segundos. El GET esperaba a que el servidor
// despertara; el POST, no.
const PAUSAS_REGISTRO = [5000, 7000, 13000, 20000];

async function sendToBackend(payload, intentos = PAUSAS_REGISTRO.length + 1) {
  for (let i = 0; i < intentos; i++) {
    try {
      const res = await fetch(BACKEND_URL, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        console.log(`%c[CognitiveAnalysis] ✓ tracked: "${payload.title}"`, 'color:#4ade80');
        return true;
      }
      console.warn(`[CognitiveAnalysis] Backend respondió ${res.status} `
        + `(intento ${i + 1}/${intentos}):`, await res.text());
    } catch (err) {
      // Sintoma clasico y muy confuso: se recarga la extension desde
      // chrome://extensions y las pestanas de YouTube que ya estaban
      // abiertas siguen corriendo el script viejo, que ya no puede hacer
      // nada. Todo "parece" andar y ningun pedido sale. Conviene decirlo.
      if (String(err).includes('Extension context invalidated')) {
        console.error('[CognitiveAnalysis] La extensión se recargó: esta '
          + 'pestaña quedó con el script viejo. Recargá la página.');
        panelSinDatos({
          motivo: 'sin_respuesta',
          mensaje: 'La extensión se recargó mientras esta pestaña estaba '
                 + 'abierta. Recargá la página (F5) para reactivarla.',
        });
        return false;
      }
      console.error(`[CognitiveAnalysis] No se pudo alcanzar el backend `
        + `(intento ${i + 1}/${intentos}).`, err);
    }
    if (i < intentos - 1) {
      await new Promise((r) => setTimeout(r, PAUSAS_REGISTRO[i] || 20000));
    }
  }
  return false;
}

// ─── NAVEGACION ───────────────────────────────────────────────────────────────
const trackedThisSession = new Set();
let reintentosRegistro = 0;   // rondas de reintento disparadas por el panel
const MAX_REINTENTOS_PANEL = 2;

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
  reintentosRegistro = 0;

  setTimeout(async () => {
    const data = extractVideoData();
    if (!data) return;
    // Antes de dibujar nada: si el script esta huerfano, mostrar "Analizando"
    // es mentirle al usuario. No va a analizar nada.
    if (!contextoVivo()) {
      avisarHuerfano();
      return;
    }
    panelCargando();
    ultimoPayload = data;

    // El panel no depende del registro: se pide igual aunque el POST falle.
    // Son dos cosas distintas y no tienen por que caerse juntas.
    pedirPanel(data.video_id);

    if (trackedThisSession.has(data.video_id)) return;
    // Se marca ANTES de mandar, no despues. YouTube dispara
    // yt-navigate-finish mas de una vez por navegacion, y como el chequeo
    // estaba antes de un await, las dos pasadas lo cruzaban antes de que
    // ninguna terminara: salian dos POST identicos con 0,2 s de diferencia.
    // Eso ademas lanzaba dos enriquecimientos en paralelo, que es de donde
    // salio la fila con status 'ok' y error 'sin_creditos' a la vez.
    trackedThisSession.add(data.video_id);

    if (data.duration_seconds === null) {
      data.duration_seconds = await getDurationWhenReady(
        document.querySelector('video.html5-main-video'));
    }
    // Si fallaron los tres intentos se desmarca, para que un refresh de la
    // pagina vuelva a intentarlo en vez de darlo por hecho.
    if (!await sendToBackend(data)) trackedThisSession.delete(data.video_id);
  }, DELAY_MS);
}

if (window.location.pathname === '/watch') handleNavigation();
window.addEventListener('yt-navigate-finish', handleNavigation);

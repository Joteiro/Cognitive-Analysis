/**
 * Prueba de content.js sin navegador y sin backend.
 *
 * METODO
 * Se simula la CAPA EXTERNA —el DOM, chrome.* y fetch— y se ejecuta el
 * content.js de verdad, entero, incluido su arranque. No se reimplementa aca
 * ninguna de sus funciones: eso probaria la copia y no lo que se instala.
 *
 * La respuesta falsa del backend NO esta escrita a mano: la genero panel.py en
 * fixture_panel.json. Asi las dos mitades no pueden separarse sin que esto se
 * entere.
 */
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { JSDOM } from 'jsdom';

// backend/tests/ -> raiz del repositorio
const AQUI = path.dirname(fileURLToPath(import.meta.url));
const RAIZ = path.resolve(AQUI, '..', '..');
const ruta = (...p) => path.join(RAIZ, ...p);

const fixture = JSON.parse(fs.readFileSync(path.join(AQUI, 'fixture_panel.json'), 'utf8'));
const fuente = fs.readFileSync(ruta('cognitive-analysis-ext', 'content.js'), 'utf8');

const fallos = [];
const check = (cond, msg) => {
  console.log((cond ? '  ok    ' : '  FALLA ') + msg);
  if (!cond) fallos.push(msg);
};
const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

// ── dobles ───────────────────────────────────────────────────────────────────
const dom = new JSDOM(
  `<!doctype html><html><body>
     <h1 class="ytd-watch-metadata"><yt-formatted-string>Internet Estaba A Semanas Del Desastre</yt-formatted-string></h1>
     <div id="channel-name"><a>Veritasium en español</a></div>
   </body></html>`,
  { url: 'https://www.youtube.com/watch?v=a62HpQpVBh8', pretendToBeVisual: true,
    runScripts: 'outside-only' });

const w = dom.window;
const pedidos = [];
const guardado = {};

w.chrome = {
  runtime: { id: 'prueba' },
  storage: {
    local: {
      get: (k, cb) => cb({ [k]: guardado[k] }),
      set: (obj) => Object.assign(guardado, obj),
    },
  },
};
w.fetch = (url, opts) => {
  pedidos.push({ url: String(url), metodo: (opts && opts.method) || 'GET' });
  if (String(url).includes('/panel/')) {
    return Promise.resolve({ ok: true, status: 200, json: async () => fixture });
  }
  return Promise.resolve({ ok: true, status: 200, text: async () => 'ok' });
};

// ── ejecutar el content.js real ───────────────────────────────────────────────
// w.Function crea la funcion DENTRO del realm de jsdom, asi que el script
// resuelve document, fetch, chrome y demas contra la ventana simulada. No hace
// falta copiar nada a globalThis — y copiarlo rompia, porque navigator es de
// solo lectura en Node.
const ejecutar = new w.Function(fuente);
ejecutar.call(w);

const panel = () => {
  const host = w.document.getElementById('cogana-panel');
  return host && host.shadowRoot ? host.shadowRoot : null;
};

console.log('\n== el servidor se despierta antes de que haga falta ==');
check(pedidos.some((p) => p.url.endsWith('/health')),
      'se pide /health al cargar la pagina, sin esperar al video');
check(pedidos.filter((p) => p.url.endsWith('/health')).length === 1,
      'una sola vez: el despertar esta limitado, no machaca el servidor');

await dormir(3200);   // DELAY_MS = 2500 antes de pedir el panel

console.log('\n== el panel se dibujo ==');
const sh = panel();
check(!!sh, 'hay panel en el DOM');
const filas = sh ? sh.querySelectorAll('.fila') : [];
check(filas.length === 8, `8 descriptores dibujados (hay ${filas.length})`);

console.log('\n== el formato es corregible ==');
const sel = sh && sh.querySelector('.selfmt');
check(!!sel, 'la etiqueta de formato es un desplegable, no un texto muerto');
check(sel && sel.options.length === 4, `4 formatos elegibles (hay ${sel ? sel.options.length : 0})`);
check(sel && sel.value === 'informativo', 'arranca en el formato que calculo el backend');
check(sel && [...sel.options].some((o) => o.textContent === 'práctico y personal'),
      'los formatos se muestran en castellano');

console.log('\n== la banda de margen ==');
const bandas = sh ? sh.querySelectorAll('.margen') : [];
check(bandas.length === 4,
      `4 bandas: los 5 estratificados menos el que no se mueve (hay ${bandas.length})`);
const anchoCifras = bandas.length ? bandas[0].style.width : '';
check(anchoCifras && parseFloat(anchoCifras) >= 20,
      `la banda de densidad de cifras mide ${anchoCifras}`);

console.log('\n== el percentil 100 no dice "mas que el 100 %" ==');
const textos = [...filas].map((f) => f.textContent.replace(/\s+/g, ' '));
check(!textos.some((t) => t.includes('100 % de los videos')),
      'no aparece "más que el 100 % de los videos comparables"');
check(textos.some((t) => t.includes('Más que todos los videos comparables')),
      'aparece "Más que todos los videos comparables"');

console.log('\n== la procedencia del texto ==');
const nota = sh ? sh.querySelector('.nota').textContent.replace(/\s+/g, ' ') : '';
check(nota.includes('subtítulos automáticos de YouTube'),
      'dice de donde salio el texto, no si estaba guardado');
check(!nota.includes('ya almacenada'), 'ya no dice "transcripción ya almacenada"');
check(nota.includes('La puntuación la insertó el transcriptor'),
      'avisa que el texto es automatico, que es lo que condiciona la lectura');

console.log('\n== corregir el formato cambia la lectura, sin volver a la red ==');
const antes = pedidos.length;
const textoCifrasAntes = [...panel().querySelectorAll('.fila')]
  .find((f) => f.textContent.includes('Densidad de cifras')).textContent;
sel.value = 'entretenimiento';
sel.dispatchEvent(new w.Event('change'));
const sh2 = panel();
const filaCifras = [...sh2.querySelectorAll('.fila')]
  .find((f) => f.textContent.includes('Densidad de cifras'));
check(pedidos.length === antes, 'no se hizo ni un pedido mas: las 4 lecturas ya estaban');
check(textoCifrasAntes.includes('60 %'), `antes decia percentil 60`);
check(filaCifras.textContent.includes('83 %'),
      'ahora dice percentil 83 — el valor medido no cambio, cambio contra quien se compara');
check(sh2.querySelector('.corregido'),
      'se avisa que la correccion es local y no toca la etiqueta del estudio');
check(sh2.querySelector('.corregido').textContent.includes('no cambia la etiqueta del estudio'),
      'y se dice explicitamente por que');
check(guardado.formatos_corregidos &&
      guardado.formatos_corregidos['a62HpQpVBh8'] === 'entretenimiento',
      'la correccion queda guardada en este navegador');

console.log('\n== el panel sigue siendo el mismo producto ==');
const html = sh2.innerHTML;
check(html.includes('No es una calificación'),
      '"No es una calificación" sigue en la interfaz');
check(!/#(4ade80|ef4444|22c55e|dc2626)/i.test(html),
      'no se colo ningun verde ni rojo de semaforo');

// ── segundo escenario: extension nueva contra backend viejo ──────────────────
//
// Pasa de verdad: Render se despliega solo y la extension se recarga a mano, o
// al reves. Durante ese rato la respuesta no trae alternativas, ni
// formatos_posibles, ni transcripcion. El panel tiene que seguir sirviendo, sin
// inventar una banda ni un desplegable vacio.
console.log('\n== respuesta de un backend viejo, sin los campos nuevos ==');
const viejo = JSON.parse(JSON.stringify(fixture));
delete viejo.formatos_posibles;
delete viejo.transcripcion;
viejo.descriptores.forEach((d) => delete d.alternativas);

w.document.getElementById('cogana-panel')?.remove();
w.fetch = (url) => {
  pedidos.push({ url: String(url), metodo: 'GET' });
  if (String(url).includes('/panel/')) {
    return Promise.resolve({ ok: true, status: 200, json: async () => viejo });
  }
  return Promise.resolve({ ok: true, status: 200, text: async () => 'ok' });
};
w.dispatchEvent(new w.Event('yt-navigate-finish'));
await dormir(3200);

const shV = panel();
check(!!shV && shV.querySelectorAll('.fila').length === 8,
      'el panel se dibuja igual, con sus 8 descriptores');
check(shV && shV.querySelectorAll('.margen').length === 0,
      'sin alternativas no se dibuja ninguna banda');
check(shV && !shV.querySelector('.selfmt') && shV.querySelector('.fmt'),
      'sin formatos_posibles vuelve a la etiqueta de texto, no a un desplegable vacio');
check(shV && shV.querySelector('.nota').textContent
        .includes('origen de la transcripción no registrado'),
      'sin procedencia lo dice, en vez de afirmar una fuente que no sabe');
check(shV && shV.querySelector('.nota').textContent.includes('No es una calificación'),
      'y el limite sigue en la interfaz');

console.log();
if (fallos.length) {
  console.log(`FALLARON ${fallos.length} comprobaciones:`);
  fallos.forEach((f) => console.log('  -', f));
  process.exit(1);
}
console.log('todo en verde');

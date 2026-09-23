/* sitio.js — lo común a todas las páginas: la barra, la clave de admin y las
   llamadas al backend de Render.

   La clave se guarda SOLO en este navegador (localStorage) y viaja en la
   cabecera X-Clave-Admin. No da acceso a la base: el backend la compara con
   su variable ADMIN_KEY y recién ahí responde. Sin clave, las páginas de
   participantes (quiz.html con ?t=) funcionan igual: no pasan por acá. */
(function () {
  'use strict';

  var API = 'https://cognitive-analysis-gfpg.onrender.com';
  var LS_CLAVE = 'ca.claveAdmin';

  var PAGINAS = [
    { id: 'inicio', href: 'index.html', txt: 'Inicio' },
    { id: 'dieta', href: 'dieta.html', txt: 'Dieta', admin: true },
    { id: 'responder', href: 'quiz.html', txt: 'Responder' },
    { id: 'generar', href: 'generar.html', txt: 'Generar', admin: true },
  ];

  var CANDADO = '<svg class="sitio-candado" viewBox="0 0 16 16" width="11" height="11" ' +
    'role="img" aria-label="con clave"><path fill="currentColor" d="M4.5 7V5a3.5 3.5 0 0 1 7 0v2H12a1 ' +
    '1 0 0 1 1 1v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1zm1.5 0h4V5a2 2 0 0 0-4 0z"/></svg>';

  var DESPERTANDO = 'Despertando el servidor… Render lo apaga tras 15 minutos sin uso ' +
                    'y tarda hasta un minuto en volver.';

  // localStorage puede no existir o tirar (modo privado, datos bloqueados).
  function leer(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } }
  function escribir(k, v) {
    try {
      if (v == null) window.localStorage.removeItem(k); else window.localStorage.setItem(k, v);
    } catch (e) { /* sin almacenamiento: la clave dura lo que la pestaña */ }
  }
  var claveEnMemoria = null;
  function clave() { return claveEnMemoria || leer(LS_CLAVE) || ''; }
  function guardarClave(k) { claveEnMemoria = k; escribir(LS_CLAVE, k); }
  function olvidarClave() { claveEnMemoria = null; escribir(LS_CLAVE, null); }

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  // ── Barra ──────────────────────────────────────────────────────────────
  // opciones.soloPublicas: en la página de un participante no se muestran las
  // secciones con clave (salvo que este navegador ya la tenga): serían
  // callejones sin salida para quien vino a contestar.
  function nav(activa, opciones) {
    opciones = opciones || {};
    var cont = document.getElementById('sitio-nav');
    if (!cont) return;
    var conClave = !!clave();
    var links = PAGINAS.filter(function (p) {
      return !(opciones.soloPublicas && p.admin && !conClave);
    }).map(function (p) {
      return '<a href="' + p.href + '"' + (p.id === activa ? ' aria-current="page"' : '') + '>' +
             p.txt + (p.admin && !conClave ? CANDADO : '') +
             '</a>';
    }).join('');
    cont.innerHTML =
      '<nav class="sitio-nav" aria-label="Secciones del sitio"><div class="sitio-nav-in">' +
      '<a class="sitio-marca" href="index.html">Cognitive Analysis</a>' +
      '<div class="sitio-links">' + links + '</div>' +
      (conClave ? '<button class="sitio-salir" type="button" title="Borra la clave de este navegador">Olvidar clave</button>' : '') +
      '</div></nav>';
    var salir = cont.querySelector('.sitio-salir');
    if (salir) salir.addEventListener('click', function () {
      olvidarClave();
      location.reload();
    });
  }

  // ── Ventana de la clave ────────────────────────────────────────────────
  function Cancelado() { this.name = 'Cancelado'; this.message = 'Sin clave'; }

  function pedirClave(motivo) {
    return new Promise(function (resolver, rechazar) {
      var fondo = document.createElement('div');
      fondo.className = 'sitio-modal';
      fondo.innerHTML =
        '<form role="dialog" aria-modal="true" aria-labelledby="sitio-clave-t">' +
        '<h2 id="sitio-clave-t">Clave de admin</h2>' +
        '<p>Esta sección muestra tu historial o gasta tu cuota de Gemini. ' +
        'La clave es la variable <code>ADMIN_KEY</code> de Render; queda guardada solo en este navegador.</p>' +
        '<input type="password" autocomplete="current-password" required aria-label="Clave de admin">' +
        '<p class="sitio-error" role="alert">' + esc(motivo || '') + '</p>' +
        '<div class="acciones">' +
        '<button type="button" class="sitio-boton secundario" data-cancelar>Cancelar</button>' +
        '<button type="submit" class="sitio-boton">Entrar</button></div></form>';
      document.body.appendChild(fondo);
      var input = fondo.querySelector('input');
      setTimeout(function () { input.focus(); }, 0);
      fondo.querySelector('form').addEventListener('submit', function (e) {
        e.preventDefault();
        var k = input.value.trim();
        if (!k) return;
        guardarClave(k);
        fondo.remove();
        resolver(k);
      });
      fondo.querySelector('[data-cancelar]').addEventListener('click', function () {
        fondo.remove();
        rechazar(new Cancelado());
      });
    });
  }

  // ── Backend ────────────────────────────────────────────────────────────
  function ErrorApi(status, detalle) {
    this.name = 'ErrorApi'; this.status = status; this.message = detalle;
  }

  function dormir(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  async function detalleDe(r) {
    try { var j = await r.json(); return typeof j.detail === 'string' ? j.detail : null; }
    catch (e) { return null; }
  }

  // Llama a /admin/... con la clave. Si falta o es incorrecta, la pide.
  // Si el servidor está dormido (Render gratuito), reintenta y avisa con
  // opciones.alEsperar() para que la página diga por qué tarda.
  async function api(ruta, opciones) {
    opciones = opciones || {};
    var k = clave() || await pedirClave();
    for (var intento = 0; ; intento++) {
      var r = null;
      var aviso = setTimeout(function () { if (opciones.alEsperar) opciones.alEsperar(DESPERTANDO); }, 4000);
      try {
        var headers = { 'X-Clave-Admin': k };
        if (opciones.body) headers['Content-Type'] = 'application/json';
        r = await fetch(API + ruta, {
          method: opciones.method || 'GET', headers: headers,
          body: opciones.body ? JSON.stringify(opciones.body) : undefined,
        });
      } catch (e) {
        r = null;   // sin respuesta: red caída o servidor arrancando
      } finally {
        clearTimeout(aviso);
      }
      if (r && r.ok) return r.json();
      if (r && r.status === 401) {
        olvidarClave();
        k = await pedirClave('Clave incorrecta. Probá de nuevo.');
        continue;
      }
      if (r) {
        var d = await detalleDe(r);
        // Un 503 CON detalle es nuestro (p. ej. «falta ADMIN_KEY»): no se
        // arregla reintentando. Uno SIN detalle es Render arrancando.
        if (d || [502, 503, 504].indexOf(r.status) < 0) throw new ErrorApi(r.status, d || ('HTTP ' + r.status));
      }
      if (intento >= 7) throw new ErrorApi(0, 'No pude contactar al servidor. Probá de nuevo en un rato.');
      if (opciones.alEsperar) opciones.alEsperar(DESPERTANDO);
      await dormir(Math.min(12000, 2500 * (intento + 1)));
    }
  }

  // Estado de error listo para pintar, con la salida que corresponda.
  function pintarError(nodo, e, reintentar) {
    var sinClave = e && e.name === 'Cancelado';
    nodo.hidden = false;
    nodo.innerHTML = sinClave
      ? '<p>Esta sección necesita la clave de admin.</p>'
      : '<p>' + esc(e && e.message ? e.message : 'Algo falló.') + '</p>';
    var b = document.createElement('button');
    b.className = 'sitio-boton';
    b.type = 'button';
    b.textContent = sinClave ? 'Ingresar la clave' : 'Reintentar';
    b.addEventListener('click', reintentar);
    nodo.appendChild(b);
  }

  window.Sitio = {
    API: API, nav: nav, api: api, clave: clave, olvidarClave: olvidarClave,
    pedirClave: pedirClave, pintarError: pintarError, esc: esc,
    leer: leer, escribir: escribir, DESPERTANDO: DESPERTANDO,
  };
})();

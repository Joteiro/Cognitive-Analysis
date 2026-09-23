/* dieta_vivo.js — carga los datos de la dieta y recién entonces ejecuta el
   dibujo del dashboard.

   dieta.html es la plantilla de siempre (backend/scripts/plantilla_dashboard.html,
   armada con build_dashboard.py --vivo) con su código de dibujo guardado en un
   <script type="text/plain">: el navegador no lo corre al cargar porque todavía
   no hay datos. Acá se piden a /admin/dieta, se dejan en window.DIETA y se
   ejecuta ese mismo código, sin tocarlo. Un solo dashboard que mantener. */
(function () {
  'use strict';
  var carga = document.getElementById('dieta-carga');
  var afuera = document.getElementById('dieta-afuera');

  function hora(iso) {
    var d = new Date(iso);
    return d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
  }

  function avisoAfuera(a, leido) {
    var partes = [];
    if (a.sin_panel) {
      partes.push(a.sin_panel + (a.sin_panel === 1 ? ' tiene' : ' tienen') +
        ' transcripción pero todavía no panel (<code>backfill_panel.py</code>)');
    }
    if (a.sin_transcripcion) {
      partes.push(a.sin_transcripcion + (a.sin_transcripcion === 1 ? ' no tiene' : ' no tienen') +
        ' transcripción (<code>enrich_local.py</code>)');
    }
    var texto = '<b>En vivo</b>, leído a las ' + hora(leido) + '.';
    if (partes.length) {
      var n = (a.sin_panel || 0) + (a.sin_transcripcion || 0);
      texto += ' Quedan afuera ' + n + ' video' + (n === 1 ? '' : 's') + ' vistos: ' +
               partes.join('; ') + '.';
    }
    afuera.innerHTML = '<div>' + texto + '</div>';
    afuera.hidden = false;
  }

  async function cargar() {
    carga.hidden = false;
    carga.textContent = 'Cargando la dieta…';
    var d;
    try {
      d = await Sitio.api('/admin/dieta', { alEsperar: function (m) { carga.textContent = m; } });
    } catch (e) {
      Sitio.pintarError(carga, e, cargar);
      return;
    }
    Sitio.nav('dieta');   // ya hay clave: la barra deja de mostrar candados
    if (!d.filas || !d.filas.length) {
      carga.textContent = 'Todavía no hay videos medidos con fecha de visionado.';
      return;
    }
    window.DIETA = d;
    avisoAfuera(d.afuera || {}, d.leido_at);
    carga.hidden = true;
    // Visible ANTES de dibujar: los gráficos miden el ancho de su contenedor.
    document.querySelector('.viz-root').hidden = false;
    var s = document.createElement('script');
    s.textContent = document.getElementById('dieta-codigo').textContent;
    document.body.appendChild(s);
  }

  Sitio.nav('dieta');
  cargar();
})();

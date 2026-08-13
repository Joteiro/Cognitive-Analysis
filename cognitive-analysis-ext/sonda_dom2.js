/* ============================================================================
   sonda_dom2.js — ULTIMO intento del camino navegador.

   POR QUE SE VUELVE A INTENTAR ALGO QUE YA FALLO
   La vez pasada dije que paraba, y la razon era buena: Supadata resolvia el
   problema y no valia la pena pelear con el DOM. Esa razon se cayo — el plan
   de Supadata se agoto con una sola llamada de 134 creditos. Cuando cambia lo
   que hay del otro lado de la balanza, cambia la decision.

   QUE FALLO Y POR QUE
   La sonda anterior encontro 7 botones "Show transcript" y les hizo `.click()`.
   No paso nada. `.click()` de JavaScript dispara UN evento sintetico; los
   componentes de YouTube escuchan la secuencia real de un mouse
   (pointerover -> pointerdown -> pointerup -> click) y descartan lo demas.
   Ademas se clickeaban botones invisibles: de los 7, la mayoria son copias
   ocultas del maquetado.

   QUE CAMBIA ACA
   1. Se descartan los botones que no estan visibles.
   2. Se emite la secuencia completa de eventos de puntero, con coordenadas
      reales tomadas de la posicion del boton en pantalla.
   3. Se baja hasta el boton mas interno, que es el que suele tener el oyente.

   Si esto tampoco anda, el camino del navegador esta cerrado de verdad y la
   respuesta es el panel sobre los ~500 videos ya enriquecidos.

   USO: F12 -> Console. Pegar, Enter, esperar el "=== FIN ===".
   ========================================================================= */

(async () => {
  const P = (...a) => console.log("%c[dom2]", "color:#0aa;font-weight:bold", ...a);
  const ok = (m) => console.log("%c  OK  %c " + m, "background:#0a0;color:#fff", "");
  const no = (m) => console.log("%c FALLA %c " + m, "background:#c00;color:#fff", "");
  const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

  const visible = (el) => {
    if (!el || !el.offsetParent) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  // Un mouse real emite una secuencia, no un evento suelto. Los componentes de
  // YouTube escuchan esa secuencia; un .click() pelado lo ignoran.
  const clickReal = (el) => {
    el.scrollIntoView({ block: "center" });
    const r = el.getBoundingClientRect();
    const base = {
      bubbles: true, cancelable: true, composed: true, view: window,
      clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
      pointerId: 1, pointerType: "mouse", isPrimary: true, button: 0,
    };
    for (const [Tipo, nombre, botones] of [
      [PointerEvent, "pointerover", 0], [PointerEvent, "pointerenter", 0],
      [MouseEvent, "mouseover", 0], [PointerEvent, "pointerdown", 1],
      [MouseEvent, "mousedown", 1], [PointerEvent, "pointerup", 0],
      [MouseEvent, "mouseup", 0], [MouseEvent, "click", 0],
    ]) {
      try { el.dispatchEvent(new Tipo(nombre, { ...base, buttons: botones })); }
      catch (e) { /* algun tipo de evento no soportado: seguir */ }
    }
  };

  const leer = () => {
    const filas = document.querySelectorAll("ytd-transcript-segment-renderer");
    if (!filas.length) return null;
    const texto = [...filas]
      .map((f) => (f.querySelector(".segment-text") || f).textContent.trim())
      .join(" ").replace(/\s+/g, " ").trim();
    return { filas: filas.length, texto };
  };

  const reportar = (r, via) => {
    const pal = r.texto.split(/\s+/).length;
    ok(`${via}: ${r.filas} renglones, ${pal} palabras`);
    console.log("Muestra:\n" + r.texto.slice(0, 400) + "…");
    console.log("%c=== FIN === el DOM SIRVE", "background:#0a0;color:#fff;font-weight:bold");
    console.log(JSON.stringify({ via, renglones: r.filas, palabras: pal }, null, 1));
  };

  let r = leer();
  if (r) return reportar(r, "ya estaba abierto");

  P("despliego la descripcion");
  const exp = document.querySelector("#expand, tp-yt-paper-button#expand");
  if (exp && visible(exp)) clickReal(exp);
  await dormir(1000);
  r = leer();
  if (r) return reportar(r, "al desplegar la descripcion");

  const todos = [...document.querySelectorAll("button, yt-button-shape, ytd-button-renderer, a, tp-yt-paper-item")]
    .filter((b) => {
      const t = (b.textContent || "").trim();
      return t.length < 40 && /transcripci|transcript/i.test(t);
    });
  const vis = todos.filter(visible);
  P(`${todos.length} candidatos, ${vis.length} visibles`);
  if (!vis.length && todos.length) {
    P("ninguno visible: los 7 de la vez pasada eran copias ocultas del maquetado");
  }

  for (let i = 0; i < vis.length; i++) {
    const el = vis[i];
    // el oyente suele estar en el boton mas interno, no en el contenedor
    const objetivo = el.querySelector("button") || el;
    P(`clickeo ${i + 1}/${vis.length}: "${(el.textContent || "").trim().slice(0, 30)}" ` +
      `<${objetivo.tagName.toLowerCase()}>`);
    clickReal(objetivo);
    for (let k = 0; k < 8; k++) {
      await dormir(500);
      r = leer();
      if (r) return reportar(r, `boton visible ${i + 1}, eventos de puntero`);
    }
    P("  nada tras 4 s");
  }

  no("Tampoco con eventos de puntero reales.");
  console.log("Estado del DOM:", {
    engagement_panels: document.querySelectorAll("ytd-engagement-panel-section-list-renderer").length,
    transcript_renderer: document.querySelectorAll("ytd-transcript-renderer").length,
    candidatos_totales: todos.length, candidatos_visibles: vis.length,
  });
  console.log(
    "%cPRUEBA MANUAL (30 segundos, decisiva):%c abri vos mismo 'Show transcript' " +
    "con el mouse, y cuando veas los renglones pega esto:\n\n" +
    "document.querySelectorAll('ytd-transcript-segment-renderer').length\n\n" +
    "Si eso da un numero mayor a cero, el texto ES legible desde el DOM y el " +
    "problema es solo abrir el panel — lo cual se puede resolver pidiendole al " +
    "usuario que lo abra una vez. Si da 0, el panel usa shadow DOM cerrado y " +
    "no hay nada que hacer.",
    "font-weight:bold", "");
  console.log("%c=== FIN === el DOM no se abre solo", "background:#c00;color:#fff;font-weight:bold");
})();

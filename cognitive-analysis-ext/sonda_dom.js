/* ============================================================================
   sonda_dom.js — ULTIMA SONDA. Solo la via D.

   Por que se abandona la via C:
   get_transcript contesta FAILED_PRECONDITION. El servidor exige algo del
   estado de sesion que no le estamos dando, y averiguar que es significa
   pelear contra un sistema antiabuso que Google mantiene activamente. Aunque
   se destrabe hoy, puede romperse antes de la defensa. No es buena inversion
   con el plazo encima.

   La via D no pelea con nadie: abre el panel de transcripcion como lo abriria
   una persona y lee los renglones. Es fragil por maquetado —si YouTube cambia
   el HTML hay que ajustar un selector— pero no hay nada del otro lado tratando
   de impedirlo.

   Esta sonda imprime CADA PASO a medida que ocurre, asi que aunque cortes el
   pegado antes de tiempo, lo que hayas copiado ya dice algo.

   USO: F12 -> Console. Pegar, Enter, y esperar a ver "=== FIN ===".
   ========================================================================= */

(async () => {
  const P = (...a) => console.log("%c[dom]", "color:#0aa;font-weight:bold", ...a);
  const ok = (m) => console.log("%c  OK  %c " + m, "background:#0a0;color:#fff", "");
  const no = (m) => console.log("%c FALLA %c " + m, "background:#c00;color:#fff", "");
  const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

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
    console.log("Muestra:\n" + r.texto.slice(0, 300) + "…");
    console.log("%c=== FIN === via D SIRVE", "background:#0a0;color:#fff;font-weight:bold");
    return { via, renglones: r.filas, palabras: pal, muestra: r.texto.slice(0, 200) };
  };

  P("paso 1: ¿el panel ya esta abierto?");
  let r = leer();
  if (r) return reportar(r, "ya abierto");
  P("  no");

  P("paso 2: despliego la descripcion");
  document.querySelector("#expand, tp-yt-paper-button#expand")?.click();
  await dormir(900);
  r = leer();
  if (r) return reportar(r, "tras desplegar descripcion");
  P("  sigue sin panel");

  P("paso 3: busco el boton de transcripcion");
  const cand = [...document.querySelectorAll("button, yt-button-shape, ytd-button-renderer, a")]
    .filter((b) => {
      const t = (b.textContent || "").trim();
      return t.length < 40 && /transcripci|transcript/i.test(t);
    });
  P(`  ${cand.length} candidatos:`, cand.map((b) => (b.textContent || "").trim().slice(0, 30)));

  for (let i = 0; i < cand.length; i++) {
    P(`paso 4.${i + 1}: clickeo "${(cand[i].textContent || "").trim().slice(0, 30)}"`);
    try { cand[i].click(); } catch (e) { P("  no se pudo clickear:", e.message); continue; }
    for (let k = 0; k < 6; k++) {
      await dormir(500);
      r = leer();
      if (r) return reportar(r, `boton ${i + 1}`);
    }
    P("  sin resultado tras 3 s");
  }

  // Ultimo recurso: el menu de tres puntos debajo del video.
  P("paso 5: pruebo el menu de tres puntos");
  const masBtn = document.querySelector(
    "#actions ytd-menu-renderer yt-icon-button, #top-level-buttons-computed ytd-menu-renderer button");
  if (masBtn) {
    masBtn.click();
    await dormir(900);
    const items = [...document.querySelectorAll("tp-yt-paper-item, ytd-menu-service-item-renderer")]
      .filter((b) => /transcripci|transcript/i.test(b.textContent || ""));
    P(`  ${items.length} items en el menu`);
    if (items[0]) {
      items[0].click();
      for (let k = 0; k < 8; k++) {
        await dormir(500);
        r = leer();
        if (r) return reportar(r, "menu tres puntos");
      }
    }
    document.body.click();  // cerrar el menu
  } else {
    P("  no encontre el boton de menu");
  }

  no("Ninguna via del DOM funciono en este video.");
  console.log("Copiame tambien esto, ayuda a saber si el panel existe siquiera:");
  console.log({
    hay_engagement_panels: document.querySelectorAll("ytd-engagement-panel-section-list-renderer").length,
    hay_transcript_renderer: document.querySelectorAll("ytd-transcript-renderer").length,
    idioma_interfaz: document.documentElement.lang,
  });
  console.log("%c=== FIN === via D NO sirve", "background:#c00;color:#fff;font-weight:bold");
})();

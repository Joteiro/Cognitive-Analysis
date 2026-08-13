/* ============================================================================
   sonda_transcripcion3.js
   Tercera sonda. Estado de lo aprendido:
     1. Las pistas de subtitulos existen y se listan bien.       (sonda 1)
     2. `timedtext` devuelve vacio: falta el token de origen.    (sonda 1)
     3. get_transcript encuentra el `params` pero da HTTP 400.   (sonda 2)

   El 400 es casi seguro culpa mia: le mande un `context` armado a mano con dos
   campos. Innertube quiere el contexto completo del cliente —idioma, region,
   visitorData, capacidades— y la pagina YA lo tiene cargado en ytcfg. Es el
   mismo criterio que uso para el `params`: leerlo de la pagina en vez de
   inventarlo. Ademas se agregan las cabeceras que manda el propio YouTube.

   Y sobre todo: si vuelve a fallar, ESTA VEZ IMPRIME EL CUERPO DEL ERROR.
   Un 400 sin leer el mensaje es no haber medido nada.

   USO: F12 -> Console, mismo video. Pegar y Enter. Esperar ~10 segundos.
   ========================================================================= */

(async () => {
  const log = (...a) => console.log("%c[sonda3]", "color:#0aa;font-weight:bold", ...a);
  const ok = (m) => console.log("%c  OK  %c " + m, "background:#0a0;color:#fff", "");
  const no = (m) => console.log("%c FALLA %c " + m, "background:#c00;color:#fff", "");
  const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

  const vid = new URLSearchParams(location.search).get("v");
  const R = { video: vid, C: {}, D: {} };

  const buscar = (obj, clave, prof = 0) => {
    if (!obj || typeof obj !== "object" || prof > 30) return null;
    if (clave in obj) return obj[clave];
    for (const v of Object.values(obj)) {
      const r = buscar(v, clave, prof + 1);
      if (r) return r;
    }
    return null;
  };

  const textoDe = (j) => {
    const seg = [];
    const rec = (o, p = 0) => {
      if (!o || typeof o !== "object" || p > 40) return;
      if (o.transcriptSegmentRenderer) {
        const s = o.transcriptSegmentRenderer.snippet;
        const t = s?.simpleText || (s?.runs || []).map((r) => r.text).join("");
        if (t) seg.push(t);
      }
      for (const v of Object.values(o)) rec(v, p + 1);
    };
    rec(j);
    return { seg, texto: seg.join(" ").replace(/\s+/g, " ").trim() };
  };

  // ---------------------------------------------------------------- VIA C+
  log("--- VIA C+: get_transcript con el contexto REAL de la pagina ---");
  const cfg = window.ytcfg?.data_ || {};
  const key = cfg.INNERTUBE_API_KEY;
  const ctx = cfg.INNERTUBE_CONTEXT;
  log("contexto de la pagina:", ctx ? "presente" : "AUSENTE",
      "| cliente:", ctx?.client?.clientName, ctx?.client?.clientVersion,
      "| hl/gl:", ctx?.client?.hl, ctx?.client?.gl);

  const params = buscar(window.ytInitialData, "getTranscriptEndpoint")?.params;
  if (!params) {
    no("C+: sin params. Abri 'Mostrar transcripcion' a mano y volve a correr.");
    R.C = { params: false };
  } else if (!ctx) {
    no("C+: ytcfg no expone INNERTUBE_CONTEXT en esta pagina.");
    R.C = { params: true, contexto: false };
  } else {
    // Se prueban dos formas del cuerpo: el contexto tal cual, y el contexto con
    // el idioma forzado a espanol por si la pista se elige por locale.
    const intentos = [
      { nombre: "contexto tal cual", body: { context: ctx, params } },
      { nombre: "contexto con hl=es", body: { context: { ...ctx, client: { ...ctx.client, hl: "es" } }, params } },
    ];
    for (const it of intentos) {
      try {
        const resp = await fetch(`/youtubei/v1/get_transcript?key=${key}&prettyPrint=false`, {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            "X-YouTube-Client-Name": String(cfg.INNERTUBE_CONTEXT_CLIENT_NAME ?? 1),
            "X-YouTube-Client-Version": ctx.client.clientVersion,
            ...(ctx.client.visitorData ? { "X-Goog-Visitor-Id": ctx.client.visitorData } : {}),
          },
          body: JSON.stringify(it.body),
        });
        log(`C+ [${it.nombre}] HTTP ${resp.status}`);
        const crudo = await resp.text();
        if (!resp.ok) {
          // ESTO es lo que faltaba en la sonda anterior
          no(`C+ [${it.nombre}] cuerpo del error: ${crudo.slice(0, 400)}`);
          R.C[it.nombre] = { http: resp.status, error: crudo.slice(0, 300) };
          continue;
        }
        const { seg, texto } = textoDe(JSON.parse(crudo));
        const pal = texto ? texto.split(/\s+/).length : 0;
        if (pal > 20) {
          ok(`C+ [${it.nombre}] ${seg.length} renglones, ${pal} palabras — SIRVE`);
          console.log("Muestra:\n" + texto.slice(0, 300) + "…");
          R.C[it.nombre] = { http: 200, renglones: seg.length, palabras: pal,
                             muestra: texto.slice(0, 200) };
          break;
        }
        no(`C+ [${it.nombre}] 200 pero ${pal} palabras`);
        R.C[it.nombre] = { http: 200, palabras: pal };
      } catch (e) {
        no(`C+ [${it.nombre}] excepcion: ${e.message}`);
        R.C[it.nombre] = { error: e.message };
      }
    }
  }

  // ---------------------------------------------------------------- VIA D
  // La sonda anterior encontro 7 botones candidatos y se corto ahi. Aca se
  // reintenta con mas paciencia y se reporta que paso con cada uno.
  log("--- VIA D: panel de transcripcion en el DOM ---");
  try {
    const leer = () => {
      const filas = document.querySelectorAll("ytd-transcript-segment-renderer");
      if (!filas.length) return null;
      const t = [...filas]
        .map((f) => f.querySelector(".segment-text")?.textContent?.trim() || "")
        .join(" ").replace(/\s+/g, " ").trim();
      return { filas: filas.length, texto: t };
    };

    let r = leer();
    if (!r) {
      document.querySelector("#expand, tp-yt-paper-button#expand")?.click();
      await dormir(900);
      const cand = [...document.querySelectorAll("button, yt-button-shape, ytd-button-renderer")]
        .filter((b) => /transcripci|transcript/i.test(b.textContent || ""));
      log(`D: ${cand.length} botones candidatos; los clickeo de a uno`);
      for (const b of cand) {
        b.click();
        for (let i = 0; i < 8 && !r; i++) { await dormir(500); r = leer(); }
        if (r) break;
      }
    }
    if (!r) {
      no("D: no aparecieron renglones");
      R.D = { renglones: 0 };
    } else {
      const pal = r.texto.split(/\s+/).length;
      ok(`D: ${r.filas} renglones, ${pal} palabras`);
      console.log("Muestra:\n" + r.texto.slice(0, 300) + "…");
      R.D = { renglones: r.filas, palabras: pal, muestra: r.texto.slice(0, 200) };
    }
  } catch (e) {
    no("D: excepcion -> " + e.message);
    R.D = { error: e.message };
  }

  console.log("%c\n=========== VEREDICTO ===========", "font-weight:bold");
  const cOk = Object.values(R.C).some((v) => v && v.palabras > 20);
  if (cOk) ok("VIA C sirve con el contexto real. Es la buena.");
  else if (R.D.palabras > 20) no("Solo la VIA D (DOM). Se puede, pero es fragil.");
  else no("Ninguna. Se cierra el camino del navegador.");
  console.log("Copiame esto entero:");
  console.log(JSON.stringify(R, null, 1));
})();

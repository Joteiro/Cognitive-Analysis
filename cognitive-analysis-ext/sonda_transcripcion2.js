/* ============================================================================
   sonda_transcripcion2.js
   Segunda sonda. La primera dejo claro que:
     - las pistas de subtitulos EXISTEN y se pueden listar por las dos vias
     - pero bajar el texto de `timedtext` devuelve 200 con cuerpo VACIO

   Es el bloqueo por falta de token de origen: hace un par de anios YouTube
   exige un parametro extra en esa URL y, si no esta, contesta vacio en vez de
   dar error. Pero el reproductor sigue mostrando la transcripcion, asi que el
   texto es alcanzable por otra puerta. Esta sonda prueba las dos que quedan.

   VIA C — innertube get_transcript
     Es el endpoint que usa el propio boton "Mostrar transcripcion". En vez de
     construir a mano el parametro codificado (fragil y mal documentado), se lo
     LEE de la pagina: ytInitialData ya lo trae en el panel de transcripcion.
     Si anda, es la via limpia: JSON, sin tocar la interfaz.

   VIA D — leer el panel del DOM
     Abrir la transcripcion como la abre un humano y leer los renglones. Feo,
     visible, y se rompe cuando YouTube cambia el maquetado. Es el plan C real.

   USO: F12 -> Console, sobre un video con subtitulos. Pegar y Enter.
   ========================================================================= */

(async () => {
  const log = (...a) => console.log("%c[sonda2]", "color:#0aa;font-weight:bold", ...a);
  const ok = (m) => console.log("%c  OK  %c " + m, "background:#0a0;color:#fff", "");
  const no = (m) => console.log("%c FALLA %c " + m, "background:#c00;color:#fff", "");
  const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

  const vid = new URLSearchParams(location.search).get("v");
  if (!vid) return no("Abri un video (/watch?v=...) y volve a intentar.");
  log("video:", vid);
  const R = { video: vid, C: {}, D: {} };

  // Busca recursivamente la primera clave con ese nombre en un objeto grande.
  const buscar = (obj, clave, prof = 0) => {
    if (!obj || typeof obj !== "object" || prof > 30) return null;
    if (clave in obj) return obj[clave];
    for (const v of Object.values(obj)) {
      const r = buscar(v, clave, prof + 1);
      if (r) return r;
    }
    return null;
  };

  // ---------------------------------------------------------------- VIA C
  log("--- VIA C: innertube get_transcript ---");
  try {
    const cfg = window.ytcfg?.data_ || {};
    const key = cfg.INNERTUBE_API_KEY;
    const ver = cfg.INNERTUBE_CLIENT_VERSION;
    log("C: api key", key ? "presente" : "AUSENTE", "| client version", ver || "AUSENTE");

    const datos = window.ytInitialData;
    const ep = datos ? buscar(datos, "getTranscriptEndpoint") : null;
    const params = ep?.params;
    if (!params) {
      no("C: no aparece getTranscriptEndpoint en ytInitialData. " +
         "Puede que el panel de transcripcion no este cargado todavia: abri " +
         "'Mostrar transcripcion' a mano y volve a correr la sonda.");
      R.C = { params: false };
    } else {
      ok("C: params encontrado (" + params.slice(0, 24) + "…)");
      const resp = await fetch(
        `/youtubei/v1/get_transcript${key ? "?key=" + key : ""}`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            context: { client: { clientName: "WEB", clientVersion: ver || "2.20240101.00.00" } },
            params,
          }),
        }
      );
      log("C: HTTP", resp.status);
      if (!resp.ok) {
        no("C: HTTP " + resp.status);
        R.C = { params: true, http: resp.status };
      } else {
        const j = await resp.json();
        // los renglones vienen como transcriptSegmentRenderer, anidados hondo
        const seg = [];
        const recorrer = (o, prof = 0) => {
          if (!o || typeof o !== "object" || prof > 40) return;
          if (o.transcriptSegmentRenderer) {
            const s = o.transcriptSegmentRenderer.snippet;
            const t = s?.simpleText || (s?.runs || []).map((r) => r.text).join("");
            if (t) seg.push(t);
          }
          for (const v of Object.values(o)) recorrer(v, prof + 1);
        };
        recorrer(j);
        const texto = seg.join(" ").replace(/\s+/g, " ").trim();
        const pal = texto ? texto.split(/\s+/).length : 0;
        if (pal > 20) {
          ok(`C: ${seg.length} renglones, ${pal} palabras — ESTA ES LA VIA LIMPIA`);
          console.log("Primeras 300 letras:\n" + texto.slice(0, 300) + "…");
          R.C = { params: true, http: 200, renglones: seg.length, palabras: pal,
                  muestra: texto.slice(0, 200) };
        } else {
          no(`C: respondio 200 pero solo ${pal} palabras`);
          R.C = { params: true, http: 200, palabras: pal };
        }
      }
    }
  } catch (e) {
    no("C: excepcion -> " + e.message);
    R.C = { error: e.message };
  }

  // ---------------------------------------------------------------- VIA D
  log("--- VIA D: leer el panel del DOM ---");
  try {
    let filas = document.querySelectorAll("ytd-transcript-segment-renderer");
    if (!filas.length) {
      log("D: el panel no esta abierto, intento abrirlo…");
      // el boton vive en la descripcion expandida; hay varios maquetados
      document.querySelector("#expand, tp-yt-paper-button#expand")?.click();
      await dormir(700);
      const cand = [...document.querySelectorAll("button, yt-button-shape, ytd-button-renderer")]
        .filter((b) => /transcripci|transcript/i.test(b.textContent || ""));
      log("D: botones candidatos:", cand.length);
      cand[0]?.click();
      for (let i = 0; i < 12 && !filas.length; i++) {
        await dormir(500);
        filas = document.querySelectorAll("ytd-transcript-segment-renderer");
      }
    }
    if (!filas.length) {
      no("D: no aparecieron renglones de transcripcion en el DOM");
      R.D = { renglones: 0 };
    } else {
      const texto = [...filas]
        .map((f) => f.querySelector(".segment-text")?.textContent?.trim() || "")
        .join(" ").replace(/\s+/g, " ").trim();
      const pal = texto ? texto.split(/\s+/).length : 0;
      ok(`D: ${filas.length} renglones, ${pal} palabras`);
      console.log("Primeras 300 letras:\n" + texto.slice(0, 300) + "…");
      R.D = { renglones: filas.length, palabras: pal, muestra: texto.slice(0, 200) };
    }
  } catch (e) {
    no("D: excepcion -> " + e.message);
    R.D = { error: e.message };
  }

  // ---------------------------------------------------------------- veredicto
  console.log("%c\n=========== VEREDICTO ===========", "font-weight:bold");
  if (R.C.palabras > 20) {
    ok("VIA C sirve. Es la buena: JSON, sin tocar la interfaz, y trae los mismos " +
       "subtitulos de YouTube con los que se construyo la escala.");
  } else if (R.D.palabras > 20) {
    no("VIA C no; VIA D si. Se puede hacer, pero leyendo el DOM: mas fragil, y " +
       "hay que abrir el panel de transcripcion en cada video.");
  } else {
    no("Ninguna de las dos. Ahi el camino del navegador se cierra y toca " +
       "Supadata con experimento de calibracion, o declararlo trabajo futuro.");
  }
  console.log("Copiame esto entero:");
  console.log(JSON.stringify(R, null, 1));
})();

/* ============================================================================
   sonda_transcripcion.js
   Prueba si se puede sacar la transcripcion de un video DESDE EL NAVEGADOR.

   POR QUE ESTA PRUEBA VA PRIMERO
   Todo el panel depende de esto. Si el navegador puede leer los subtitulos, se
   elimina de raiz el cuello de botella de los 10 videos por hora y el bloqueo
   por IP de datacenter, porque la peticion sale de la sesion del usuario. Si no
   puede, no tiene sentido construir nada alrededor y hay que cambiar de plan.
   Cinco minutos de prueba antes que una semana de codigo.

   COMO USARLA
   1. Abri un video de YouTube en espanol que tenga subtitulos.
   2. F12 -> pestana "Console".
   3. Pega TODO este archivo y Enter.
   4. Pegame lo que imprima.

   Prueba las dos vias por separado, porque no son equivalentes:
     A. la variable global de la pagina  -> anda en la consola, NO en un
        content script (corre en un mundo aislado y no ve las variables de la
        pagina). Sirve para saber si el dato existe.
     B. bajar el HTML y extraerlo       -> es la que va a usar la extension.
   Si A anda y B no, hay que inyectar un script en el contexto de la pagina.
   ========================================================================= */

(async () => {
  const log = (...a) => console.log("%c[sonda]", "color:#0aa;font-weight:bold", ...a);
  const ok = (m) => console.log("%c  OK  %c " + m, "background:#0a0;color:#fff", "");
  const no = (m) => console.log("%c FALLA %c " + m, "background:#c00;color:#fff", "");

  const vid = new URLSearchParams(location.search).get("v");
  if (!vid) return no("Esto no es una pagina de video (/watch?v=...). Abri un video y volve a intentar.");
  log("video:", vid);

  const resultado = { video: vid, A: {}, B: {}, pista: null, texto: null };

  // ---------- helpers ----------
  const pistasDe = (pr) =>
    pr?.captions?.playerCaptionsTracklistRenderer?.captionTracks || null;

  const describir = (pistas) =>
    pistas.map((t) => ({
      lang: t.languageCode,
      tipo: t.kind === "asr" ? "automatica" : "manual",
      nombre: t.name?.simpleText || t.name?.runs?.[0]?.text || "",
    }));

  // ---------- VIA A: variable global de la pagina ----------
  log("--- VIA A: variable global de la pagina ---");
  try {
    const pr = window.ytInitialPlayerResponse;
    if (!pr) {
      no("A: no existe window.ytInitialPlayerResponse");
      resultado.A = { existe: false };
    } else {
      const pistas = pistasDe(pr);
      if (!pistas?.length) {
        no("A: el playerResponse esta pero no trae captionTracks (video sin subtitulos)");
        resultado.A = { existe: true, pistas: 0 };
      } else {
        ok(`A: ${pistas.length} pista(s) de subtitulos`);
        console.table(describir(pistas));
        resultado.A = { existe: true, pistas: pistas.length, detalle: describir(pistas) };
        resultado.pista = pistas;
      }
    }
  } catch (e) {
    no("A: excepcion -> " + e.message);
    resultado.A = { error: e.message };
  }

  // ---------- VIA B: bajar el HTML y extraer ----------
  // Es la que necesita la extension: un content script no ve las variables de
  // la pagina, pero si puede hacer fetch al mismo origen con las cookies.
  log("--- VIA B: fetch del HTML + extraccion ---");
  try {
    const r = await fetch(location.href, { credentials: "include" });
    const html = await r.text();
    log("B: HTML descargado,", (html.length / 1024).toFixed(0), "KB");

    let pr = null;
    // El JSON esta embebido en un <script>. Se corta por el cierre conocido en
    // vez de intentar una regex glotona, que se come media pagina.
    const marca = "ytInitialPlayerResponse = ";
    const i = html.indexOf(marca);
    if (i === -1) {
      no("B: no aparece 'ytInitialPlayerResponse' en el HTML");
    } else {
      // recorre contando llaves hasta cerrar el objeto
      const desde = html.indexOf("{", i);
      let prof = 0, fin = -1, enStr = false, esc = false;
      for (let j = desde; j < html.length; j++) {
        const c = html[j];
        if (esc) { esc = false; continue; }
        if (c === "\\") { esc = true; continue; }
        if (c === '"') { enStr = !enStr; continue; }
        if (enStr) continue;
        if (c === "{") prof++;
        else if (c === "}") { prof--; if (prof === 0) { fin = j + 1; break; } }
      }
      if (fin === -1) {
        no("B: no se pudo cerrar el objeto JSON");
      } else {
        pr = JSON.parse(html.slice(desde, fin));
        const pistas = pistasDe(pr);
        if (!pistas?.length) {
          no("B: playerResponse extraido pero sin captionTracks");
          resultado.B = { extraido: true, pistas: 0 };
        } else {
          ok(`B: ${pistas.length} pista(s) — ESTA ES LA VIA QUE USARIA LA EXTENSION`);
          console.table(describir(pistas));
          resultado.B = { extraido: true, pistas: pistas.length, detalle: describir(pistas) };
          resultado.pista = resultado.pista || pistas;
        }
      }
    }
  } catch (e) {
    no("B: excepcion -> " + e.message);
    resultado.B = { error: e.message };
  }

  // ---------- BAJAR EL TEXTO ----------
  log("--- Descarga del texto de la pista ---");
  if (!resultado.pista) {
    no("Sin pistas por ninguna via: no se puede probar la descarga.");
    console.log(resultado);
    return;
  }

  // preferencia: espanol manual > espanol automatica > la primera que haya
  const pref =
    resultado.pista.find((t) => t.languageCode?.startsWith("es") && t.kind !== "asr") ||
    resultado.pista.find((t) => t.languageCode?.startsWith("es")) ||
    resultado.pista[0];
  log("pista elegida:", pref.languageCode, pref.kind === "asr" ? "(automatica)" : "(manual)");

  for (const fmt of ["json3", "srv3", ""]) {
    const url = pref.baseUrl + (fmt ? "&fmt=" + fmt : "");
    try {
      const r = await fetch(url, { credentials: "include" });
      if (!r.ok) { no(`fmt=${fmt || "(defecto)"} -> HTTP ${r.status}`); continue; }
      const cuerpo = await r.text();
      if (!cuerpo.trim()) { no(`fmt=${fmt || "(defecto)"} -> respuesta vacia`); continue; }

      let texto = "";
      if (fmt === "json3") {
        const j = JSON.parse(cuerpo);
        texto = (j.events || [])
          .flatMap((e) => (e.segs || []).map((s) => s.utf8))
          .join("")
          .replace(/\n/g, " ");
      } else {
        texto = cuerpo.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
      }
      texto = texto.trim();
      const palabras = texto ? texto.split(/\s+/).length : 0;

      if (palabras > 20) {
        ok(`fmt=${fmt || "(defecto)"} -> ${palabras} palabras`);
        console.log("%cPrimeras 300 letras:", "font-weight:bold");
        console.log(texto.slice(0, 300) + "…");
        resultado.texto = { fmt: fmt || "defecto", palabras, muestra: texto.slice(0, 300) };
        break;
      }
      no(`fmt=${fmt || "(defecto)"} -> solo ${palabras} palabras`);
    } catch (e) {
      no(`fmt=${fmt || "(defecto)"} -> ${e.message}`);
    }
  }

  // ---------- VEREDICTO ----------
  console.log("%c\n=========== VEREDICTO ===========", "font-weight:bold");
  const viaB = resultado.B.pistas > 0;
  const hayTexto = !!resultado.texto;
  if (viaB && hayTexto) {
    ok("El plan del panel es viable: la extension puede conseguir la transcripcion sola.");
  } else if (hayTexto && !viaB) {
    no("El texto se baja, pero la via B fallo. La extension va a necesitar " +
       "inyectar un script en el contexto de la pagina. Es mas codigo pero se puede.");
  } else {
    no("No se pudo obtener el texto. Hay que replantear: panel solo para videos " +
       "ya enriquecidos, o declararlo trabajo futuro.");
  }
  console.log("Copiame esto entero:");
  console.log(JSON.stringify(resultado, null, 1));
})();

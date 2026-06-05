// ─── CONFIG ───────────────────────────────────────────────────────────────────
// Cambiá esta URL por la de Render una vez que hagas el deploy:
// Ejemplo: 'https://cognitive-analysis-api.onrender.com'
const API_BASE      = 'https://TU-APP.onrender.com';
const BACKEND_URL   = `${API_BASE}/videos`;
const SCORE_URL     = `${API_BASE}/videos/by-youtube`;
const DELAY_MS      = 2500;
const POLL_INTERVAL = 4000;   // ms entre intentos (más largo para tolerar cold start)
const POLL_MAX      = 20;     // intentos máximos (~80 seg — cubre el cold start de Render)

// ─── COLORES POR LETRA ────────────────────────────────────────────────────────
const GRADE_COLORS = {
  A: { bg: '#16a34a', text: '#fff' },
  B: { bg: '#2563eb', text: '#fff' },
  C: { bg: '#d97706', text: '#fff' },
  D: { bg: '#ea580c', text: '#fff' },
  E: { bg: '#dc2626', text: '#fff' },
};

// ─── BADGE ────────────────────────────────────────────────────────────────────
function removeBadge() {
  document.getElementById('cogana-badge')?.remove();
}

function showBadge(scoreData) {
  removeBadge();

  const { score_letter, score_numeric, score_labels } = scoreData;
  if (!score_letter) return;

  const colors = GRADE_COLORS[score_letter] || { bg: '#6b7280', text: '#fff' };
  const labels = (score_labels || []).join('  ·  ');

  const badge = document.createElement('div');
  badge.id = 'cogana-badge';
  badge.style.cssText = `
    position: fixed;
    bottom: 24px;
    right: 24px;
    z-index: 9999;
    background: ${colors.bg};
    color: ${colors.text};
    border-radius: 12px;
    padding: 10px 16px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 13px;
    line-height: 1.4;
    box-shadow: 0 4px 16px rgba(0,0,0,0.25);
    max-width: 320px;
    cursor: default;
    user-select: none;
    transition: opacity 0.3s;
  `;

  badge.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;">
      <span style="font-size:28px;font-weight:700;line-height:1;">${score_letter}</span>
      <div>
        <div style="font-weight:600;font-size:12px;opacity:0.85;">Nutri-Score cognitivo · ${score_numeric}/100</div>
        <div style="font-size:11px;opacity:0.75;margin-top:2px;">${labels}</div>
      </div>
      <span id="cogana-close" style="margin-left:auto;opacity:0.6;font-size:16px;cursor:pointer;padding:0 4px;">✕</span>
    </div>
  `;

  document.body.appendChild(badge);

  badge.querySelector('#cogana-close').addEventListener('click', () => {
    badge.style.opacity = '0';
    setTimeout(removeBadge, 300);
  });

  // Auto-ocultar después de 12 segundos
  setTimeout(() => {
    if (badge.parentNode) {
      badge.style.opacity = '0';
      setTimeout(removeBadge, 300);
    }
  }, 12000);
}

function showLoadingBadge() {
  removeBadge();
  const badge = document.createElement('div');
  badge.id = 'cogana-badge';
  badge.style.cssText = `
    position: fixed;
    bottom: 24px;
    right: 24px;
    z-index: 9999;
    background: #374151;
    color: #d1d5db;
    border-radius: 12px;
    padding: 10px 16px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 12px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.25);
  `;
  badge.textContent = '⏳ Calculando Nutri-Score…';
  document.body.appendChild(badge);
}

// ─── POLLING DEL SCORE ────────────────────────────────────────────────────────
async function pollScore(youtubeId, attempts = 0) {
  if (attempts >= POLL_MAX) {
    removeBadge();
    return;
  }
  // Verificar que seguimos en el mismo video
  const currentId = new URLSearchParams(window.location.search).get('v');
  if (currentId !== youtubeId) return;

  try {
    const res = await fetch(`${SCORE_URL}/${youtubeId}/score`);
    if (res.ok) {
      const data = await res.json();
      if (data.scoring_done) {
        showBadge(data);
        return;
      }
    }
  } catch (_) {}

  setTimeout(() => pollScore(youtubeId, attempts + 1), POLL_INTERVAL);
}

// ─── EXTRACTION ───────────────────────────────────────────────────────────────
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
    video_id:         videoId,
    title,
    url:              `https://www.youtube.com/watch?v=${videoId}`,
    channel,
    duration_seconds: duration,
    view_count_raw:   viewsRaw,
    tracked_at:       new Date().toISOString(),
  };
}

// ─── SEND ─────────────────────────────────────────────────────────────────────
async function sendToBackend(payload) {
  try {
    const res = await fetch(BACKEND_URL, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });
    if (res.ok) {
      console.log(`%c[CognitiveAnalysis] ✓ tracked: "${payload.title}"`, 'color: #4ade80');
      return true;
    } else {
      const body = await res.text();
      console.warn(`[CognitiveAnalysis] Backend responded ${res.status}:`, body);
    }
  } catch (err) {
    console.error('[CognitiveAnalysis] Could not reach backend. Is FastAPI running?', err);
  }
  return false;
}

// ─── DEDUPLICATION ────────────────────────────────────────────────────────────
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

  removeBadge();

  setTimeout(async () => {
    const data = extractVideoData();
    if (!data) return;

    // Mostrar badge de carga inmediatamente
    showLoadingBadge();

    if (trackedThisSession.has(data.video_id)) {
      console.log(`[CognitiveAnalysis] Already tracked ${data.video_id} — polling score.`);
      pollScore(data.video_id);
      return;
    }

    if (data.duration_seconds === null) {
      const videoEl = document.querySelector('video.html5-main-video');
      data.duration_seconds = await getDurationWhenReady(videoEl);
    }

    const ok = await sendToBackend(data);
    if (ok) {
      trackedThisSession.add(data.video_id);
      pollScore(data.video_id);
    } else {
      removeBadge();
    }
  }, DELAY_MS);
}

// ─── LISTENERS ────────────────────────────────────────────────────────────────
if (window.location.pathname === '/watch') {
  handleNavigation();
}
window.addEventListener('yt-navigate-finish', handleNavigation);

/**
 * player.js — JavaScript untuk halaman pemutar (player.html)
 * Mengelola video player, navigasi episode, dan sidebar daftar episode.
 */

// ─────────────────────────────────────────────
//  KONFIGURASI
// ─────────────────────────────────────────────

const API_BASE = window.location.origin && window.location.origin.startsWith("http")
  ? window.location.origin
  : "http://localhost:5000";

// ─────────────────────────────────────────────
//  HELPER
// ─────────────────────────────────────────────

async function apiFetch(endpoint) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: { 'ngrok-skip-browser-warning': 'true' }
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const json = await res.json();
  return json.data;
}

function imgFallback(el) {
  if (el.dataset.fallbackApplied) return;
  el.dataset.fallbackApplied = "true";
  el.src = "icons/default_poster.svg";
}

function getParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    slug: params.get("slug") || "",
    ep: parseInt(params.get("ep") || "1", 10),
  };
}

function setParam(ep) {
  const url = new URL(window.location.href);
  url.searchParams.set("ep", ep);
  window.history.pushState({}, "", url.toString());
}

// ─────────────────────────────────────────────
//  STATE
// ─────────────────────────────────────────────

let currentAnime = null;
let currentEpNumber = 1;
let allEpisodes = [];
let currentQualities = [];
let currentPreferredRes = localStorage.getItem("anime_preferred_res") || "720p";
let currentPlaybackRate = parseFloat(localStorage.getItem("anime_playback_rate") || "1.0");
let currentEpisodeData = null;

// ─────────────────────────────────────────────
//  TOAST & RESOLUSI GRAFIK
// ─────────────────────────────────────────────

function showToast(message, duration = 2500) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), duration);
}

function updateQualityButtons(activeRes) {
  const buttons = document.querySelectorAll("#quality-selector .btn-res");
  buttons.forEach(btn => {
    if (btn.getAttribute("data-res") === activeRes) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });
}

function applyVideoQualityFilter(videoEl, res) {
  if (!videoEl) return;
  if (res === "1080p") {
    videoEl.style.imageRendering = "-webkit-optimize-contrast";
    videoEl.style.filter = "contrast(1.06) saturate(1.08) brightness(1.01)";
  } else if (res === "720p") {
    videoEl.style.imageRendering = "-webkit-optimize-contrast";
    videoEl.style.filter = "contrast(1.02) saturate(1.04)";
  } else if (res === "480p") {
    videoEl.style.imageRendering = "auto";
    videoEl.style.filter = "none";
  } else if (res === "360p") {
    videoEl.style.imageRendering = "auto";
    videoEl.style.filter = "contrast(0.98)";
  } else if (res === "144p") {
    videoEl.style.imageRendering = "pixelated";
    videoEl.style.filter = "contrast(0.92) brightness(0.95)";
  }
}

const DEAD_STREAM_DOMAINS = ["solidfiles", "zippyshare", "racaty", "tusfiles", "mediafire", "acefile", "mega.nz", "mirrorace", "hxfile", "commondatastorage", "bigbuckbunny", "youtube.com", "youtu.be", "ytimg", "youtube", "blogger.com", "blogger", "blogspot"];

function isDirectEmbedProvider(url) {
  if (!url || typeof url !== "string") return false;
  const lower = url.toLowerCase();
  return (
    lower.includes("playsobat.xyz") ||
    lower.includes("streamwish.to") ||
    lower.includes("vidlink.pro") ||
    lower.includes("vidlink") ||
    lower.includes("embed.su") ||
    lower.includes("vidsrc.me") ||
    lower.includes("vidsrc.to") ||
    lower.includes("vidsrc.net") ||
    lower.includes("vidsrc.cc") ||
    lower.includes("vidsrc") ||
    lower.includes("2embed.cc") ||
    lower.includes("2embed.to") ||
    lower.includes("2embed")
  );
}

function isUsableStreamUrl(url) {
  if (!url || typeof url !== "string" || !url.startsWith("http")) return false;
  const lower = url.toLowerCase();
  return !DEAD_STREAM_DOMAINS.some(d => lower.includes(d));
}

function changeResolution(targetRes) {
  currentPreferredRes = targetRes;
  localStorage.setItem("anime_preferred_res", targetRes);
  updateQualityButtons(targetRes);

  let selectedUrl = "";
  if (currentQualities && currentQualities.length > 0) {
    const qObj = currentQualities.find(q => q.quality === targetRes && isUsableStreamUrl(q.embed_url));
    if (qObj && qObj.embed_url) {
      selectedUrl = qObj.embed_url;
    }
  }
  if (!selectedUrl && currentEpisodeData?.episode?.embed_url && isUsableStreamUrl(currentEpisodeData.episode.embed_url)) {
    selectedUrl = currentEpisodeData.episode.embed_url;
  }
  if (!selectedUrl && currentQualities && currentQualities.length > 0) {
    const fallbackQ = currentQualities.find(q => isUsableStreamUrl(q.embed_url));
    if (fallbackQ) selectedUrl = fallbackQ.embed_url;
  }

  // Kirim sinyal ke iframe player secara realtime
  const frame = document.getElementById("main-player-frame");
  if (frame && frame.contentWindow) {
    try {
      frame.contentWindow.postMessage({
        type: "CHANGE_QUALITY",
        quality: targetRes,
        newUrl: selectedUrl
      }, "*");
    } catch (e) {}

    // Jika URL stream sumber berbeda (mis. URL 720p vs 480p)
    const currentSrc = frame.getAttribute("src") || "";
    if (isDirectEmbedProvider(selectedUrl)) {
      if (frame.src !== selectedUrl && selectedUrl) {
        frame.src = selectedUrl;
      }
    } else if (currentSrc.includes("/api/stream-proxy")) {
      const expectedSrc = `${API_BASE}/api/stream-proxy?url=${encodeURIComponent(selectedUrl)}&quality=${targetRes}&_t=${Date.now()}`;
      if (!currentSrc.includes(encodeURIComponent(selectedUrl)) || !currentSrc.includes(`quality=${targetRes}`)) {
        frame.src = expectedSrc;
      }
    } else if (frame.src !== selectedUrl && selectedUrl) {
      frame.src = selectedUrl;
    }
  }

  // Jika direct video HTML5
  const videoEl = document.querySelector("#video-wrapper video");
  if (videoEl) {
    applyVideoQualityFilter(videoEl, targetRes);
    if (selectedUrl && selectedUrl !== videoEl.src && !selectedUrl.includes("<iframe")) {
      const curTime = videoEl.currentTime || 0;
      const isPaused = videoEl.paused;
      videoEl.src = selectedUrl;
      videoEl.currentTime = curTime;
      if (!isPaused) videoEl.play().catch(() => {});
    }
  }

    const label = targetRes === "1080p" ? "1080p Full HD ✨" :
                  targetRes === "720p" ? "720p HD 🎬" :
                  targetRes === "480p" ? "480p SD ⚡" :
                  targetRes === "360p" ? "360p Hemat 📱" : "144p Super Hemat 🚀";
    showToast(`Resolusi: ${label}`);
    if (selectedUrl) {
      currentStreamUrl = selectedUrl;
      updateServerBadge(selectedUrl);
    }
  }

  function updateServerBadge(url) {
    const serverBadge = document.getElementById("server-badge");
    if (serverBadge) serverBadge.style.display = "none";
  }

  // ─────────────────────────────────────────────
  //  PENGATUR KECEPATAN PUTAR (PLAYBACK SPEED)
  // ─────────────────────────────────────────────

  function setPlaybackSpeed(speed) {
    const num = parseFloat(speed);
    if (isNaN(num) || num <= 0) return;
    currentPlaybackRate = num;
    localStorage.setItem("anime_playback_rate", num.toString());

    const vEl = document.querySelector("#video-wrapper video");
    if (vEl) {
      vEl.playbackRate = num;
    }

    const speedBtn = document.getElementById("btn-playback-speed");
    if (speedBtn) {
      speedBtn.innerHTML = `⚡ ${num === 1.0 ? '1.0x' : num + 'x'}`;
    }

    const inSpeedBtnText = document.getElementById("ctrl-speed-text");
    if (inSpeedBtnText) {
      inSpeedBtnText.textContent = `⚡ ${num === 1.0 ? '1.0x' : num + 'x'}`;
    }

    document.querySelectorAll(".speed-opt, .in-speed-btn").forEach(btn => {
      const btnSpeed = parseFloat(btn.getAttribute("data-speed"));
      if (Math.abs(btnSpeed - num) < 0.01) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });

    closeAllSpeedMenus();
    showToast(`⚡ Kecepatan Putar: ${num === 1.0 ? '1.0x (Normal)' : num + 'x'}`);
  }

  function togglePlaybackSpeedMenu(e) {
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }
    const menu = document.getElementById("playback-speed-menu");
    if (!menu) return;
    const isShown = menu.style.display === "block";
    closeAllSpeedMenus();
    if (!isShown) {
      menu.style.display = "block";
    }
  }

  function toggleInPlayerSpeedMenu(e) {
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }
    const popup = document.getElementById("in-player-speed-popup");
    if (!popup) return;
    const isShown = popup.style.display === "block";
    closeAllSpeedMenus();
    if (!isShown) {
      popup.style.display = "block";
    }
  }

  function closeAllSpeedMenus() {
    const menu = document.getElementById("playback-speed-menu");
    if (menu) menu.style.display = "none";
    const popup = document.getElementById("in-player-speed-popup");
    if (popup) popup.style.display = "none";
  }

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".playback-speed-container") && !e.target.closest(".in-player-speed-wrapper")) {
      closeAllSpeedMenus();
    }
  });

  // ─────────────────────────────────────────────
  //  UNDUH EPISODE (DIRECT MP4 UNTUK OFFLINE)
  // ─────────────────────────────────────────────

  async function downloadCurrentEpisode() {
    let streamUrl = currentStreamUrl || "";
    const vEl = document.querySelector("#video-wrapper video");
    if (!streamUrl && vEl) {
      const srcEl = vEl.querySelector("source");
      streamUrl = srcEl ? srcEl.src : vEl.src;
    }

    if (currentQualities && currentQualities.length > 0) {
      const bestQ = currentQualities.find(q => (q.quality === "720p" || q.quality === "1080p") && isUsableStreamUrl(q.embed_url)) || currentQualities.find(q => isUsableStreamUrl(q.embed_url));
      if (bestQ && bestQ.embed_url) {
        streamUrl = bestQ.embed_url;
      }
    }

    if (!streamUrl) {
      showToast("⚠️ Link video belum siap untuk diunduh!");
      return;
    }

    const animeTitle = currentAnime?.title || document.getElementById("player-anime-title")?.textContent || "Anime";
    const epTitle = document.getElementById("player-ep-title")?.textContent || `Episode ${currentEpNumber}`;
    
    let cleanName = `${animeTitle} - ${epTitle}`.replace(/[\\/*?:"<>|]/g, "").trim();
    if (!cleanName.toLowerCase().endsWith(".mp4")) {
      cleanName += ".mp4";
    }

    showToast(`📥 Menyiapkan unduhan: ${cleanName}...`, 3500);

    const downloadUrl = `${API_BASE}/api/video-stream?download=1&filename=${encodeURIComponent(cleanName)}&url=${encodeURIComponent(streamUrl)}`;

    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = cleanName;
    a.target = "_blank";
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      try { document.body.removeChild(a); } catch(e) {}
    }, 1000);

    showToast(`✅ Unduhan dimulai! Cek bar notifikasi HP Anda.`, 3500);
  }

  async function downloadSpecificEpisode(e, slug, epNum) {
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }

    const animeTitle = currentAnime?.title || document.getElementById("player-anime-title")?.textContent || "Anime";
    const cleanName = `${animeTitle} - Episode ${epNum}.mp4`.replace(/[\\/*?:"<>|]/g, "").trim();

    if (epNum === currentEpNumber && currentStreamUrl) {
      downloadCurrentEpisode();
      return;
    }

    showToast(`🔍 Menyiapkan Episode ${epNum}...`, 2000);

    try {
      const data = await apiFetch(`/api/animes/${slug}/episodes/${epNum}`);
      let url = data?.episode?.embed_url;
      if (data?.qualities && data.qualities.length > 0) {
        const qBest = data.qualities.find(q => (q.quality === "720p" || q.quality === "1080p") && isUsableStreamUrl(q.embed_url)) || data.qualities.find(q => isUsableStreamUrl(q.embed_url));
        if (qBest && qBest.embed_url) url = qBest.embed_url;
      }

      if (!url) {
        showToast(`⚠️ Episode ${epNum} belum memiliki stream langsung.`);
        return;
      }

      showToast(`📥 Mengunduh Episode ${epNum}...`, 3500);

      const downloadUrl = `${API_BASE}/api/video-stream?download=1&filename=${encodeURIComponent(cleanName)}&url=${encodeURIComponent(url)}`;
      const a = document.createElement("a");
      a.href = downloadUrl;
      a.download = cleanName;
      a.target = "_blank";
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        try { document.body.removeChild(a); } catch(err) {}
      }, 1000);

      showToast(`✅ Episode ${epNum} sedang diunduh ke memori HP!`, 3500);
    } catch (err) {
      showToast(`❌ Gagal mengunduh Episode ${epNum}: ${err.message}`);
    }
  }

  // ─────────────────────────────────────────────
  //  VIDEO PLAYER
  // ─────────────────────────────────────────────

  let currentStreamUrl = "";

  async function reloadCurrentVideo() {
    showToast("🔄 Menyegarkan link stream...");
    const params = getParams();
    if (params.slug && params.ep) {
      try {
        const freshData = await apiFetch(`/api/animes/${encodeURIComponent(params.slug)}/episodes/${params.ep}?force=1`);
        if (freshData && freshData.episode && freshData.episode.embed_url) {
          currentEpisodeData = freshData;
          currentQualities = freshData.qualities || [];
          loadVideoPlayer(freshData.episode.embed_url, freshData.episode.title, currentPreferredRes);
          showToast("✅ Stream berhasil dimuat ulang!");
          return;
        }
      } catch (e) {
        console.warn("Force refresh error, reloading frame directly:", e);
      }
    }

    const frame = document.getElementById("main-player-frame");
    if (frame && frame.src) {
      frame.src = frame.src.split("&_t=")[0] + `&_t=${Date.now()}`;
    } else if (currentStreamUrl) {
      loadVideoPlayer(currentStreamUrl, document.getElementById("player-ep-title")?.textContent, currentPreferredRes);
    }
  }

  window.addEventListener("message", async (e) => {
    if (e.data && e.data.type === "NEXT_EPISODE") {
      goToNextEp();
      return;
    }
    if (e.data && (e.data.type === "STREAM_FAILED" || e.data.type === "SWITCH_SERVER")) {
      if (!window._isStreamAutoRecovering) {
        window._isStreamAutoRecovering = true;
        showToast("🔄 Server utama sibuk, beralih ke server alternatif...");
        switchAlternativeServer();
        setTimeout(() => { window._isStreamAutoRecovering = false; }, 3500);
      }
    }
  });

function loadVideoPlayer(embedUrl, title, quality = currentPreferredRes) {
  const wrapper = document.getElementById("video-wrapper");
  if (!wrapper) return;

  currentStreamUrl = embedUrl || "";
  const openTabBtn = document.getElementById("btn-open-tab");
  const serverBadge = document.getElementById("server-badge");

  if (!embedUrl) {
    if (openTabBtn) openTabBtn.style.display = "none";
    if (serverBadge) serverBadge.textContent = "Tidak Ada";
    wrapper.innerHTML = `
      <div class="video-placeholder">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
          <path d="M15 10l4.553-2.276A1 1 0 0121 8.723v6.554a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2z"/>
        </svg>
        <p>Video sedang disiapkan untuk episode ini</p>
        <button type="button" class="btn btn-primary" onclick="reloadCurrentVideo()" style="margin-top:12px;padding:8px 16px;font-size:0.85rem;">
          🔄 Ambil Stream Sekarang
        </button>
      </div>
    `;
    return;
  }

  let url = embedUrl.trim();
  if (url.includes("<iframe")) {
    const srcMatch = url.match(/src=["']([^"']+)["']/i);
    if (srcMatch) url = srcMatch[1];
  }

  if (openTabBtn) {
    openTabBtn.href = url;
    openTabBtn.style.display = "inline-flex";
  }

  if (serverBadge) {
    serverBadge.style.display = "none";
  }

  const switchBtn = document.getElementById("btn-switch-server");
  if (switchBtn) {
    switchBtn.style.display = (currentQualities && currentQualities.length > 1) ? "inline-flex" : "none";
  }

  const isDirectVideo = url.endsWith(".mp4") || url.endsWith(".webm") || url.includes(".mp4") || url.includes("googlevideo.com") || url.includes("archive.org/download") || url.includes("animeverse.id") || url.includes("pixeldrain.com");
  const nextHtml = (currentNavData && currentNavData.next !== null && currentNavData.next !== undefined)
    ? "inline-flex" : "none";
  const nextText = (currentNavData && currentNavData.next !== null && currentNavData.next !== undefined)
    ? `Next Eps ${currentNavData.next}` : "Next Eps";

  if (isDirectVideo) {
    // Alirkan video direct melalui stream-proxy backend dengan parameter bypass ngrok
    const proxiedUrl = `${API_BASE}/api/video-stream?ngrok-skip-browser-warning=1&url=${encodeURIComponent(url)}`;
    const nextHtml = (currentNavData && currentNavData.next !== null && currentNavData.next !== undefined)
      ? "inline-flex" : "none";
    const nextText = (currentNavData && currentNavData.next !== null && currentNavData.next !== undefined)
      ? `Next Eps ${currentNavData.next}` : "Next Eps";

    wrapper.innerHTML = `
      <video
        id="direct-video-player"
        autoplay
        playsinline
        webkit-playsinline
        preload="auto"
        style="position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#000;"
      >
        <source src="${proxiedUrl}" type="video/mp4">
        <source src="${url}" type="video/mp4">
        Browser Anda tidak mendukung tag video HTML5.
      </video>

      <!-- Center Big Play/Pause Button on Tap -->
      <button type="button" id="custom-center-play-btn" class="custom-center-play-btn" aria-label="Play / Pause">
        <svg id="center-play-icon" viewBox="0 0 24 24" fill="currentColor" width="36" height="36">
          <path d="M8 5v14l11-7z"/>
        </svg>
      </button>

      <!-- Double Tap Ripple Indicators -->
      <div id="double-tap-ripple-left" class="double-tap-ripple left" style="display:none;">⏪ 10s</div>
      <div id="double-tap-ripple-right" class="double-tap-ripple right" style="display:none;">⏩ 10s</div>

      <!-- Custom In-Player Controls Bar -->
      <div id="custom-player-controls" class="custom-player-controls">
        <div class="custom-top-bar">
          <div class="custom-player-title">${title || 'Anime Streaming'}</div>
          <div class="custom-top-right">
            <span class="custom-server-badge" style="display:none !important;"></span>
          </div>
        </div>

        <div class="custom-bottom-bar">
          <!-- Progress Scrubber Bar -->
          <div class="custom-progress-container" id="custom-progress-container">
            <div class="custom-progress-bg">
              <div class="custom-progress-buffer" id="custom-progress-buffer"></div>
              <div class="custom-progress-played" id="custom-progress-played"></div>
            </div>
            <div class="custom-progress-thumb" id="custom-progress-thumb"></div>
          </div>

          <!-- Controls Row -->
          <div class="custom-controls-row">
            <div class="custom-controls-left">
              <button type="button" class="ctrl-btn" id="ctrl-play-pause" title="Play/Pause">
                <svg viewBox="0 0 24 24" fill="currentColor" width="22" height="22">
                  <path id="ctrl-play-path" d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
                </svg>
              </button>

              <!-- TOMBOL NEXT EPISODE DI DALAM PEMUTAR (FULLSCREEN & NORMAL) -->
              <button type="button" class="ctrl-btn in-player-next-chip" id="ctrl-next-ep" onclick="goToNextEp()" title="Episode Selanjutnya" style="display:${nextHtml};">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
                <span id="ctrl-next-text">${nextText}</span>
              </button>

              <span class="custom-time-display" id="custom-time-display">00:00 / 00:00</span>
            </div>

            <div class="custom-controls-right">
              <!-- In-Player Speed Button & Popup (Bisa diakses langsung di mode landscape / fullscreen) -->
              <div class="in-player-speed-wrapper" style="position:relative;display:inline-flex;">
                <button type="button" class="ctrl-btn in-player-speed-chip" id="ctrl-speed-btn" title="Atur Kecepatan Putar">
                  <span id="ctrl-speed-text">⚡ ${currentPlaybackRate === 1.0 ? '1.0x' : currentPlaybackRate + 'x'}</span>
                </button>
                <div id="in-player-speed-popup" class="in-player-speed-popup" style="display:none;">
                  <div class="in-speed-header">⚡ Kecepatan Putar</div>
                  <div class="in-speed-list">
                    <button type="button" class="in-speed-btn ${Math.abs(currentPlaybackRate - 0.75) < 0.01 ? 'active' : ''}" data-speed="0.75" onclick="setPlaybackSpeed(0.75)">0.75x</button>
                    <button type="button" class="in-speed-btn ${Math.abs(currentPlaybackRate - 1.0) < 0.01 ? 'active' : ''}" data-speed="1.0" onclick="setPlaybackSpeed(1.0)">1.0x (Normal)</button>
                    <button type="button" class="in-speed-btn ${Math.abs(currentPlaybackRate - 1.25) < 0.01 ? 'active' : ''}" data-speed="1.25" onclick="setPlaybackSpeed(1.25)">1.25x</button>
                    <button type="button" class="in-speed-btn ${Math.abs(currentPlaybackRate - 1.5) < 0.01 ? 'active' : ''}" data-speed="1.5" onclick="setPlaybackSpeed(1.5)">1.5x</button>
                    <button type="button" class="in-speed-btn ${Math.abs(currentPlaybackRate - 2.0) < 0.01 ? 'active' : ''}" data-speed="2.0" onclick="setPlaybackSpeed(2.0)">2.0x</button>
                  </div>
                </div>
              </div>

              <!-- In-Player Direct Download Button -->
              <button type="button" class="ctrl-btn in-player-download-chip" id="ctrl-download-btn" onclick="downloadCurrentEpisode()" title="Unduh Episode Ini (MP4)">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM17 13l-5 5-5-5h3V9h4v4h3z"/></svg>
              </button>

              <button type="button" class="ctrl-btn" id="ctrl-fullscreen-btn" onclick="toggleRotateFullscreen()" title="Layar Penuh (Landscape)">
                <svg viewBox="0 0 24 24" fill="currentColor" width="22" height="22">
                  <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    `;

    const vEl = wrapper.querySelector("video");
    if (vEl) {
      applyVideoQualityFilter(vEl, quality);
      vEl.playbackRate = currentPlaybackRate || 1.0;
      attachLongPressSpeed(vEl);
      setupCustomVideoControls(wrapper, vEl);

      // Auto-next ke episode berikutnya saat video selesai diputar
      vEl.addEventListener("ended", () => {
        if (currentNavData && currentNavData.next !== null && currentNavData.next !== undefined) {
          showToast(`🎬 Episode selesai! Memutar Episode ${currentNavData.next}...`);
          setTimeout(() => { goToNextEp(); }, 1200);
        }
      });

      let fallbackTried = false;
      vEl.addEventListener("error", (e) => {
        if (!fallbackTried) {
          fallbackTried = true;
          console.warn("Stream proxy gagal, mencoba koneksi CDN langsung:", url);
          vEl.removeAttribute("crossorigin");
          vEl.src = url;
          vEl.load();
          vEl.play().catch(() => {});
        } else {
          showToast("⚠️ Menghubungkan ke server cadangan...");
          if (typeof switchAlternativeServer === "function") {
            setTimeout(switchAlternativeServer, 1500);
          }
        }
      });
    }
    startWatchExpTracker(currentAnimeSlug, currentEpNumber);
    return;
  }

  // Semua stream non-direct dialirkan melalui stream-proxy untuk membongkar proteksi CSP & X-Frame-Options.
  // Namun untuk provider embed terbuka (vidsrc.me, 2embed.cc, vidlink.pro) yang memang didesain untuk
  // langsung di-embed tanpa blocking header, gunakan URL aslinya agar seluruh aset player berjalan mulus.
  const isDirectEmbed = isDirectEmbedProvider(url);

  const iframeSrc = isDirectEmbed
    ? url
    : `${API_BASE}/api/stream-proxy?ngrok-skip-browser-warning=1&url=${encodeURIComponent(url)}&quality=${quality || '720p'}&_t=${Date.now()}`;

  wrapper.innerHTML = `
    <iframe
      id="main-player-frame"
      src="${iframeSrc}"
      title="${title || 'Anime Player'}"
      allowfullscreen="true"
      webkitallowfullscreen="true"
      mozallowfullscreen="true"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share; fullscreen; screen-wake-lock; orientation"
      referrerpolicy="origin-when-cross-origin"
      loading="eager"
      style="position:absolute;inset:0;width:100%;height:100%;border:none;background:#000;">
    </iframe>
    <button type="button" id="ctrl-next-ep" class="ctrl-btn in-player-next-chip" onclick="goToNextEp()" title="Episode Selanjutnya" style="position:absolute;top:14px;right:14px;z-index:50;display:${nextHtml};">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
      <span id="ctrl-next-text">${nextText}</span>
    </button>
  `;

  startWatchExpTracker(currentAnimeSlug, currentEpNumber);
}

function formatPlayerTime(sec) {
  if (isNaN(sec) || !isFinite(sec)) return "00:00";
  const s = Math.floor(sec);
  const m = Math.floor(s / 60);
  const remSec = s % 60;
  const h = Math.floor(m / 60);
  const remMin = m % 60;
  if (h > 0) {
    return `${h}:${remMin.toString().padStart(2, "0")}:${remSec.toString().padStart(2, "0")}`;
  }
  return `${remMin.toString().padStart(2, "0")}:${remSec.toString().padStart(2, "0")}`;
}

let customControlsFadeTimer = null;
function setupCustomVideoControls(wrapper, vEl) {
  const controls = wrapper.querySelector("#custom-player-controls");
  const playPauseBtn = wrapper.querySelector("#ctrl-play-pause");
  const playPath = wrapper.querySelector("#ctrl-play-path");
  const centerPlayBtn = wrapper.querySelector("#custom-center-play-btn");
  const centerPlayIcon = wrapper.querySelector("#center-play-icon");
  const progressContainer = wrapper.querySelector("#custom-progress-container");
  const progressPlayed = wrapper.querySelector("#custom-progress-played");
  const progressBuffer = wrapper.querySelector("#custom-progress-buffer");
  const progressThumb = wrapper.querySelector("#custom-progress-thumb");
  const timeDisplay = wrapper.querySelector("#custom-time-display");
  const rippleLeft = wrapper.querySelector("#double-tap-ripple-left");
  const rippleRight = wrapper.querySelector("#double-tap-ripple-right");

  const nextEpBtn = wrapper.querySelector("#ctrl-next-ep");
  const fsBtn = wrapper.querySelector("#ctrl-fullscreen-btn");
  const topBar = wrapper.querySelector(".custom-top-bar");
  const bottomBar = wrapper.querySelector(".custom-bottom-bar");

  const AUTO_HIDE_DELAY = 3000; // Tepat 3 detik otomatis hilang jika tidak disentuh lagi
  let isControlsVisible = true;

  function showControls() {
    if (!controls) return;
    isControlsVisible = true;
    controls.classList.remove("fade-out");
    clearTimeout(customControlsFadeTimer);
    if (centerPlayBtn && vEl.paused) {
      centerPlayBtn.classList.remove("hidden");
    }
    // Jika tidak disentuh lagi, otomatis hilang setelah 3 detik
    if (!vEl.paused) {
      customControlsFadeTimer = setTimeout(() => {
        hideControls();
      }, AUTO_HIDE_DELAY);
    }
  }

  function hideControls() {
    if (!controls) return;
    isControlsVisible = false;
    controls.classList.add("fade-out");
    clearTimeout(customControlsFadeTimer);
    if (centerPlayBtn) {
      centerPlayBtn.classList.add("hidden");
    }
  }

  function toggleControls() {
    if (!controls) return;
    // Jika sedang hilang -> Munculkan
    // Jika sedang muncul -> Langsung hilangkan
    if (controls.classList.contains("fade-out") || !isControlsVisible) {
      showControls();
    } else {
      hideControls();
    }
  }

  function updatePlayIcons(isPlaying) {
    if (playPath) {
      playPath.setAttribute("d", isPlaying ? "M6 19h4V5H6v14zm8-14v14h4V5h-4z" : "M8 5v14l11-7z");
    }
    if (centerPlayIcon) {
      centerPlayIcon.innerHTML = isPlaying
        ? '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>'
        : '<path d="M8 5v14l11-7z"/>';
    }
    if (centerPlayBtn) {
      if (isPlaying) {
        centerPlayBtn.classList.add("hidden");
      } else {
        centerPlayBtn.classList.remove("hidden");
      }
    }
  }

  function togglePlay() {
    if (vEl.paused) {
      vEl.play().catch(() => {});
    } else {
      vEl.pause();
    }
  }

  // Handle tombol play/pause di bottom bar
  if (playPauseBtn) {
    playPauseBtn.onclick = (e) => {
      e.stopPropagation();
      togglePlay();
      showControls();
    };
  }

  // Handle tombol play besar di tengah layar
  if (centerPlayBtn) {
    centerPlayBtn.onclick = (e) => {
      e.stopPropagation();
      togglePlay();
      showControls();
    };
  }

  // Handle tombol Next Eps di dalam player
  if (nextEpBtn) {
    nextEpBtn.onclick = (e) => {
      e.stopPropagation();
      goToNextEp();
      showControls();
    };
  }

  // Handle tombol Fullscreen / Putar Layar di dalam player
  if (fsBtn) {
    fsBtn.onclick = (e) => {
      e.stopPropagation();
      toggleRotateFullscreen();
      showControls();
    };
  }

  // Handle tombol Kecepatan Putar di dalam player
  const ctrlSpeedBtn = wrapper.querySelector("#ctrl-speed-btn");
  if (ctrlSpeedBtn) {
    ctrlSpeedBtn.onclick = (e) => {
      e.stopPropagation();
      toggleInPlayerSpeedMenu(e);
      showControls();
    };
  }

  // Handle tombol Download di dalam player
  const ctrlDlBtn = wrapper.querySelector("#ctrl-download-btn");
  if (ctrlDlBtn) {
    ctrlDlBtn.onclick = (e) => {
      e.stopPropagation();
      downloadCurrentEpisode();
      showControls();
    };
  }

  // Cegah interaksi di dalam bilah kontrol atas dan bawah memicu penutupan kontrol
  [topBar, bottomBar].forEach(bar => {
    if (!bar) return;
    const keepControlsAlive = (e) => {
      e.stopPropagation();
      showControls();
    };
    bar.addEventListener("click", keepControlsAlive);
    bar.addEventListener("touchend", keepControlsAlive);
  });

  vEl.addEventListener("play", () => {
    updatePlayIcons(true);
    showControls();
  });

  vEl.addEventListener("pause", () => {
    updatePlayIcons(false);
    clearTimeout(customControlsFadeTimer);
    if (controls) controls.classList.remove("fade-out");
  });

  // Time & progress update
  vEl.addEventListener("timeupdate", () => {
    if (!vEl.duration) return;
    const pos = (vEl.currentTime / vEl.duration) * 100;
    if (progressPlayed) progressPlayed.style.width = `${pos}%`;
    if (progressThumb) progressThumb.style.left = `${pos}%`;
    if (timeDisplay) {
      timeDisplay.textContent = `${formatPlayerTime(vEl.currentTime)} / ${formatPlayerTime(vEl.duration)}`;
    }
  });

  // Buffer progress
  vEl.addEventListener("progress", () => {
    if (!vEl.duration || !vEl.buffered.length) return;
    const bufEnd = vEl.buffered.end(vEl.buffered.length - 1);
    const bufPos = (bufEnd / vEl.duration) * 100;
    if (progressBuffer) progressBuffer.style.width = `${bufPos}%`;
  });

  // Scrubber drag / click seeking
  if (progressContainer) {
    let isSeeking = false;
    function seekToPos(e) {
      const rect = progressContainer.getBoundingClientRect();
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const frac = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      if (vEl.duration) {
        vEl.currentTime = frac * vEl.duration;
      }
      showControls();
    }

    progressContainer.addEventListener("mousedown", (e) => {
      e.stopPropagation();
      isSeeking = true;
      seekToPos(e);
    });
    window.addEventListener("mousemove", (e) => {
      if (isSeeking) seekToPos(e);
    });
    window.addEventListener("mouseup", () => {
      if (isSeeking) isSeeking = false;
    });

    progressContainer.addEventListener("touchstart", (e) => {
      e.stopPropagation();
      isSeeking = true;
      seekToPos(e);
    }, { passive: true });
    progressContainer.addEventListener("touchmove", (e) => {
      if (isSeeking) seekToPos(e);
    }, { passive: true });
    progressContainer.addEventListener("touchend", (e) => {
      e.stopPropagation();
      isSeeking = false;
      showControls();
    });
  }

  // Tap & Double-Tap detection
  let lastTapTime = 0;
  let singleTapTimer = null;
  let lastTouchEndTime = 0;

  function showRipple(side, text) {
    const el = side === "left" ? rippleLeft : rippleRight;
    if (!el) return;
    el.textContent = text;
    el.style.display = "block";
    el.style.animation = "none";
    void el.offsetWidth; // trigger reflow
    el.style.animation = "pulseRipple 0.6s ease forwards";
    setTimeout(() => { el.style.display = "none"; }, 600);
  }

  function handleVideoAreaTap(e) {
    // Abaikan jika interaksi pada tombol atau bilah kontrol
    if (e.target && e.target.closest && (
      e.target.closest(".custom-bottom-bar") ||
      e.target.closest(".custom-top-bar") ||
      e.target.closest(".ctrl-btn") ||
      e.target.closest(".in-player-speed-wrapper") ||
      e.target.closest(".in-player-speed-popup") ||
      e.target.closest(".custom-center-play-btn") ||
      e.target.closest(".custom-progress-container") ||
      e.target.closest("#ctrl-next-ep") ||
      e.target.closest("#ctrl-download-btn") ||
      e.target.closest("#ctrl-speed-btn") ||
      e.target.closest("#ctrl-fullscreen-btn")
    )) {
      showControls();
      return;
    }

    const now = Date.now();
    const rect = wrapper.getBoundingClientRect();
    const clientX = (e.changedTouches && e.changedTouches[0]) ? e.changedTouches[0].clientX : e.clientX;
    const offsetX = clientX - rect.left;
    const isRight = offsetX > rect.width / 2;

    if (now - lastTapTime < 260) {
      // Double tap: batalkan toggle single tap, jalankan skip +/- 10s
      clearTimeout(singleTapTimer);
      singleTapTimer = null;
      lastTapTime = 0;
      if (isRight) {
        vEl.currentTime = Math.min(vEl.duration || Infinity, vEl.currentTime + 10);
        showRipple("right", "⏩ +10s");
      } else {
        vEl.currentTime = Math.max(0, vEl.currentTime - 10);
        showRipple("left", "⏪ -10s");
      }
      showControls();
    } else {
      lastTapTime = now;
      clearTimeout(singleTapTimer);
      singleTapTimer = setTimeout(() => {
        singleTapTimer = null;
        // Single tap pada area video:
        // Jika sedang tertutup -> Muncul (dan otomatis hilang setelah 3 detik jika tidak dipencet)
        // Jika sedang terbuka -> Langsung hilang saat dipencet lagi
        toggleControls();
      }, 200);
    }
  }

  function onWrapperTouchEnd(e) {
    lastTouchEndTime = Date.now();
    handleVideoAreaTap(e);
  }

  function onWrapperClick(e) {
    // Cegah ghost click sintetis dari browser HP yang terkirim setelah touchend
    if (Date.now() - lastTouchEndTime < 650) return;
    handleVideoAreaTap(e);
  }

  wrapper.addEventListener("touchend", onWrapperTouchEnd, { passive: true });
  wrapper.addEventListener("click", onWrapperClick);
  wrapper.addEventListener("mousemove", () => {
    // Hanya respon mouse komputer asli, bukan sentuhan layar HP
    if (Date.now() - lastTouchEndTime < 1000) return;
    showControls();
  }, { passive: true });

  // MediaSession API integration
  if ("mediaSession" in navigator) {
    try {
      navigator.mediaSession.setActionHandler("nexttrack", () => goToNextEp());
      navigator.mediaSession.setActionHandler("previoustrack", () => goToPrevEp());
      navigator.mediaSession.setActionHandler("seekforward", (details) => {
        vEl.currentTime = Math.min(vEl.duration || Infinity, vEl.currentTime + (details.seekOffset || 10));
      });
      navigator.mediaSession.setActionHandler("seekbackward", (details) => {
        vEl.currentTime = Math.max(0, vEl.currentTime - (details.seekOffset || 10));
      });
    } catch (err) {}
  }

  showControls();
}

function toggleRotateFullscreen() {
  const wrapper = document.getElementById("video-wrapper");
  if (!wrapper) return;
  const isFs = !!(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement);
  if (!isFs) {
    const vEl = wrapper.querySelector("video");
    const req = wrapper.requestFullscreen || wrapper.webkitRequestFullscreen || wrapper.mozRequestFullScreen || wrapper.msRequestFullscreen;
    if (req) {
      req.call(wrapper).then(() => {
        try {
          if (screen.orientation && screen.orientation.lock) {
            screen.orientation.lock("landscape").catch(() => {});
          }
        } catch (e) {}
        showToast("🔄 Mode Layar Penuh Landscape");
      }).catch(() => {
        if (vEl && vEl.webkitEnterFullscreen) {
          try { vEl.webkitEnterFullscreen(); } catch (e) {}
        } else {
          showToast("🔄 Mode Layar Penuh Aktif");
        }
      });
    } else if (vEl && vEl.webkitEnterFullscreen) {
      try { vEl.webkitEnterFullscreen(); } catch (e) {}
    }
  } else {
    const exit = document.exitFullscreen || document.webkitExitFullscreen || document.mozCancelFullScreen;
    if (exit) {
      exit.call(document).then(() => {
        try {
          if (screen.orientation && screen.orientation.unlock) {
            screen.orientation.unlock();
          }
        } catch (e) {}
      }).catch(() => {});
    }
  }
}

// Sinkronkan ikon & status tombol saat masuk/keluar fullscreen
document.addEventListener("fullscreenchange", () => {
  const isFs = !!(document.fullscreenElement || document.webkitFullscreenElement);
  const rotBtn = document.getElementById("btn-rotate-screen");
  if (rotBtn) {
    rotBtn.innerHTML = isFs ? "🔄 Layar Normal (Portrait)" : "🔄 Layar Miring (Landscape)";
  }
  if (!isFs && screen.orientation && screen.orientation.unlock) {
    try { screen.orientation.unlock(); } catch (e) {}
  }
});
document.addEventListener("webkitfullscreenchange", () => {
  const isFs = !!(document.fullscreenElement || document.webkitFullscreenElement);
  const rotBtn = document.getElementById("btn-rotate-screen");
  if (rotBtn) {
    rotBtn.innerHTML = isFs ? "🔄 Layar Normal (Portrait)" : "🔄 Layar Miring (Landscape)";
  }
  if (!isFs && screen.orientation && screen.orientation.unlock) {
    try { screen.orientation.unlock(); } catch (e) {}
  }
});

let watchExpInterval = null;
let currentWatchTimeSeconds = 0;

function startWatchExpTracker(slug, epNum) {
  if (watchExpInterval) clearInterval(watchExpInterval);
  currentWatchTimeSeconds = 0;
  if (!slug) return;

  // Bonus awal menonton setelah 12 detik
  setTimeout(() => {
    if (typeof OtakuAuth !== "undefined") {
      OtakuAuth.addExp(15, slug, epNum, 15);
    }
  }, 12000);

  // Setiap 45 detik saat pengguna menonton episode, berikan +25 EXP!
  watchExpInterval = setInterval(() => {
    currentWatchTimeSeconds += 45;
    if (typeof OtakuAuth !== "undefined") {
      OtakuAuth.addExp(25, slug, epNum, 45);
    }
  }, 45000);
}

// ─────────────────────────────────────────────
//  RIWAYAT NONTON (WATCH HISTORY)
// ─────────────────────────────────────────────

function recordUserWatchHistory(slug, epNum, animeTitle, animeThumbnail) {
  if (!slug) return;
  const historyItem = {
    anime_slug: slug,
    ep_number: epNum || 1,
    anime_title: animeTitle || currentAnime?.title || document.getElementById("player-ep-title")?.textContent || "Anime",
    anime_thumbnail: animeThumbnail || currentAnime?.thumbnail || "icons/default_poster.svg",
    watch_seconds: 60,
    timestamp: Date.now()
  };

  try {
    let historyList = JSON.parse(localStorage.getItem("otakux_watch_history") || "[]");
    historyList = historyList.filter(h => !(h.anime_slug === slug && h.ep_number === epNum));
    historyList.unshift(historyItem);
    if (historyList.length > 50) historyList = historyList.slice(0, 50);
    localStorage.setItem("otakux_watch_history", JSON.stringify(historyList));
  } catch (e) {
    console.warn("[History] Gagal simpan ke localStorage:", e);
  }

  // Sinkronkan ke database server jika login
  if (typeof OtakuAuth !== "undefined") {
    const user = OtakuAuth.getUser();
    if (user && user.id) {
      fetch(`${API_BASE}/api/user/${user.id}/add-exp`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "true" },
        body: JSON.stringify({
          exp: 5,
          anime_slug: slug,
          ep_number: epNum || 1,
          seconds: 30
        })
      }).catch(() => {});
    }
  }
}

// ─────────────────────────────────────────────
//  LONG-PRESS -> 2X SPEED & BLOKIR CONTEXT MENU
// ─────────────────────────────────────────────

// Blokir context menu bawaan di area video player
document.addEventListener("contextmenu", (e) => {
  if (e.target.closest("#video-wrapper") || e.target.closest("video") || e.target.closest("iframe")) {
    e.preventDefault();
    return false;
  }
}, { capture: true });

function attachLongPressSpeed(videoEl) {
  if (!videoEl) return;
  videoEl.addEventListener("contextmenu", (e) => { e.preventDefault(); return false; });

  const badge = document.getElementById("floating-speed-badge");
  let timer = null;
  let is2x = false;
  let prevRate = 1.0;

  const startSpeed = () => {
    if (videoEl.paused) return;
    prevRate = videoEl.playbackRate || 1.0;
    videoEl.playbackRate = 2.0;
    is2x = true;
    if (badge) badge.classList.add("show");
    try { if (navigator.vibrate) navigator.vibrate(35); } catch(e) {}
  };

  const stopSpeed = () => {
    if (timer) { clearTimeout(timer); timer = null; }
    if (is2x) {
      videoEl.playbackRate = currentPlaybackRate || 1.0;
      is2x = false;
      if (badge) badge.classList.remove("show");
    }
  };

  const wrapper = document.getElementById("video-wrapper");
  if (wrapper) {
    wrapper.addEventListener("pointerdown", (e) => {
      if (e.target.closest("button") || e.target.closest(".res-badge")) return;
      stopSpeed();
      timer = setTimeout(startSpeed, 260);
    });
    wrapper.addEventListener("pointerup", stopSpeed);
    wrapper.addEventListener("pointercancel", stopSpeed);
    wrapper.addEventListener("pointerleave", stopSpeed);
    wrapper.addEventListener("touchend", stopSpeed);
    wrapper.addEventListener("touchcancel", stopSpeed);
  }
}


// ─────────────────────────────────────────────
//  PLAYER INFO
// ─────────────────────────────────────────────

function renderPlayerInfo(anime, episode, nav) {
  // Judul anime dan episode
  const animeTitle = document.getElementById("player-anime-title");
  const epTitle = document.getElementById("player-ep-title");
  if (animeTitle) animeTitle.textContent = anime.title;
  if (epTitle) epTitle.textContent = episode.title || `Episode ${episode.ep_number}`;

  // Meta badges
  const metaEl = document.getElementById("player-meta");
  if (metaEl) {
    metaEl.innerHTML = `
      <span class="badge ${anime.status === 'Completed' ? 'badge-completed' : 'badge-ongoing'}">${anime.status || 'Ongoing'}</span>
      ${anime.genre ? `<span style="font-size:.82rem;color:var(--clr-text-muted)">${anime.genre}</span>` : ''}
      ${anime.score > 0 ? `<span class="hero-score" style="font-size:.9rem">⭐ ${anime.score}</span>` : ''}
      ${episode.duration ? `<span style="font-size:.82rem;color:var(--clr-text-muted)">🕐 ${episode.duration}</span>` : ''}
    `;
  }

  // Sinopsis
  const synopsisEl = document.getElementById("synopsis-text");
  if (synopsisEl) {
    synopsisEl.textContent = anime.synopsis || "Tidak ada sinopsis tersedia.";
  }

  // Navigation buttons
  renderNavButtons(nav, anime.slug || currentAnime?.slug);

  // Periksa apakah tersedia serial TV lengkap untuk waralaba ini atau sediakan tombol scrape
  checkRelatedSeries(anime, episode);
}

async function checkRelatedSeries(anime, episode) {
  const container = document.getElementById("smart-recommendation");
  if (!container) return;
  container.style.display = "none";

  try {
    const isPreview = episode && (String(episode.id).startsWith("p-") || episode.duration === "Official HD" || !episode.embed_url);
    // Jika anime saat ini sudah memiliki episode nyata (> 1 episode) dan bukan entri preview kosong, jangan tampilkan banner ini!
    if ((allEpisodes && allEpisodes.length > 1) && !isPreview) {
      return;
    }

    const rawTitle = anime.title || "";
    const baseTitle = rawTitle.split(/[:\-\(]/)[0].trim();
    if (!baseTitle || baseTitle.length < 3) return;

    const res = await fetch(`${API_BASE}/api/animes/search?q=${encodeURIComponent(baseTitle)}`);
    if (!res.ok) return;
    const json = await res.json();
    const hits = json.data || [];

    // Cari anime utama hanya jika anime saat ini adalah klip / OVA tunggal (<= 1 ep)
    const isCurrentSingleOrPreview = !allEpisodes || allEpisodes.length <= 1 || isPreview;
    const mainSeries = isCurrentSingleOrPreview ? hits.find(h => {
      const isDiff = h.slug !== anime.slug;
      const hasManyEps = (h.ep_count && h.ep_count > 3);
      return isDiff && hasManyEps;
    }) : null;

    if (mainSeries && isCurrentSingleOrPreview) {
      container.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;">
          <span style="font-size:1.6rem;">📺</span>
          <div>
            <div style="font-weight:600;color:#fff;">Tersedia Serial Utama Lengkap: <span style="color:var(--clr-primary);">${mainSeries.title}</span></div>
            <div style="font-size:0.82rem;color:var(--clr-text-muted);">Tonton seluruh episode lengkap tanpa terpotong (${mainSeries.ep_count || 170} Episode).</div>
          </div>
        </div>
        <a href="player.html?slug=${mainSeries.slug}&ep=1" class="btn btn-primary" style="padding:7px 16px;font-size:0.85rem;white-space:nowrap;text-decoration:none;background:var(--clr-primary);color:#fff;border-radius:6px;display:inline-block;">Nonton Serial Utama ›</a>
      `;
      container.style.display = "flex";
      return;
    }

    // Jika ini adalah cuplikan tanpa episode nyata, tampilkan tombol scrape on-demand
    if (isPreview) {
      container.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;">
          <span style="font-size:1.6rem;">⚡</span>
          <div>
            <div style="font-weight:600;color:#fff;">Episode Belum Tersedia di Server Lokal</div>
            <div style="font-size:0.82rem;color:var(--clr-text-muted);">Ingin tonton langsung di web ini tanpa buka aplikasi lain? Ambil episode otomatis sekarang.</div>
          </div>
        </div>
        <button id="btn-scrape-fast" onclick="scrapeFastAnime('${anime.slug}')" class="btn btn-primary" style="padding:7px 16px;font-size:0.85rem;white-space:nowrap;border:none;cursor:pointer;border-radius:6px;">
          ⚡ Ambil Episode Sekarang
        </button>
      `;
      container.style.display = "flex";
    }
  } catch (err) {
    console.warn("Gagal mengecek serial terkait:", err);
  }
}

async function scrapeFastAnime(slug) {
  const btn = document.getElementById("btn-scrape-fast");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳ Mengambil episode...";
  }
  try {
    const res = await fetch(`${API_BASE}/api/animes/${encodeURIComponent(slug)}/scrape-fast`);
    const json = await res.json();
    if (json.status === "success") {
      alert("✅ Episode berhasil diambil! Memuat ulang pemutar...");
      window.location.reload();
    } else {
      alert("Catatan: " + (json.message || "Episode belum tersedia di sumber streaming saat ini."));
      if (btn) {
        btn.disabled = false;
        btn.textContent = "⚡ Coba Lagi";
      }
    }
  } catch (err) {
    alert("Koneksi gagal: " + err.message);
    if (btn) {
      btn.disabled = false;
      btn.textContent = "⚡ Coba Lagi";
    }
  }
}

const episodeDataCache = new Map();

async function prefetchEpisode(slug, epNum) {
  if (!slug || epNum === null || epNum === undefined) return;
  const key = `${slug}:${epNum}`;
  if (episodeDataCache.has(key)) return;
  try {
    const data = await apiFetch(`/api/animes/${slug}/episodes/${epNum}`);
    if (data && data.episode) {
      episodeDataCache.set(key, data);
    }
  } catch (err) {
    // silent prefetch
  }
}

let currentNavData = { prev: null, next: null };

function goToNextEp() {
  if (currentNavData && currentNavData.next !== null && currentNavData.next !== undefined) {
    const slug = currentAnime?.slug || getParams().slug;
    const wasFullscreen = !!(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement);
    loadEpisode(slug, currentNavData.next, true);
    showToast(`▶ Memutar Episode ${currentNavData.next}`);

    // Pertahankan mode fullscreen / layar miring jika sedang aktif
    if (wasFullscreen) {
      setTimeout(() => {
        const wrapper = document.getElementById("video-wrapper");
        if (wrapper && !(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement)) {
          const req = wrapper.requestFullscreen || wrapper.webkitRequestFullscreen || wrapper.mozRequestFullScreen;
          if (req) req.call(wrapper).catch(() => {});
        }
      }, 350);
    }
  } else {
    showToast("🎉 Ini adalah episode terbaru yang tersedia!");
  }
}

function goToPrevEp() {
  if (currentNavData && currentNavData.prev !== null && currentNavData.prev !== undefined) {
    const slug = currentAnime?.slug || getParams().slug;
    loadEpisode(slug, currentNavData.prev, true);
    showToast(`◀ Memutar Episode ${currentNavData.prev}`);
  }
}

function switchAlternativeServer() {
  if (!currentQualities || currentQualities.length <= 1) {
    showToast("🔄 Menyegarkan link stream dari server...");
    reloadCurrentVideo();
    return;
  }

  const usable = currentQualities.filter(q => isUsableStreamUrl(q.embed_url));
  if (usable.length <= 1) {
    showToast("🔄 Mengambil mirror stream baru...");
    reloadCurrentVideo();
    return;
  }

  // Cari server alternatif yang URL atau domainnya berbeda dari server yang sedang aktif
  const curUrl = (currentStreamUrl || "").toLowerCase();
  let target = null;

  for (const q of usable) {
    const qUrl = (q.embed_url || "").toLowerCase();
    if (q.quality !== currentPreferredRes && qUrl && !curUrl.includes(qUrl)) {
      target = q;
      break;
    }
  }

  if (!target) {
    const currentIdx = usable.findIndex(q => q.quality === currentPreferredRes);
    const nextIdx = (currentIdx + 1) % usable.length;
    target = usable[nextIdx];
  }

  if (target) {
    showToast(`⚡ Beralih ke Server ${target.quality}...`);
    changeResolution(target.quality);
  } else {
    reloadCurrentVideo();
  }
}

// Dukungan undo / tombol Back browser tanpa reload halaman (Instant SPA back/forward)
window.addEventListener("popstate", () => {
  const params = getParams();
  if (params.slug && params.ep && params.ep !== currentEpNumber) {
    loadEpisode(params.slug, params.ep, false);
  }
});

function renderNavButtons(nav, slug) {
  currentNavData = nav || { prev: null, next: null };
  const prevBtn = document.getElementById("btn-prev-ep");
  const nextBtn = document.getElementById("btn-next-ep");
  const quickPrev = document.getElementById("btn-quick-prev");
  const quickNext = document.getElementById("btn-quick-next");
  const quickBadge = document.getElementById("quick-ep-badge");
  const switchBtn = document.getElementById("btn-switch-server");

  if (switchBtn) {
    switchBtn.style.display = (currentQualities && currentQualities.length > 1) ? "inline-flex" : "none";
  }

  if (quickBadge) {
    quickBadge.textContent = `Episode ${currentEpNumber}`;
  }

  // Tombol navigasi bawah (SPA - tidak mereload halaman)
  if (prevBtn) {
    if (nav.prev !== null && nav.prev !== undefined) {
      prevBtn.disabled = false;
      prevBtn.classList.remove("disabled");
      prevBtn.removeAttribute("disabled");
      prevBtn.onclick = (e) => { e.preventDefault(); goToPrevEp(); };
    } else {
      prevBtn.disabled = true;
      prevBtn.classList.add("disabled");
      prevBtn.setAttribute("disabled", "true");
      prevBtn.onclick = (e) => { e.preventDefault(); };
    }
  }

  if (nextBtn) {
    if (nav.next !== null && nav.next !== undefined) {
      nextBtn.disabled = false;
      nextBtn.classList.remove("disabled");
      nextBtn.removeAttribute("disabled");
      nextBtn.onclick = (e) => { e.preventDefault(); goToNextEp(); };
    } else {
      nextBtn.disabled = true;
      nextBtn.classList.add("disabled");
      nextBtn.setAttribute("disabled", "true");
      nextBtn.onclick = (e) => { e.preventDefault(); };
    }
  }

  // Tombol navigasi cepat tepat di bawah video player
  if (quickPrev) {
    if (nav.prev !== null && nav.prev !== undefined) {
      quickPrev.disabled = false;
      quickPrev.classList.remove("disabled");
      quickPrev.onclick = () => goToPrevEp();
      quickPrev.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/></svg>
        <span>Eps ${nav.prev}</span>
      `;
    } else {
      quickPrev.disabled = true;
      quickPrev.classList.add("disabled");
      quickPrev.innerHTML = `<span>⏮ Awal</span>`;
    }
  }

  if (quickNext) {
    if (nav.next !== null && nav.next !== undefined) {
      quickNext.disabled = false;
      quickNext.classList.remove("disabled");
      quickNext.onclick = () => goToNextEp();
      quickNext.innerHTML = `
        <span>Eps ${nav.next} Selanjutnya</span>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/></svg>
      `;
    } else {
      quickNext.disabled = true;
      quickNext.classList.add("disabled");
      quickNext.innerHTML = `<span>Tamat / Terakhir 🏁</span>`;
    }
  }

  // Tombol Next Episode di dalam layar pemutar (in-player / fullscreen)
  const inPlayerNext = document.getElementById("ctrl-next-ep") || document.getElementById("in-player-next-btn");
  const inPlayerNextText = document.getElementById("ctrl-next-text");
  if (inPlayerNext) {
    if (nav.next !== null && nav.next !== undefined) {
      inPlayerNext.style.display = "inline-flex";
      inPlayerNext.disabled = false;
      inPlayerNext.onclick = (e) => {
        e.stopPropagation();
        goToNextEp();
      };
      if (inPlayerNextText) {
        inPlayerNextText.textContent = `Next Eps ${nav.next}`;
      } else {
        inPlayerNext.innerHTML = `
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
          <span>Next Eps ${nav.next}</span>
        `;
      }
    } else {
      inPlayerNext.style.display = "none";
      inPlayerNext.disabled = true;
    }
  }
}

// ─────────────────────────────────────────────
//  SIDEBAR EPISODE LIST
// ─────────────────────────────────────────────

function renderSidebar(episodes, currentEp, animeSlug) {
  const list = document.getElementById("episode-list");
  const countEl = document.getElementById("episode-count");

  if (countEl) countEl.textContent = `${episodes.length} Episode`;
  if (!list) return;

  list.innerHTML = episodes.map(ep => `
    <div
      class="ep-list-item ${ep.ep_number === currentEp ? 'active' : ''}"
      id="ep-item-${ep.ep_number}"
      onclick="handleEpClick(event, '${animeSlug}', ${ep.ep_number})"
      style="cursor:pointer;"
    >
      <div class="ep-list-num">${ep.ep_number}</div>
      <div class="ep-list-info">
        <div class="ep-list-title">${ep.title || `Episode ${ep.ep_number}`}</div>
        ${ep.duration ? `<div class="ep-list-dur">⏱ ${ep.duration}</div>` : ''}
      </div>
      <div style="display:flex;align-items:center;gap:6px;flex-shrink:0;">
        <button type="button" class="btn-ep-download" onclick="downloadSpecificEpisode(event, '${animeSlug}', ${ep.ep_number})" title="Unduh Episode ${ep.ep_number} (MP4)">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM17 13l-5 5-5-5h3V9h4v4h3z"/></svg>
        </button>
        ${ep.ep_number === currentEp ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="color:var(--clr-primary);flex-shrink:0"><path d="M8 5v14l11-7z"/></svg>` : ''}
      </div>
    </div>
  `).join('');

  // Scroll ke episode aktif
  const activeEl = document.getElementById(`ep-item-${currentEp}`);
  if (activeEl) {
    setTimeout(() => activeEl.scrollIntoView({ block: "center", behavior: "smooth" }), 200);
  }
}

// ─────────────────────────────────────────────
//  NAVIGASI EPISODE (IN-PAGE SPA DENGAN MEMORY CACHE)
// ─────────────────────────────────────────────

async function handleEpClick(e, slug, epNumber) {
  e.preventDefault();
  if (epNumber === currentEpNumber) return;

  await loadEpisode(slug, epNumber, true);
}

async function loadEpisode(slug, epNumber, updateHistory = true) {
  const cacheKey = `${slug}:${epNumber}`;
  let data = episodeDataCache.get(cacheKey);

  // Jika data belum ada di cache memory, ambil dari API
  if (!data) {
    const wrapper = document.getElementById("video-wrapper");
    if (wrapper) {
      wrapper.innerHTML = `<div class="video-placeholder"><div class="spinner"></div><p style="margin-top:16px;color:var(--clr-text-muted)">Memuat Episode ${epNumber}...</p></div>`;
    }

    try {
      data = await apiFetch(`/api/animes/${slug}/episodes/${epNumber}`);
      if (!data) return;
      episodeDataCache.set(cacheKey, data);
    } catch (e) {
      console.error("[Player] Gagal load episode:", e);
      if (/\b404\b/.test(e.message)) {
        await showNoEpisodes(slug, epNumber);
        return;
      }
      const wrapper = document.getElementById("video-wrapper");
      if (wrapper) {
        wrapper.innerHTML = `
          <div class="video-placeholder">
            <p style="color:var(--clr-error)">⚠ Gagal memuat episode ${epNumber}</p>
            <p style="font-size:.8rem;color:var(--clr-text-muted)">${e.message}</p>
          </div>
        `;
      }
      return;
    }
  }

  currentEpNumber = epNumber;
  if (updateHistory) {
    setParam(epNumber);
  }

  allEpisodes = data.all_episodes || allEpisodes;
  currentEpisodeData = data;
  currentQualities = data.qualities || [];
  currentAnimeSlug = slug;

  // Tentukan resolusi sesuai preferensi pengguna
  let chosenRes = currentPreferredRes;
  let chosenStreamUrl = "";

  if (currentQualities && currentQualities.length > 0) {
    const matchingQ = currentQualities.find(q => q.quality === chosenRes && isUsableStreamUrl(q.embed_url));
    if (matchingQ && matchingQ.embed_url) {
      chosenStreamUrl = matchingQ.embed_url;
    } else {
      const hdQ = currentQualities.find(q => (q.quality === "720p" || q.quality === "1080p") && isUsableStreamUrl(q.embed_url)) || currentQualities.find(q => isUsableStreamUrl(q.embed_url));
      if (hdQ) {
        chosenRes = hdQ.quality;
        chosenStreamUrl = hdQ.embed_url;
      }
    }
  }
  if (!chosenStreamUrl && isUsableStreamUrl(data.episode?.embed_url)) {
    chosenStreamUrl = data.episode.embed_url;
  }
  updateQualityButtons(chosenRes);

  // Update navigasi dan info terlebih dahulu agar data episode selanjutnya langsung siap
  currentNavData = data.navigation || { prev: null, next: null };
  renderPlayerInfo(data.anime, data.episode, data.navigation);

  // Update player video secara instan
  loadVideoPlayer(chosenStreamUrl, data.episode?.title, chosenRes);

  // Update status aktif di sidebar episode secara efisien tanpa lag
  const existingEpItems = document.querySelectorAll(".ep-list-item");
  if (existingEpItems.length > 0) {
    existingEpItems.forEach(item => item.classList.remove("active"));
    const activeEl = document.getElementById(`ep-item-${epNumber}`);
    if (activeEl) {
      activeEl.classList.add("active");
      activeEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
    } else {
      renderSidebar(allEpisodes, currentEpNumber, slug);
    }
  } else {
    renderSidebar(allEpisodes, currentEpNumber, slug);
  }

  if (window.updateBreadcrumb) window.updateBreadcrumb(data.anime.title, slug, epNumber);

  // Update halaman title
  document.title = `${data.anime.title} - Episode ${epNumber} | Otakux`;

  // Prefetch episode selanjutnya dan sebelumnya di background agar navigasi berikutnya 0ms instant!
  if (data.navigation) {
    if (data.navigation.next) prefetchEpisode(slug, data.navigation.next);
    if (data.navigation.prev) prefetchEpisode(slug, data.navigation.prev);
  }

  // Non-blocking async data (komentar, view counter, statistik, riwayat nonton)
  loadAnimeStats(slug);
  loadAnimeComments(slug, epNumber);
  recordAnimeView(slug);
  recordUserWatchHistory(slug, epNumber, data.anime?.title, data.anime?.thumbnail);
}

// ─────────────────────────────────────────────
//  ANIME TANPA EPISODE (trailer + platform resmi)
// ─────────────────────────────────────────────

function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function safeHttpUrl(u) {
  try {
    const x = new URL(u);
    return x.protocol === "http:" || x.protocol === "https:" ? x.href : null;
  } catch (e) {
    return null;
  }
}

function trailerInfo(trailer) {
  if (!trailer || !/^[\w-]{3,64}$/.test(trailer.id || "")) return null;
  const site = String(trailer.site || "").toLowerCase();
  if (site === "youtube") {
    return {
      embed: `https://www.youtube.com/embed/${trailer.id}?rel=0`,
      page: `https://www.youtube.com/watch?v=${trailer.id}`,
      label: "YouTube",
    };
  }
  if (site === "dailymotion") {
    return {
      embed: `https://www.dailymotion.com/embed/video/${trailer.id}`,
      page: `https://www.dailymotion.com/video/${trailer.id}`,
      label: "Dailymotion",
    };
  }
  return null;
}

function ensureWatchLinksBox() {
  let box = document.getElementById("watch-links-box");
  if (box) return box;
  box = document.createElement("div");
  box.id = "watch-links-box";
  box.style.cssText = "margin-top:10px;padding:14px;background:var(--clr-surface);border:1px solid var(--clr-border);border-radius:var(--radius-md);";
  const toolbar = document.querySelector(".video-toolbar");
  if (toolbar && toolbar.parentNode) {
    toolbar.parentNode.insertBefore(box, toolbar.nextSibling);
  } else {
    const wrapper = document.getElementById("video-wrapper");
    if (wrapper && wrapper.parentNode) wrapper.parentNode.insertBefore(box, wrapper.nextSibling);
  }
  return box;
}

function buildLinkButton(href, label) {
  const a = document.createElement("a");
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.className = "btn btn-secondary";
  a.style.cssText = "padding:8px 14px;font-size:.85rem;text-decoration:none;";
  a.textContent = label;
  return a;
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

/**
 * Dipanggil saat episode tidak ditemukan.
 * - Kalau anime sebenarnya punya episode lain -> arahkan ke episode pertama.
 * - Kalau tidak punya episode sama sekali -> tampilkan trailer resmi dan
 *   tombol "Tonton di platform resmi" (data dari AniList).
 */
async function showNoEpisodes(slug, requestedEp) {
  const wrapper = document.getElementById("video-wrapper");
  if (!wrapper) return;

  let anime = null;
  let extras = null;
  try { anime = await apiFetch(`/api/animes/${encodeURIComponent(slug)}`); } catch (e) { /* ditangani di bawah */ }

  if (!anime) {
    wrapper.innerHTML = `
      <div class="video-placeholder">
        <p>Anime tidak ditemukan.</p>
        <a href="index.html" style="color:var(--clr-primary);margin-top:12px;font-size:.85rem">← Kembali ke Beranda</a>
      </div>
    `;
    return;
  }

  try { extras = await apiFetch(`/api/animes/${encodeURIComponent(slug)}/extras`); } catch (e) { /* opsional */ }

  // Anime punya episode lain? Arahkan ke episode pertama yang ada.
  if (extras && extras.episode_count > 0) {
    try {
      const list = await apiFetch(`/api/animes/${encodeURIComponent(slug)}/episodes`);
      const first = list && list.episodes && list.episodes[0] ? list.episodes[0].ep_number : null;
      if (first !== null && first !== requestedEp) {
        setParam(first);
        await loadEpisode(slug, first);
        return;
      }
    } catch (e) { /* lanjut ke tampilan tanpa episode */ }
  }

  currentAnime = anime;
  allEpisodes = [];

  // Info halaman
  document.title = `${anime.title} | Otakux`;
  setText("player-anime-title", anime.title);
  const bAnime = document.getElementById("breadcrumb-anime");
  if (bAnime) bAnime.innerHTML = `<a href="detail.html?slug=${slug}">${escapeHtml(anime.title)}</a>`;
  setText("breadcrumb-ep", "Info");
  setText("synopsis-text", anime.synopsis || "Tidak ada sinopsis tersedia.");

  const metaEl = document.getElementById("player-meta");
  if (metaEl) {
    metaEl.innerHTML = `
      <span class="badge ${anime.status === 'Completed' ? 'badge-completed' : 'badge-ongoing'}">${escapeHtml(anime.status || 'Ongoing')}</span>
      ${anime.genre ? `<span style="font-size:.82rem;color:var(--clr-text-muted)">${escapeHtml(anime.genre)}</span>` : ''}
      ${anime.score > 0 ? `<span class="hero-score" style="font-size:.9rem">⭐ ${escapeHtml(anime.score)}</span>` : ''}
      ${anime.total_eps ? `<span style="font-size:.82rem;color:var(--clr-text-muted)">${escapeHtml(anime.total_eps)} episode (data AniList)</span>` : ''}
    `;
  }

  // Tombol episode sebelumnya/selanjutnya dimatikan
  renderNavButtons({ prev: null, next: null }, slug);

  // Toolbar server tidak relevan tanpa video
  const toolbar = document.querySelector(".video-toolbar");
  if (toolbar) toolbar.style.display = "none";

  // Sidebar
  setText("episode-count", "0 Episode");
  const epList = document.getElementById("episode-list");
  if (epList) {
    epList.innerHTML = '<p style="padding:20px;text-align:center;color:var(--clr-text-muted);font-size:.85rem">Belum ada episode di Otakux.</p>';
  }

  // Area video: trailer resmi kalau ada
  const trailer = trailerInfo(extras && extras.trailer);
  if (trailer) {
    wrapper.innerHTML = `
      <iframe
        id="main-player-frame"
        src="${trailer.embed}"
        title="Trailer ${escapeHtml(anime.title)}"
        allowfullscreen="true"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        referrerpolicy="strict-origin-when-cross-origin"
        loading="lazy">
      </iframe>
    `;
  } else {
    wrapper.innerHTML = `
      <div class="video-placeholder">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
          <path d="M15 10l4.553-2.276A1 1 0 0121 8.723v6.554a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2z"/>
        </svg>
        <p>Episode belum tersedia di Otakux</p>
        <p style="font-size:.8rem;color:var(--clr-text-muted)">Anime ini belum punya trailer resmi.</p>
      </div>
    `;
  }

  loadAnimeStats(slug);
  loadAnimeComments(slug, null);
  recordAnimeView(slug);
}

// ─────────────────────────────────────────────
//  SYNOPSIS TOGGLE
// ─────────────────────────────────────────────

function setupSynopsisToggle() {
  const btn = document.getElementById("synopsis-toggle");
  const text = document.getElementById("synopsis-text");
  if (!btn || !text) return;

  text.classList.add("collapsed");
  btn.textContent = "Tampilkan Lebih";

  btn.addEventListener("click", () => {
    const isCollapsed = text.classList.contains("collapsed");
    text.classList.toggle("collapsed", !isCollapsed);
    text.classList.toggle("expanded", isCollapsed);
    btn.textContent = isCollapsed ? "Tampilkan Lebih Sedikit" : "Tampilkan Lebih";
  });
}

// ─────────────────────────────────────────────
//  NAVBAR MOBILE
// ─────────────────────────────────────────────

function setupNavbar() {
  const toggle = document.getElementById("menu-toggle");
  const nav = document.getElementById("main-nav");
  if (!toggle || !nav) return;
  toggle.addEventListener("click", () => {
    nav.classList.toggle("open");
    toggle.textContent = nav.classList.contains("open") ? "✕" : "☰";
  });
}

// ─────────────────────────────────────────────
//  KEYBOARD SHORTCUT
// ─────────────────────────────────────────────

function setupKeyboard() {
  document.addEventListener("keydown", (e) => {
    // Jangan intercept jika sedang mengetik di input
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

    const { slug } = getParams();
    const eps = allEpisodes.map(e => e.ep_number);
    const idx = eps.indexOf(currentEpNumber);

    if (e.key === "ArrowRight" || e.key === "n") {
      // Episode selanjutnya
      if (idx < eps.length - 1) {
        setParam(eps[idx + 1]);
        loadEpisode(slug, eps[idx + 1]);
      }
    } else if (e.key === "ArrowLeft" || e.key === "p") {
      // Episode sebelumnya
      if (idx > 0) {
        setParam(eps[idx - 1]);
        loadEpisode(slug, eps[idx - 1]);
      }
    }
  });
}

// ─────────────────────────────────────────────
//  INIT
// ─────────────────────────────────────────────

async function initPlayer() {
  setupNavbar();
  setupSynopsisToggle();
  setupKeyboard();

  // Sinkronkan preferensi kecepatan putar yang tersimpan
  const speedBtn = document.getElementById("btn-playback-speed");
  if (speedBtn) {
    speedBtn.innerHTML = `⚡ ${currentPlaybackRate === 1.0 ? '1.0x' : currentPlaybackRate + 'x'}`;
  }
  document.querySelectorAll(".speed-opt, .in-speed-btn").forEach(btn => {
    const btnSpeed = parseFloat(btn.getAttribute("data-speed"));
    if (Math.abs(btnSpeed - currentPlaybackRate) < 0.01) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  const { slug, ep } = getParams();

  if (!slug) {
    const wrapper = document.getElementById("video-wrapper");
    if (wrapper) {
      wrapper.innerHTML = `
        <div class="video-placeholder">
          <p>Parameter anime tidak ditemukan.</p>
          <a href="index.html" style="color:var(--clr-primary);margin-top:12px;font-size:.85rem">← Kembali ke Beranda</a>
        </div>
      `;
    }
    return;
  }

  currentEpNumber = ep;
  await loadEpisode(slug, ep);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initPlayer);
} else {
  initPlayer();
}

// ─────────────────────────────────────────────
//  STATS, LIKE, BOOKMARK, SHARE & KOMENTAR
// ─────────────────────────────────────────────
let currentAnimeStats = { likes: 0, views: 0 };
let currentAnimeSlug = "";

function updateLikeButtonUI(isLiked, count) {
  const btn = document.getElementById("btn-like-anime");
  const countEl = document.getElementById("label-like-count");
  if (btn) {
    if (isLiked) btn.classList.add("liked");
    else btn.classList.remove("liked");
  }
  if (countEl) countEl.textContent = `Suka (${count || 0})`;
}

function updateFavButtonUI(isFav) {
  const btn = document.getElementById("btn-fav-anime");
  const label = document.getElementById("label-fav");
  if (btn) {
    if (isFav) btn.classList.add("favorited");
    else btn.classList.remove("favorited");
  }
  if (label) label.textContent = isFav ? "Tersimpan" : "Favorit";
}

async function loadAnimeStats(slug) {
  currentAnimeSlug = slug;
  try {
    const res = await fetch(`${API_BASE}/api/animes/${encodeURIComponent(slug)}/stats`, {
      headers: { "ngrok-skip-browser-warning": "true" }
    });
    if (!res.ok) return;
    const json = await res.json();
    if (json.data) {
      currentAnimeStats = json.data;
      const viewsEl = document.getElementById("views-count-text");
      if (viewsEl) viewsEl.textContent = `${(currentAnimeStats.views || 0).toLocaleString()} Ditonton`;

      const likedKey = `otakux_liked_${slug}`;
      const isLiked = localStorage.getItem(likedKey) === "1";
      updateLikeButtonUI(isLiked, currentAnimeStats.likes);
    }
  } catch (e) {
    console.warn("Gagal load stats:", e);
  }

  // Cek bookmark status
  const favList = JSON.parse(localStorage.getItem("otakux_bookmarks") || "[]");
  updateFavButtonUI(favList.includes(slug));
}

async function recordAnimeView(slug) {
  try {
    fetch(`${API_BASE}/api/animes/${encodeURIComponent(slug)}/view`, {
      method: "POST",
      headers: { "ngrok-skip-browser-warning": "true" }
    }).catch(() => {});
  } catch (e) {}
}

async function toggleAnimeLike() {
  if (!currentAnimeSlug) return;
  const likedKey = `otakux_liked_${currentAnimeSlug}`;
  const wasLiked = localStorage.getItem(likedKey) === "1";
  const nowLiked = !wasLiked;

  localStorage.setItem(likedKey, nowLiked ? "1" : "0");
  const delta = nowLiked ? 1 : -1;
  currentAnimeStats.likes = Math.max(0, (currentAnimeStats.likes || 0) + delta);
  updateLikeButtonUI(nowLiked, currentAnimeStats.likes);

  if (typeof showToast === "function") {
    showToast(nowLiked ? "❤️ Anda menyukai anime ini!" : "Batal menyukai anime ini.");
  }

  try {
    const res = await fetch(`${API_BASE}/api/animes/${encodeURIComponent(currentAnimeSlug)}/like`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "true" },
      body: JSON.stringify({ is_like: nowLiked })
    });
    if (res.ok) {
      const json = await res.json();
      if (json.data && json.data.likes !== undefined) {
        currentAnimeStats.likes = json.data.likes;
        updateLikeButtonUI(nowLiked, currentAnimeStats.likes);
      }
    }
  } catch (e) {
    console.warn("Gagal kirim like:", e);
  }
}

function toggleAnimeBookmark() {
  if (!currentAnimeSlug) return;
  const animeObj = {
    slug: currentAnimeSlug,
    title: document.getElementById("player-anime-title")?.textContent || currentAnimeSlug,
    thumbnail: document.querySelector(".video-backdrop-blur")?.src || "icons/default_poster.svg"
  };

  if (typeof OtakuWatchlist !== "undefined") {
    const isNowFav = !OtakuWatchlist.isFavorite(currentAnimeSlug);
    OtakuWatchlist.toggleFavorite(animeObj);
    updateFavButtonUI(isNowFav);
  } else {
    let favList = JSON.parse(localStorage.getItem("otakux_bookmarks") || "[]");
    const idx = favList.indexOf(currentAnimeSlug);
    let isNowFav = false;
    if (idx > -1) {
      favList.splice(idx, 1);
    } else {
      favList.push(currentAnimeSlug);
      isNowFav = true;
    }
    localStorage.setItem("otakux_bookmarks", JSON.stringify(favList));
    updateFavButtonUI(isNowFav);

    if (typeof showToast === "function") {
      showToast(isNowFav ? "⭐ Ditambahkan ke Daftar Favorit!" : "Dihapus dari Daftar Favorit.");
    }
  }
}

function shareCurrentAnime() {
  const title = document.getElementById("player-anime-title")?.textContent || "Anime";
  const epText = document.getElementById("player-ep-title")?.textContent || "";
  const shareData = {
    title: `${title} | Otakux`,
    text: `Nonton streaming ${title} ${epText} di Otakux!`,
    url: window.location.href
  };

  if (navigator.share) {
    navigator.share(shareData).catch(() => {});
  } else {
    navigator.clipboard.writeText(window.location.href).then(() => {
      if (typeof showToast === "function") showToast("📋 Link berhasil disalin ke clipboard!");
      else alert("Link berhasil disalin!");
    });
  }
}

// ── KOMENTAR ──
async function loadAnimeComments(slug, epNumber) {
  const listEl = document.getElementById("comments-list");
  const badgeEl = document.getElementById("comments-badge");
  if (!listEl) return;

  // Restore saved username
  const savedName = localStorage.getItem("otakux_username") || "";
  const userInput = document.getElementById("comment-username");
  if (userInput && savedName) userInput.value = savedName;

  try {
    const url = epNumber 
      ? `${API_BASE}/api/animes/${encodeURIComponent(slug)}/comments?ep=${epNumber}`
      : `${API_BASE}/api/animes/${encodeURIComponent(slug)}/comments`;
    const res = await fetch(url, {
      headers: { "ngrok-skip-browser-warning": "true" }
    });
    if (!res.ok) throw new Error("Gagal load komentar");
    const json = await res.json();
    const comments = json.data || [];

    if (badgeEl) badgeEl.textContent = `(${comments.length})`;

    // Sinkronkan Danmaku dengan komentar penonton
    initDanmaku(comments);

    if (comments.length === 0) {
      listEl.innerHTML = `
        <div style="text-align:center;padding:25px;color:var(--clr-text-muted);font-size:0.85rem;">
          ✨ Belum ada komentar di episode ini. Jadilah yang pertama berkomentar!
        </div>
      `;
      return;
    }

    listEl.innerHTML = comments.map(c => `
      <div class="comment-item" id="comment-${c.id}">
        <div class="comment-avatar" style="background:${c.avatar_color || '#7c3aed'};">
          ${(c.username || 'O').charAt(0).toUpperCase()}
        </div>
        <div class="comment-body">
          <div class="comment-meta">
            <span class="comment-author">${escapeHtml(c.username || 'Otaku Fans')}</span>
            ${c.ep_number ? `<span class="comment-ep-badge">Eps ${c.ep_number}</span>` : ''}
            <span class="comment-time">${formatCommentTime(c.created_at)}</span>
          </div>
          <div class="comment-text">${typeof OtakuTimestamp !== "undefined" ? OtakuTimestamp.format(c.content) : escapeHtml(c.content)}</div>
          <div class="comment-actions">
            <button type="button" class="btn-like-comment" onclick="likeCommentItem(${c.id})">
              <span>👍</span> <span id="comment-like-${c.id}">${c.likes || 0}</span>
            </button>
          </div>
        </div>
      </div>
    `).join("");
  } catch (e) {
    if (listEl) {
      listEl.innerHTML = `<div style="text-align:center;padding:20px;color:var(--clr-error);font-size:0.85rem;">Gagal memuat komentar.</div>`;
    }
  }
}

async function submitNewComment() {
  if (!currentAnimeSlug) return;
  const userInput = document.getElementById("comment-username");
  const contentInput = document.getElementById("comment-content");
  if (!contentInput) return;

  const content = contentInput.value.trim();
  if (!content) {
    if (typeof showToast === "function") showToast("⚠️ Tulis komentar terlebih dahulu!");
    else alert("Tulis komentar terlebih dahulu!");
    contentInput.focus();
    return;
  }

  const username = (userInput && userInput.value.trim()) ? userInput.value.trim() : "Otaku Fans";
  localStorage.setItem("otakux_username", username);

  try {
    const res = await fetch(`${API_BASE}/api/animes/${encodeURIComponent(currentAnimeSlug)}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "true" },
      body: JSON.stringify({
        username: username,
        content: content,
        ep_number: currentEpNumber || null
      })
    });
    if (!res.ok) throw new Error("Gagal mengirim komentar");
    contentInput.value = "";
    if (typeof showToast === "function") showToast("🎉 Komentar berhasil diposting!");
    await loadAnimeComments(currentAnimeSlug, currentEpNumber);
  } catch (e) {
    alert("Gagal mengirim komentar: " + e.message);
  }
}

async function likeCommentItem(commentId) {
  const btn = document.getElementById(`comment-like-${commentId}`);
  try {
    const res = await fetch(`${API_BASE}/api/comments/${commentId}/like`, {
      method: "POST",
      headers: { "ngrok-skip-browser-warning": "true" }
    });
    if (res.ok) {
      const json = await res.json();
      if (btn && json.data && json.data.likes !== undefined) {
        btn.textContent = json.data.likes;
      }
    }
  } catch (e) {}
}

function formatCommentTime(dateStr) {
  if (!dateStr) return "Baru saja";
  try {
    const d = new Date(dateStr);
    const now = new Date();
    const diffSec = Math.floor((now - d) / 1000);
    if (diffSec < 60) return "Baru saja";
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)} mnt lalu`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} jam lalu`;
    return `${Math.floor(diffSec / 86400)} hari lalu`;
  } catch (e) {
    return dateStr;
  }
}

// ─────────────────────────────────────────────
//  LEWATI OPENING, ENDING & PICTURE-IN-PICTURE
// ─────────────────────────────────────────────

function skipIntro(seconds = 85) {
  const videoEl = document.querySelector("#video-wrapper video");
  if (videoEl) {
    videoEl.currentTime = Math.min((videoEl.duration || Infinity), (videoEl.currentTime || 0) + seconds);
    showToast(`⏩ Dilewati +${seconds}s (Opening Selesai)`);
    return;
  }
  const frame = document.querySelector("#video-wrapper iframe");
  if (frame && frame.contentWindow) {
    frame.contentWindow.postMessage({ type: 'SEEK_FORWARD', seconds: seconds }, '*');
    showToast(`⏩ Dilewati +${seconds}s (Opening Selesai)`);
  }
}

function skipEnding(seconds = 90) {
  const videoEl = document.querySelector("#video-wrapper video");
  if (videoEl) {
    videoEl.currentTime = Math.min((videoEl.duration || Infinity), (videoEl.currentTime || 0) + seconds);
    showToast(`⏭️ Dilewati +${seconds}s (Ending Selesai)`);
    return;
  }
  const frame = document.querySelector("#video-wrapper iframe");
  if (frame && frame.contentWindow) {
    frame.contentWindow.postMessage({ type: 'SEEK_FORWARD', seconds: seconds }, '*');
    showToast(`⏭️ Dilewati +${seconds}s (Ending Selesai)`);
  }
}

function togglePictureInPicture() {
  const videoEl = document.querySelector("#video-wrapper video");
  if (videoEl && document.pictureInPictureEnabled) {
    if (document.pictureInPictureElement) {
      document.exitPictureInPicture().catch(() => {});
      showToast("📺 PiP Dimatikan");
    } else {
      videoEl.requestPictureInPicture().then(() => {
        showToast("📺 Mode Layar Mengambang (PiP) Aktif");
      }).catch(() => {
        toggleFloatingInAppPlayer();
      });
    }
    return;
  }

  const frame = document.querySelector("#video-wrapper iframe");
  if (frame && frame.contentWindow) {
    frame.contentWindow.postMessage({ type: 'REQUEST_PIP' }, '*');
  }
  toggleFloatingInAppPlayer();
}

function toggleFloatingInAppPlayer() {
  const wrapper = document.getElementById("video-wrapper");
  if (!wrapper) return;
  wrapper.classList.toggle("mini-pip-mode");
  const isMini = wrapper.classList.contains("mini-pip-mode");
  showToast(isMini ? "📺 Mini Player Mengambang Aktif" : "📺 Kembali ke Mode Normal");
}

// ─────────────────────────────────────────────
//  DANMAKU / BULLET COMMENTS (DINONAKTIFKAN TOTAL)
// ─────────────────────────────────────────────

let danmakuEnabled = false;
let danmakuInterval = null;
let danmakuPool = [];

function initDanmaku(comments = []) {
  if (danmakuInterval) clearInterval(danmakuInterval);
  danmakuEnabled = false;
  const existing = document.getElementById("danmaku-container");
  if (existing) existing.remove();
}

function updateDanmakuUI() {
  const container = document.getElementById("danmaku-container");
  if (container) container.remove();
}

function toggleDanmaku() {
  danmakuEnabled = false;
  if (danmakuInterval) clearInterval(danmakuInterval);
}

function startDanmakuStream() {
  if (danmakuInterval) clearInterval(danmakuInterval);
  danmakuEnabled = false;
}

function spawnDanmaku(text, isMine = false) {
  // Dinonaktifkan total sesuai permintaan user
  return;
}

async function sendDanmakuComment() {
  return;
}


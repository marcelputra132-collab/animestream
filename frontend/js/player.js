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
  const res = await fetch(`${API_BASE}${endpoint}`);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const json = await res.json();
  return json.data;
}

function imgFallback(el) {
  el.src = `data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='80' height='50' viewBox='0 0 80 50'><rect fill='%231c1c2e' width='80' height='50'/><text x='50%25' y='50%25' font-family='sans-serif' font-size='10' fill='%236b6b8a' text-anchor='middle' dy='.3em'>No Image</text></svg>`;
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

const DEAD_STREAM_DOMAINS = ["solidfiles", "zippyshare", "racaty", "tusfiles", "mediafire", "acefile", "mega.nz", "mirrorace", "hxfile"];

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
    if (currentSrc.includes("/api/stream-proxy")) {
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
}

// ─────────────────────────────────────────────
//  VIDEO PLAYER
// ─────────────────────────────────────────────

let currentStreamUrl = "";

function reloadCurrentVideo() {
  if (currentStreamUrl) {
    loadVideoPlayer(currentStreamUrl, document.getElementById("player-ep-title")?.textContent, currentPreferredRes);
  }
}

function loadVideoPlayer(embedUrl, title, quality = currentPreferredRes) {
  const wrapper = document.getElementById("video-wrapper");
  if (!wrapper) return;

  const crunchyBtn = document.getElementById("btnCrunchyroll");
  if (crunchyBtn && title) {
    crunchyBtn.href = `https://www.crunchyroll.com/search?q=${encodeURIComponent(title)}`;
  }
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
        <p>Video tidak tersedia untuk episode ini</p>
        <p style="font-size:.8rem;color:var(--clr-text-muted)">Jalankan python backend/fix_video.py untuk memperbarui link.</p>
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
    if (url.includes("otakuwatch")) serverBadge.textContent = "OtakuWatch HD";
    else if (url.includes("desustream")) serverBadge.textContent = "DesuStream";
    else if (url.includes("mp4upload")) serverBadge.textContent = "MP4Upload";
    else if (url.includes("youtube")) serverBadge.textContent = "YouTube";
    else serverBadge.textContent = "Stream Server";
  }

  const isDirectVideo = url.endsWith(".mp4") || url.endsWith(".webm") || url.includes("googlevideo.com");
  if (isDirectVideo) {
    wrapper.innerHTML = `
      <video
        src="${url}"
        controls
        autoplay
        playsinline
        style="position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#000;"
      >
        Browser Anda tidak mendukung tag video HTML5.
      </video>
    `;
    const vEl = wrapper.querySelector("video");
    if (vEl) applyVideoQualityFilter(vEl, quality);
    return;
  }

  const ytMatch = url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
  let isYouTube = false;
  if (ytMatch) {
    isYouTube = true;
    url = `https://www.youtube.com/embed/${ytMatch[1]}?autoplay=1&rel=0`;
  }

  let iframeSrc = url;
  if (url.includes("desustream") || url.includes("otakuwatch")) {
    iframeSrc = `${API_BASE}/api/stream-proxy?url=${encodeURIComponent(url)}&quality=${quality || '720p'}&_t=${Date.now()}`;
  }

  // YouTube membutuhkan referrerpolicy 'strict-origin-when-cross-origin' agar tidak memunculkan Error 153
  const refPolicy = isYouTube ? "strict-origin-when-cross-origin" : "no-referrer";

  wrapper.innerHTML = `
    <iframe
      id="main-player-frame"
      src="${iframeSrc}"
      title="${title || 'Anime Player'}"
      allowfullscreen="true"
      webkitallowfullscreen="true"
      mozallowfullscreen="true"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
      referrerpolicy="${refPolicy}"
      loading="eager">
    </iframe>
  `;
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
    const rawTitle = anime.title || "";
    const baseTitle = rawTitle.split(/[:\-\(]/)[0].trim();
    if (!baseTitle || baseTitle.length < 3) return;

    const res = await fetch(`${API_BASE}/api/animes/search?q=${encodeURIComponent(baseTitle)}`);
    if (!res.ok) return;
    const json = await res.json();
    const hits = json.data || [];

    // Cari anime utama yang punya banyak episode
    const mainSeries = hits.find(h => {
      const isDiff = h.slug !== anime.slug;
      const hasManyEps = (h.total_eps && h.total_eps > 1) || h.slug === "black-clover" || (h.ep_count && h.ep_count > 1);
      return isDiff && hasManyEps;
    });

    if (mainSeries) {
      container.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;">
          <span style="font-size:1.6rem;">📺</span>
          <div>
            <div style="font-weight:600;color:#fff;">Tersedia Serial Utama Lengkap: <span style="color:var(--clr-primary);">${mainSeries.title}</span></div>
            <div style="font-size:0.82rem;color:var(--clr-text-muted);">Tonton seluruh episode lengkap tanpa terpotong (${mainSeries.total_eps || mainSeries.ep_count || 170} Episode).</div>
          </div>
        </div>
        <a href="player.html?slug=${mainSeries.slug}&ep=1" class="btn btn-primary" style="padding:7px 16px;font-size:0.85rem;white-space:nowrap;text-decoration:none;background:var(--clr-primary);color:#fff;border-radius:6px;display:inline-block;">Nonton Serial Utama ›</a>
      `;
      container.style.display = "flex";
      return;
    }

    // Jika ini adalah cuplikan tanpa episode nyata, tampilkan tombol scrape on-demand
    const isPreview = episode && (String(episode.id).startsWith("p-") || episode.duration === "Official HD");
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

function renderNavButtons(nav, slug) {
  const prevBtn = document.getElementById("btn-prev-ep");
  const nextBtn = document.getElementById("btn-next-ep");

  if (prevBtn) {
    if (nav.prev !== null && nav.prev !== undefined) {
      prevBtn.href = `player.html?slug=${slug}&ep=${nav.prev}`;
      prevBtn.classList.remove("disabled");
      prevBtn.removeAttribute("disabled");
    } else {
      prevBtn.href = "#";
      prevBtn.setAttribute("disabled", "true");
    }
  }

  if (nextBtn) {
    if (nav.next !== null && nav.next !== undefined) {
      nextBtn.href = `player.html?slug=${slug}&ep=${nav.next}`;
      nextBtn.classList.remove("disabled");
      nextBtn.removeAttribute("disabled");
    } else {
      nextBtn.href = "#";
      nextBtn.setAttribute("disabled", "true");
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
    <a
      href="player.html?slug=${animeSlug}&ep=${ep.ep_number}"
      class="ep-list-item ${ep.ep_number === currentEp ? 'active' : ''}"
      id="ep-item-${ep.ep_number}"
      onclick="handleEpClick(event, '${animeSlug}', ${ep.ep_number})"
    >
      <div class="ep-list-num">${ep.ep_number}</div>
      <div class="ep-list-info">
        <div class="ep-list-title">${ep.title || `Episode ${ep.ep_number}`}</div>
        ${ep.duration ? `<div class="ep-list-dur">⏱ ${ep.duration}</div>` : ''}
      </div>
      ${ep.ep_number === currentEp ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="color:var(--clr-primary);flex-shrink:0"><path d="M8 5v14l11-7z"/></svg>` : ''}
    </a>
  `).join('');

  // Scroll ke episode aktif
  const activeEl = document.getElementById(`ep-item-${currentEp}`);
  if (activeEl) {
    setTimeout(() => activeEl.scrollIntoView({ block: "center", behavior: "smooth" }), 300);
  }
}

// ─────────────────────────────────────────────
//  NAVIGASI EPISODE (IN-PAGE)
// ─────────────────────────────────────────────

async function handleEpClick(e, slug, epNumber) {
  e.preventDefault();
  if (epNumber === currentEpNumber) return;

  // Update URL tanpa reload
  setParam(epNumber);
  await loadEpisode(slug, epNumber);
}

async function loadEpisode(slug, epNumber) {
  // Loading state
  const wrapper = document.getElementById("video-wrapper");
  if (wrapper) {
    wrapper.innerHTML = '<div class="video-placeholder"><div class="spinner"></div><p style="margin-top:16px;color:var(--clr-text-muted)">Memuat video...</p></div>';
  }

  try {
    const data = await apiFetch(`/api/animes/${slug}/episodes/${epNumber}`);
    if (!data) return;

    currentEpNumber = epNumber;
    allEpisodes = data.all_episodes || allEpisodes;
    currentEpisodeData = data;
    currentQualities = data.qualities || [];

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

    // Update player
    loadVideoPlayer(chosenStreamUrl, data.episode?.title, chosenRes);
    renderPlayerInfo(data.anime, data.episode, data.navigation);
    renderSidebar(allEpisodes, currentEpNumber, slug);
    if (window.updateBreadcrumb) window.updateBreadcrumb(data.anime.title, slug, epNumber);

    // Update halaman title
    document.title = `${data.anime.title} - Episode ${epNumber} | AnimeStream`;

    // Scroll ke atas
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (e) {
    console.error("[Player] Gagal load episode:", e);
    // 404 = episode tidak ada di database (mis. anime hasil impor AniList)
    if (/\b404\b/.test(e.message)) {
      await showNoEpisodes(slug, epNumber);
      return;
    }
    if (wrapper) {
      wrapper.innerHTML = `
        <div class="video-placeholder">
          <p style="color:var(--clr-error)">⚠ Gagal memuat episode ${epNumber}</p>
          <p style="font-size:.8rem;color:var(--clr-text-muted)">${e.message}</p>
        </div>
      `;
    }
  }
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
  document.title = `${anime.title} | AnimeStream`;
  setText("player-anime-title", anime.title);
  setText("player-ep-title", "Episode belum tersedia di AnimeStream");
  setText("breadcrumb-anime", anime.title);
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
    epList.innerHTML = '<p style="padding:20px;text-align:center;color:var(--clr-text-muted);font-size:.85rem">Belum ada episode di AnimeStream.</p>';
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
        <p>Episode belum tersedia di AnimeStream</p>
        <p style="font-size:.8rem;color:var(--clr-text-muted)">Anime ini belum punya trailer resmi.</p>
      </div>
    `;
  }

  // Kotak "Tonton di platform resmi"
  const box = ensureWatchLinksBox();
  box.innerHTML = "";

  const heading = document.createElement("div");
  heading.style.cssText = "font-size:.9rem;font-weight:700;margin-bottom:6px;";
  heading.textContent = "Tonton di platform resmi";
  box.appendChild(heading);

  const note = document.createElement("p");
  note.style.cssText = "font-size:.8rem;color:var(--clr-text-muted);margin-bottom:10px;";
  note.textContent = trailer
    ? "Yang diputar di atas adalah trailer resmi. Episode lengkap bisa ditonton di platform berikut."
    : "Episode lengkap bisa ditonton di platform berikut.";
  box.appendChild(note);

  const row = document.createElement("div");
  row.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;";

  const seen = new Set();
  const links = (extras && extras.watch_links) || [];
  links.forEach(l => {
    const href = safeHttpUrl(l.url);
    if (!href || seen.has(href)) return;
    seen.add(href);
    row.appendChild(buildLinkButton(href, `▶ ${l.site}`));
  });
  if (trailer) row.appendChild(buildLinkButton(trailer.page, `🎬 Trailer di ${trailer.label}`));
  const infoHref = safeHttpUrl(extras && extras.anilist_url);
  if (infoHref) row.appendChild(buildLinkButton(infoHref, "ℹ Info di AniList"));

  if (row.children.length === 0) {
    note.textContent = "Belum ada link platform resmi untuk anime ini.";
  } else {
    box.appendChild(row);
  }
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

document.addEventListener("DOMContentLoaded", async () => {
  setupNavbar();
  setupSynopsisToggle();
  setupKeyboard();

  const { slug, ep } = getParams();

  if (!slug) {
    document.getElementById("video-wrapper").innerHTML = `
      <div class="video-placeholder">
        <p>Parameter anime tidak ditemukan.</p>
        <a href="index.html" style="color:var(--clr-primary);margin-top:12px;font-size:.85rem">← Kembali ke Beranda</a>
      </div>
    `;
    return;
  }

  currentEpNumber = ep;
  await loadEpisode(slug, ep);
});

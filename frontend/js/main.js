/**
 * main.js — JavaScript untuk halaman utama (index.html)
 * Menghubungkan ke Flask API dan merender daftar anime
 */

// ─────────────────────────────────────────────
//  KONFIGURASI
// ─────────────────────────────────────────────

const API_BASE = window.location.origin && window.location.origin.startsWith("http")
  ? window.location.origin
  : "http://localhost:5000";

// ─────────────────────────────────────────────
//  HELPER FUNCTIONS
// ─────────────────────────────────────────────

/**
 * Fetch data dari API dengan error handling.
 */
async function apiFetch(endpoint) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: { 'ngrok-skip-browser-warning': 'true' }
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${endpoint}`);
  const json = await res.json();
  return json.data;
}

/**
 * Format waktu relatif (e.g. "2 jam lalu")
 */
function timeAgo(dateStr) {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "Baru saja";
  if (diffMins < 60) return `${diffMins} menit lalu`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours} jam lalu`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays} hari lalu`;
}

/**
 * Buat thumbnail placeholder jika gambar gagal load
 */
function imgFallback(el) {
  if (el.dataset.fallbackApplied) return;
  el.dataset.fallbackApplied = "true";
  el.src = "icons/default_poster.svg";
}

/**
 * Tampilkan toast notifikasi
 */
function showToast(message, duration = 3000) {
  let toast = document.getElementById("toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toast";
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), duration);
}

// ─────────────────────────────────────────────
//  HERO SECTION
// ─────────────────────────────────────────────

let heroAnimes = [];
let heroIndex = 0;
let heroInterval = null;

function renderHero(anime) {
  const el = document.getElementById("hero-section");
  if (!el || !anime) return;

  el.innerHTML = `
    <div class="hero-bg">
      <img class="hero-bg-img" src="${anime.thumbnail || ''}" alt="${anime.title}" onerror="this.style.display='none'">
      <div class="hero-overlay"></div>
      <div class="hero-overlay-bottom"></div>
    </div>
    <div class="container hero-content">
      <div class="hero-badge">
        <span>✦</span>
        <span>${anime.status || 'Ongoing'}</span>
      </div>
      <h1 class="hero-title">${anime.title}</h1>
      <p class="hero-synopsis">${anime.synopsis || 'Tidak ada sinopsis.'}</p>
      <div class="hero-meta">
        <span class="hero-score">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
          ${anime.score || 'N/A'}
        </span>
        <span class="badge ${anime.status === 'Completed' ? 'badge-completed' : 'badge-ongoing'}">
          ${anime.status || 'Ongoing'}
        </span>
        <span class="hero-genre">${anime.genre || ''}</span>
        <span style="color:var(--clr-text-muted);font-size:.85rem;">${anime.total_eps || 0} Episodes</span>
      </div>
      <div class="hero-actions">
        <a href="player.html?slug=${anime.slug}&ep=1" class="btn btn-primary">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
          Tonton
        </a>
        <a href="detail.html?slug=${anime.slug}" class="btn btn-secondary">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg>
          Detail
        </a>
      </div>
    </div>
  `;
}

function startHeroRotation() {
  if (heroAnimes.length <= 1) return;
  heroInterval = setInterval(() => {
    heroIndex = (heroIndex + 1) % heroAnimes.length;
    renderHero(heroAnimes[heroIndex]);
  }, 6000);
}

// ─────────────────────────────────────────────
//  ANIME CARD
// ─────────────────────────────────────────────

function formatGenre(genre, status) {
  if (!genre || genre === "Tidak diketahui" || genre.trim() === "") {
    return status ? `${status} • Sub Indo` : "Anime Series";
  }
  const parts = genre.split(",").map(s => s.trim());
  if (parts.length > 2) {
    return parts.slice(0, 2).join(", ");
  }
  return genre;
}

function createAnimeCard(anime) {
  const a = document.createElement("a");
  a.href = `detail.html?slug=${anime.slug || anime.anime_slug}`;
  a.className = "anime-card animate-fade-up";
  const thumbUrl = (anime.thumbnail && anime.thumbnail.trim()) ? anime.thumbnail : "icons/default_poster.svg";
  const epCount = (anime.ep_count && anime.ep_count > 0) ? anime.ep_count : (anime.total_eps || 0);
  const epBadgeHtml = epCount > 0 ? `<span class="anime-card-ep-badge" style="background:#6c5ce7;color:#fff;font-weight:600;">🟢 ${epCount} Eps</span>` : '';

  a.innerHTML = `
    <div class="anime-card-thumb">
      <img src="${thumbUrl}" alt="${anime.title}" loading="lazy" onerror="imgFallback(this)">
      <div class="anime-card-overlay">
        <div class="anime-card-play">▶</div>
      </div>
      ${epBadgeHtml}
      ${anime.score > 0 ? `<span class="anime-card-score">⭐ ${anime.score}</span>` : ''}
    </div>
    <div class="anime-card-body">
      <div class="anime-card-title">${anime.title}</div>
      <div class="anime-card-genre">${formatGenre(anime.genre, anime.status)}</div>
    </div>
  `;
  return a;
}

function formatViews(v) {
  const num = Number(v) || 0;
  if (num >= 1000000) return (num / 1000000).toFixed(1) + "M views";
  if (num >= 1000) return (num / 1000).toFixed(1) + "K views";
  return num > 0 ? (num + " views") : "520.3K views";
}

function createHotAnimeCard(anime, rank) {
  const a = document.createElement("a");
  a.href = `detail.html?slug=${anime.slug || anime.anime_slug}`;
  const isChamp = rank === 1;
  a.className = isChamp ? "hot-card hot-card-champion animate-fade-up" : "hot-card animate-fade-up";
  const thumbUrl = (anime.thumbnail && anime.thumbnail.trim()) ? anime.thumbnail : "icons/default_poster.svg";
  const rankClass = rank === 2 ? "hot-rank-2" : rank === 3 ? "hot-rank-3" : "hot-rank-other";
  
  const epCount = (anime.ep_count && anime.ep_count > 0) ? anime.ep_count : (anime.total_eps || 1);
  const epsText = `🟢 ${epCount} Eps`;
  
  const scoreVal = (anime.score && anime.score > 0) ? Number(anime.score).toFixed(2) : "8.50";
  const viewsText = formatViews(anime.views || 520300);

  // Badge nomor peringkat — No. 1 super mencolok dengan mahkota emas & api
  const rankBadgeHtml = isChamp 
    ? `<div class="hot-champion-badge">👑 #1 TER-HOT</div>`
    : `<span class="hot-rank-badge ${rankClass}">#${rank}</span>`;

  a.innerHTML = `
    <div class="hot-card-thumb">
      <img src="${thumbUrl}" alt="${anime.title}" loading="lazy" onerror="imgFallback(this)">
      <div class="hot-card-gradient"></div>
      ${rankBadgeHtml}
      <span class="hot-score-badge">★ ${scoreVal}</span>
      <div class="hot-thumb-meta">
        <span class="hot-ep-badge">${epsText}</span>
        <div class="hot-views-count">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
          </svg>
          <span>${viewsText}</span>
        </div>
      </div>
    </div>
    <div class="hot-card-info">
      <div class="hot-card-title ${isChamp ? 'hot-title-champ' : ''}" title="${anime.title}">
        ${isChamp ? '🔥 ' : ''}${anime.title}
      </div>
      <div class="hot-card-genre">${formatGenre(anime.genre, anime.status)}</div>
    </div>
  `;
  return a;
}

// ─────────────────────────────────────────────
//  SKELETON LOADER
// ─────────────────────────────────────────────

function renderSkeletons(container, count = 6) {
  if (!container) return;
  container.innerHTML = Array.from({ length: count }, () => `
    <div class="skeleton-card">
      <div class="skeleton-poster skeleton-shimmer"></div>
      <div class="skeleton-info">
        <div class="skeleton-line skeleton-shimmer"></div>
        <div class="skeleton-line sm skeleton-shimmer"></div>
      </div>
    </div>
  `).join('');
}

// ─────────────────────────────────────────────
//  LATEST EPISODE ITEM
// ─────────────────────────────────────────────

function createEpisodeItem(ep) {
  const div = document.createElement("a");
  div.href = `player.html?slug=${ep.anime_slug}&ep=${ep.ep_number}`;
  div.className = "episode-item";
  const thumbUrl = (ep.thumbnail && ep.thumbnail.trim()) ? ep.thumbnail : "icons/default_poster.svg";

  div.innerHTML = `
    <div class="episode-item-thumb">
      <img src="${thumbUrl}" alt="${ep.anime_title}" loading="lazy" onerror="imgFallback(this)">
      <div class="episode-item-play">▶</div>
      <span class="episode-item-badge">Ep ${ep.ep_number}</span>
    </div>
    <div class="episode-item-info">
      <div class="episode-item-anime" title="${ep.anime_title || ''}">${ep.anime_title || ''}</div>
    </div>
  `;
  return div;
}

// ─────────────────────────────────────────────
//  RENDER FUNCTIONS
// ─────────────────────────────────────────────

async function loadHero() {
  try {
    const animes = await apiFetch("/api/animes/latest?limit=5");
    if (!animes || animes.length === 0) return;
    heroAnimes = animes;
    heroIndex = 0;
    renderHero(heroAnimes[0]);
    startHeroRotation();
  } catch (e) {
    console.error("[Hero] Gagal load:", e);
  }
}

async function loadPopularAnimes() {
  const grid = document.getElementById("popular-anime-grid");
  if (!grid) return;
  renderSkeletons(grid, 6);
  try {
    const animes = await apiFetch("/api/animes/popular?limit=18");
    grid.innerHTML = "";
    if (!animes || animes.length === 0) {
      grid.innerHTML = '<p class="empty-state">Belum ada hot anime.</p>';
      return;
    }
    const seen = new Set();
    let rank = 1;
    animes.forEach(a => {
      const key = (a.title || "").toLowerCase().replace(/[^a-z0-9]/g, "");
      const normKey = (key.includes("tokyorevengers") && (key.includes("santensensou") || key.includes("season4") || key.includes("s4"))) ? "tokyorevengerss4" : key;
      if (seen.has(normKey)) return;
      seen.add(normKey);
      grid.appendChild(createHotAnimeCard(a, rank));
      rank++;
    });
  } catch (e) {
    grid.innerHTML = '<p class="empty-state error-state">⚠ Gagal memuat hot anime.</p>';
    console.error("[Hot Animes] Gagal:", e);
  }
}

async function loadLatestAnimes() {
  const grid = document.getElementById("latest-anime-grid");
  if (!grid) return;
  renderSkeletons(grid, 6);
  try {
    const animes = await apiFetch("/api/animes/latest?limit=12");
    grid.innerHTML = "";
    if (!animes || animes.length === 0) {
      grid.innerHTML = '<p class="empty-state">Belum ada anime. Jalankan scraper terlebih dahulu.</p>';
      return;
    }
    animes.forEach(a => grid.appendChild(createAnimeCard(a)));
  } catch (e) {
    grid.innerHTML = '<p class="empty-state error-state">⚠ Gagal memuat anime. Pastikan server backend berjalan.</p>';
    console.error("[Latest Animes] Gagal:", e);
  }
}

async function loadCompletedAnimes() {
  const grid = document.getElementById("completed-anime-grid");
  if (!grid) return;
  renderSkeletons(grid, 6);
  try {
    const animes = await apiFetch("/api/animes/completed?limit=18");
    grid.innerHTML = "";
    if (!animes || animes.length === 0) {
      grid.innerHTML = '<p class="empty-state">Belum ada anime tamat.</p>';
      return;
    }
    animes.forEach(a => grid.appendChild(createAnimeCard(a)));
  } catch (e) {
    grid.innerHTML = '<p class="empty-state error-state">⚠ Gagal memuat anime tamat.</p>';
    console.error("[Completed Animes] Gagal:", e);
  }
}

async function loadStats() {
  const textEl = document.getElementById("total-playable-text");
  if (!textEl) return;
  try {
    const stats = await apiFetch("/api/stats");
    if (stats && stats.total_playable) {
      textEl.textContent = `${stats.total_playable.toLocaleString('id-ID')}+ Judul Anime`;
    }
  } catch (e) {
    // Keep fallback text
  }
}

let rawOngoingEpisodes = [];

const DONGHUA_KEYWORDS = [
  'donghua', 'soul of light', 'souloflight', 'i am ying tai', 'iamyingtai', 'embers',
  'soul land', 'soulland', 'battle through', 'perfect world', 'swallowed star',
  'shrouding the heavens', 'renegade immortal', 'martial universe', 'great ruler',
  'against the gods', 'tales of demons', 'apotheosis', 'bai lian cheng shen',
  'a will eternal', 'yi nian yong heng', 'stellar transformation', 'martial peak',
  'lord xue ying', 'peerless martial', 'supreme god', 'spirit sword', 'wan jie',
  'wu dong qian kun', 'fanren xiu xian', "mortal's journey", 'thousand autumns',
  'tian guan ci fu', 'mo dao zu shi', 'demonic cultivation', 'shiguang dailiren',
  'quanzhi fashi', 'quanzhi gaoshou', "king's avatar", 'cultivation', 'ancient vengeance',
  'divine manifestation', 'forty millenniums'
];

function isDonghuaAnime(item) {
  if (!item) return false;
  const t = (item.anime_title || item.title || "").toLowerCase();
  const s = (item.anime_slug || item.slug || "").toLowerCase();
  const g = (item.genre || "").toLowerCase();
  const combined = `${t} ${s} ${g}`;
  return DONGHUA_KEYWORDS.some(kw => combined.includes(kw));
}

function filterOngoing(type, btn) {
  const list = document.getElementById("latest-episodes-list");
  if (!list || !rawOngoingEpisodes.length) return;
  list.innerHTML = "";
  rawOngoingEpisodes.forEach(ep => list.appendChild(createEpisodeItem(ep)));
}

async function loadLatestEpisodes() {
  const list = document.getElementById("latest-episodes-list");
  if (!list) return;
  list.innerHTML = '<div class="spinner" style="margin:24px auto"></div>';
  try {
    const episodes = await apiFetch("/api/episodes/latest?limit=40");
    list.innerHTML = "";
    if (!episodes || episodes.length === 0) {
      list.innerHTML = '<p class="empty-state">Belum ada episode terbaru.</p>';
      return;
    }
    const seenAnime = new Set();
    rawOngoingEpisodes = [];
    episodes.forEach(ep => {
      // Tolak semua konten Donghua (hanya terima anime Jepang)
      if (isDonghuaAnime(ep)) return;

      const key = (ep.anime_title || "").toLowerCase().replace(/[^a-z0-9]/g, "");
      const normKey = (key.includes("tokyorevengers") && (key.includes("santensensou") || key.includes("season4") || key.includes("s4"))) ? "tokyorevengerss4" : key;
      if (seenAnime.has(normKey)) return;
      seenAnime.add(normKey);
      rawOngoingEpisodes.push(ep);
    });
    rawOngoingEpisodes.forEach(ep => {
      list.appendChild(createEpisodeItem(ep));
    });
  } catch (e) {
    list.innerHTML = '<p class="empty-state">Gagal memuat episode terbaru.</p>';
    console.error("[Latest Episodes] Gagal:", e);
  }
}

// ─────────────────────────────────────────────
//  SEARCH
// ─────────────────────────────────────────────

let searchTimeout = null;

function setupSearch() {
  const inputs = document.querySelectorAll(".search-input");
  inputs.forEach(input => {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const q = input.value.trim();
        if (q) window.location.href = `search.html?q=${encodeURIComponent(q)}`;
      }
    });

    input.addEventListener("input", () => {
      clearTimeout(searchTimeout);
      const q = input.value.trim();
      if (!q || q.length < 2) {
        hideSearchDrop();
        return;
      }
      searchTimeout = setTimeout(() => quickSearch(q), 350);
    });
  });

  // Close search drop on outside click
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search-bar") && !e.target.closest(".search-drop")) {
      hideSearchDrop();
    }
  });
}

async function quickSearch(q) {
  try {
    const results = await apiFetch(`/api/animes/search?q=${encodeURIComponent(q)}`);
    renderSearchDrop(results, q);
  } catch (e) { /* silent */ }
}

function renderSearchDrop(results, query) {
  let drop = document.getElementById("search-drop");
  if (!drop) {
    drop = document.createElement("div");
    drop.id = "search-drop";
    drop.className = "search-drop";
    drop.style.cssText = `
      position:absolute;top:100%;left:0;right:0;margin-top:8px;
      background:var(--clr-bg-elevated);border:1px solid var(--clr-border);
      border-radius:var(--radius-md);box-shadow:var(--shadow-elevated);
      max-height:320px;overflow-y:auto;z-index:200;
    `;
    const searchBar = document.querySelector(".search-bar");
    if (searchBar) {
      searchBar.style.position = "relative";
      searchBar.appendChild(drop);
    }
  }

  if (!results || results.length === 0) {
    drop.innerHTML = `<p style="padding:16px;color:var(--clr-text-muted);font-size:.85rem;text-align:center">Tidak ditemukan: "${query}"</p>`;
    return;
  }

  drop.innerHTML = results.slice(0, 7).map(a => `
    <a href="player.html?slug=${a.slug}&ep=1" style="
      display:flex;align-items:center;gap:12px;
      padding:10px 14px;border-bottom:1px solid var(--clr-border);
      transition:background .15s;
    " onmouseenter="this.style.background='var(--clr-surface)'"
       onmouseleave="this.style.background='transparent'">
      <img src="${a.thumbnail || ''}" onerror="imgFallback(this)" style="width:38px;height:52px;object-fit:cover;border-radius:4px;flex-shrink:0">
      <div style="min-width:0;flex:1">
        <div style="font-size:.85rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${a.title}</div>
        <div style="font-size:.72rem;color:var(--clr-text-muted);margin-top:2px;">
          ${a.ep_count ? `<span style="color:#00b894;font-weight:600;">🟢 ${a.ep_count} Episode Siap Tonton</span>` : `${a.genre || ''} • ${a.total_eps || 0} eps`}
        </div>
      </div>
    </a>
  `).join('') + (results.length > 7 ? `
    <a href="search.html?q=${encodeURIComponent(query)}" style="display:block;padding:10px;text-align:center;font-size:.82rem;color:var(--clr-primary);border-top:1px solid var(--clr-border)">
      Lihat semua ${results.length} hasil →
    </a>
  ` : '');
}

function hideSearchDrop() {
  const drop = document.getElementById("search-drop");
  if (drop) drop.innerHTML = "";
}

// ─────────────────────────────────────────────
//  NAVBAR MOBILE TOGGLE
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
//  PULL TO REFRESH (HP / MOBILE)
// ─────────────────────────────────────────────

function setupPullToRefresh() {
  let startY = 0;
  let currentY = 0;
  let isPulling = false;
  const pullEl = document.getElementById("pull-to-refresh");
  const pullIcon = document.getElementById("pull-icon");
  const pullText = document.getElementById("pull-text");
  if (!pullEl) return;

  window.addEventListener("touchstart", (e) => {
    if (window.scrollY <= 4) {
      startY = e.touches[0].clientY;
      isPulling = true;
    }
  }, { passive: true });

  window.addEventListener("touchmove", (e) => {
    if (!isPulling || window.scrollY > 4) return;
    currentY = e.touches[0].clientY;
    const diff = currentY - startY;
    if (diff > 10) {
      const topOffset = Math.min(diff * 0.4, 75);
      pullEl.style.top = `${topOffset}px`;
      if (topOffset >= 50) {
        if (pullIcon) pullIcon.style.transform = "rotate(180deg)";
        if (pullText) pullText.textContent = "Lepaskan untuk segarkan";
      } else {
        if (pullIcon) pullIcon.style.transform = "rotate(0deg)";
        if (pullText) pullText.textContent = "Tarik untuk segarkan";
      }
    }
  }, { passive: true });

  window.addEventListener("touchend", () => {
    if (!isPulling) return;
    isPulling = false;
    const currentTop = parseInt(pullEl.style.top || "-60", 10);
    if (currentTop >= 50) {
      if (pullIcon) {
        pullIcon.textContent = "🔄";
        pullIcon.style.display = "inline-block";
        pullIcon.style.animation = "spin 0.8s linear infinite";
      }
      if (pullText) pullText.textContent = "Menyegarkan...";
      pullEl.style.top = "65px";
      // Pemicu periksa episode terbaru di latar belakang
      fetch(`${API_BASE}/api/sync/latest?async=true`, {
        headers: { 'ngrok-skip-browser-warning': 'true' }
      }).catch(() => {});

      setTimeout(() => {
        window.location.reload();
      }, 350);
    } else {
      pullEl.style.top = "-60px";
      if (pullIcon) pullIcon.style.transform = "rotate(0deg)";
    }
  }, { passive: true });
}

async function loadContinueWatching() {
  const section = document.getElementById("continue-watching-section");
  const listEl = document.getElementById("continue-watching-list");
  if (!section || !listEl) return;

  try {
    let history = JSON.parse(localStorage.getItem("otakux_watch_history") || "[]");

    // Jika user login, sinkronkan dengan riwayat dari database server
    if (typeof OtakuAuth !== "undefined") {
      const user = OtakuAuth.getUser();
      if (user && user.id && (!history || history.length === 0)) {
        try {
          const res = await fetch(`${API_BASE}/api/user/${user.id}/history`, {
            headers: { 'ngrok-skip-browser-warning': 'true' }
          });
          const json = await res.json();
          if (json.success && Array.isArray(json.data) && json.data.length > 0) {
            history = json.data;
          }
        } catch (_) {}
      }
    }

    // Jika riwayat masih kosong di perangkat baru, ambil rekomendasi tontonan awal agar section tetap tampil estetik
    if (!Array.isArray(history) || history.length === 0) {
      try {
        const res = await fetch(`${API_BASE}/api/anime/popular?limit=6`, {
          headers: { 'ngrok-skip-browser-warning': 'true' }
        });
        const json = await res.json();
        if (json.success && Array.isArray(json.data) && json.data.length > 0) {
          history = json.data.slice(0, 6).map((a, idx) => ({
            anime_slug: a.slug,
            anime_title: a.title,
            anime_thumbnail: a.thumbnail,
            ep_number: (idx % 4) + 1,
            progress_percent: 50 + ((idx * 17) % 40)
          }));
        }
      } catch (_) {}
    }

    if (!history || history.length === 0) {
      section.style.display = "none";
      return;
    }

    section.style.display = "block";
    listEl.innerHTML = history.slice(0, 12).map(h => {
      // Hitung persentase progress bar merah
      let progress = 70;
      if (typeof h.progress_percent === "number") {
        progress = Math.min(95, Math.max(15, h.progress_percent));
      } else if (h.watch_seconds && h.duration) {
        progress = Math.min(95, Math.max(15, Math.round((h.watch_seconds / h.duration) * 100)));
      } else if (h.timestamp) {
        progress = 55 + (Math.abs(h.timestamp) % 35);
      }

      const epNum = h.ep_number || 1;
      const thumb = h.anime_thumbnail || 'icons/default_poster.svg';

      return `
        <a href="player.html?slug=${encodeURIComponent(h.anime_slug)}&ep=${epNum}" class="continue-watching-card" aria-label="Lanjut nonton ${h.anime_title} Episode ${epNum}">
          <div class="continue-thumb-wrap">
            <img src="${thumb}" alt="${h.anime_title}" loading="lazy" onerror="this.src='icons/default_poster.svg'">
            <div class="continue-thumb-overlay"></div>
            <span class="continue-badge-eps">Eps ${epNum}</span>
            <div class="continue-progress-bar">
              <div class="continue-progress-fill" style="width: ${progress}%;"></div>
            </div>
          </div>
          <div class="continue-anime-title">${h.anime_title}</div>
        </a>
      `;
    }).join("");
  } catch (e) {
    console.warn("[ContinueWatching] Error:", e);
    section.style.display = "none";
  }
}

// ─────────────────────────────────────────────
//  INIT
// ─────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  setupNavbar();
  setupSearch();
  setupPullToRefresh();
  loadStats();
  loadHero();
  loadContinueWatching();
  loadLatestEpisodes();
  loadPopularAnimes();
  loadLatestAnimes();
  loadCompletedAnimes();

  // Periksa otomatis update harian secara berkala di latar belakang
  setTimeout(() => {
    fetch(`${API_BASE}/api/sync/latest?async=true`, {
      headers: { 'ngrok-skip-browser-warning': 'true' }
    }).catch(() => {});
  }, 3000);
});

// ─────────────────────────────────────────────
//  GACHA ANIME ACAK (SURPRISE ME 🎲)
// ─────────────────────────────────────────────

let allPlayableAnimesCache = [];

async function openGachaModal() {
  const modal = document.getElementById("gacha-anime-modal");
  if (!modal) return;
  modal.style.display = "flex";
  await rollGachaAnime();
}

function closeGachaModal() {
  const modal = document.getElementById("gacha-anime-modal");
  if (modal) modal.style.display = "none";
}

async function rollGachaAnime() {
  const rollingState = document.getElementById("gacha-rolling-state");
  const resultState = document.getElementById("gacha-result-state");
  if (rollingState && resultState) {
    rollingState.style.display = "block";
    resultState.style.display = "none";
  }

  try {
    if (allPlayableAnimesCache.length === 0) {
      const animes = await apiFetch("/api/animes/popular");
      allPlayableAnimesCache = animes && animes.length ? animes : [];
    }

    if (allPlayableAnimesCache.length === 0) {
      allPlayableAnimesCache = await apiFetch("/api/animes/latest") || [];
    }

    // Delay 650ms untuk efek rolling dadu gacha
    await new Promise(r => setTimeout(r, 650));

    if (allPlayableAnimesCache.length === 0) {
      throw new Error("Daftar anime belum siap.");
    }

    const randomAnime = allPlayableAnimesCache[Math.floor(Math.random() * allPlayableAnimesCache.length)];
    const thumbUrl = (randomAnime.thumbnail && randomAnime.thumbnail.trim()) 
      ? randomAnime.thumbnail.trim() 
      : ((randomAnime.poster && randomAnime.poster.trim()) ? randomAnime.poster.trim() : "icons/default_poster.svg");

    if (rollingState && resultState) {
      rollingState.style.display = "none";
      resultState.style.display = "block";
      resultState.innerHTML = `
        <div style="font-size:0.8rem;text-transform:uppercase;letter-spacing:1px;color:#a78bfa;font-weight:700;">
          ✨ Rekomendasi Waifu Spesial Buatmu ✨
        </div>
        <img src="${thumbUrl}" alt="${randomAnime.title}" class="gacha-result-img" referrerpolicy="no-referrer" onerror="this.onerror=null;this.src='icons/default_poster.svg'">
        <h3 style="font-size:1.15rem;font-weight:800;margin:0 0 6px 0;color:#fff;">${randomAnime.title}</h3>
        <div style="display:flex;align-items:center;justify-content:center;gap:8px;font-size:0.8rem;margin-bottom:12px;">
          <span style="color:#f59e0b;font-weight:700;">⭐ ${randomAnime.score || '8.5'}</span>
          <span style="color:var(--text-muted);">•</span>
          <span style="color:#06b6d4;font-weight:600;">${randomAnime.genre ? randomAnime.genre.split(',').slice(0, 2).join(', ') : (randomAnime.type || 'TV Series')}</span>
          <span style="color:var(--text-muted);">•</span>
          <span style="color:#10b981;font-weight:600;">${randomAnime.status || 'Tersedia'}</span>
        </div>
        <p style="font-size:0.8rem;color:#cbd5e1;line-height:1.45;margin-bottom:20px;max-height:65px;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;">
          ${randomAnime.synopsis || 'Anime seru pilihan khusus untuk menemani maraton akhir pekanmu! Tonton langsung episode lengkapnya.'}
        </p>
        <div style="display:flex;gap:10px;justify-content:center;">
          <button type="button" class="btn" style="background:rgba(255,255,255,0.1);color:#fff;border:1px solid rgba(255,255,255,0.2);border-radius:12px;padding:9px 16px;cursor:pointer;" onclick="rollGachaAnime()">
            🎲 Acak Lagi
          </button>
          <a href="detail.html?slug=${encodeURIComponent(randomAnime.slug)}" class="btn" style="background:linear-gradient(135deg, #7c3aed, #06b6d4);color:#fff;font-weight:700;border:none;border-radius:12px;padding:9px 20px;text-decoration:none;box-shadow:0 4px 18px rgba(124,58,237,0.5);">
            ▶ Nonton Sekarang
          </a>
        </div>
      `;
    }
  } catch(e) {
    if (rollingState && resultState) {
      rollingState.style.display = "none";
      resultState.style.display = "block";
      resultState.innerHTML = `
        <p style="color:#ef4444;margin:20px 0;">Gagal mengacak anime. Coba lagi!</p>
        <button type="button" class="btn-gacha-glow" onclick="rollGachaAnime()">Coba Lagi 🎲</button>
      `;
    }
  }
}

// ─────────────────────────────────────────────
//  MASKOT WAIFU INTERAKTIF DENGAN KUTIPAN KATA
// ─────────────────────────────────────────────

const WAIFU_QUOTES = [
  "Konnichiwa, Senpai! Selamat maraton di Otakux ✨",
  "Senpai, sudah coba fitur Lewati Opening di player? Cepat banget lho! ⏩",
  "Bingung mau nonton apa? Coba ketuk tombol Acak Anime 🎲",
  "Jangan lupa makan & minum air sambil maraton ya, Senpai! 🍜",
  "Setiap nonton video kamu dapat EXP buat naik Level lho! 🏆",
  "Komentar melayang (Danmaku) di player seru banget kan, Senpai? 💬",
  "Aku paling suka anime action dan isekai! Kalau Senpai suka apa? 🌸",
  "Terima kasih sudah selalu setia nonton di Otakux! ❤️"
];

let waifuQuoteIndex = 0;

function nextWaifuQuote() {
  const bubble = document.getElementById("waifu-speech-bubble");
  if (!bubble) return;

  waifuQuoteIndex = (waifuQuoteIndex + 1) % WAIFU_QUOTES.length;
  bubble.style.animation = "none";
  void bubble.offsetWidth;
  bubble.style.animation = "bubblePop 0.3s ease";
  bubble.textContent = WAIFU_QUOTES[waifuQuoteIndex];

  const avatar = document.querySelector(".waifu-avatar-btn");
  if (avatar) {
    avatar.style.transform = "scale(1.2) rotate(-8deg)";
    setTimeout(() => {
      avatar.style.transform = "none";
    }, 250);
  }
}


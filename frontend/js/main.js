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
  const res = await fetch(`${API_BASE}${endpoint}`);
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
  el.src = `data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='300' viewBox='0 0 200 300'><rect fill='%231c1c2e' width='200' height='300'/><text x='50%25' y='50%25' font-family='sans-serif' font-size='14' fill='%236b6b8a' text-anchor='middle' dy='.3em'>No Image</text></svg>`;
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
        <a href="player.html?slug=${anime.slug}&ep=1" class="btn btn-secondary">
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
  a.href = `player.html?slug=${anime.slug || anime.anime_slug}&ep=1`;
  a.className = "anime-card animate-fade-up";
  a.innerHTML = `
    <div class="anime-card-thumb">
      <img src="${anime.thumbnail || ''}" alt="${anime.title}" loading="lazy" onerror="imgFallback(this)">
      <div class="anime-card-overlay">
        <div class="anime-card-play">▶</div>
      </div>
      ${anime.total_eps ? `<span class="anime-card-ep-badge">${anime.total_eps} Eps</span>` : ''}
      ${anime.score > 0 ? `<span class="anime-card-score">⭐ ${anime.score}</span>` : ''}
    </div>
    <div class="anime-card-body">
      <div class="anime-card-title">${anime.title}</div>
      <div class="anime-card-genre">${formatGenre(anime.genre, anime.status)}</div>
    </div>
  `;
  return a;
}

// ─────────────────────────────────────────────
//  SKELETON LOADER
// ─────────────────────────────────────────────

function renderSkeletons(container, count = 6) {
  container.innerHTML = Array.from({ length: count }, () => `
    <div class="skeleton-card">
      <div class="skeleton skeleton-thumb"></div>
      <div style="padding:12px 8px;display:flex;flex-direction:column;gap:8px;">
        <div class="skeleton" style="height:14px;border-radius:4px;width:90%"></div>
        <div class="skeleton" style="height:11px;border-radius:4px;width:60%"></div>
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
  div.innerHTML = `
    <div class="episode-item-thumb">
      <img src="${ep.thumbnail || ''}" alt="${ep.anime_title}" loading="lazy" onerror="imgFallback(this)">
    </div>
    <div class="episode-item-info">
      <div class="episode-item-anime">${ep.anime_title || ''}</div>
      <div class="episode-item-ep">Episode ${ep.ep_number}</div>
      <div class="episode-item-time">${timeAgo(ep.created_at)}</div>
    </div>
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" style="color:var(--clr-text-muted);flex-shrink:0"><path d="M8 5v14l11-7z"/></svg>
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
      grid.innerHTML = '<p class="empty-state">Belum ada anime populer.</p>';
      return;
    }
    animes.forEach(a => grid.appendChild(createAnimeCard(a)));
  } catch (e) {
    grid.innerHTML = '<p class="empty-state error-state">⚠ Gagal memuat anime populer.</p>';
    console.error("[Popular Animes] Gagal:", e);
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

async function loadLatestEpisodes() {
  const list = document.getElementById("latest-episodes-list");
  if (!list) return;
  list.innerHTML = '<div class="spinner" style="margin:24px auto"></div>';
  try {
    const episodes = await apiFetch("/api/episodes/latest?limit=12");
    list.innerHTML = "";
    if (!episodes || episodes.length === 0) {
      list.innerHTML = '<p class="empty-state">Belum ada episode terbaru.</p>';
      return;
    }
    episodes.forEach(ep => list.appendChild(createEpisodeItem(ep)));
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
      setTimeout(() => {
        window.location.reload();
      }, 350);
    } else {
      pullEl.style.top = "-60px";
      if (pullIcon) pullIcon.style.transform = "rotate(0deg)";
    }
  }, { passive: true });
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
  loadPopularAnimes();
  loadLatestAnimes();
  loadCompletedAnimes();
  loadLatestEpisodes();
});

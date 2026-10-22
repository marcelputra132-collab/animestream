const CACHE_NAME = "otakux-v44";
const ASSETS_TO_CACHE = [
  "/index.html",
  "/detail.html",
  "/player.html",
  "/profile.html",
  "/search.html",
  "/genre.html",
  "/schedule.html",
  "/playerjs.js",
  "/css/style.css",
  "/js/main.js",
  "/js/player.js",
  "/js/auth.js",
  "/js/features.js",
  "/icons/default_poster.svg",
  "/icons/splash_waifu_transparent.webp",
  "/icons/splash_waifu_transparent.png",
  "/icons/otakux_icon_512.png",
  "/icons/otakux_icon_192.png",
  "/icons/otakux_icon_maskable.png",
  "/icons/otakux_logo.png",
  "/icons/app_logo.png",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable.png"
];

self.addEventListener("install", (e) => {
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((k) => {
          if (k !== CACHE_NAME) {
            return caches.delete(k);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Network-First: selalu ambil versi terbaru dari server!
self.addEventListener("fetch", (e) => {
  if (e.request.url.includes("/api/")) {
    return;
  }
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});

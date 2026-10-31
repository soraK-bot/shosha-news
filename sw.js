/* 商社就活ニュース 簡易サービスワーカー
   画面の枠組みはキャッシュして素早く開き、ニュースデータ(news.json)は常に最新を取りに行く。 */
var CACHE = "shosha-news-v6";
var SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icon.svg"];

self.addEventListener("install", function(e){
  e.waitUntil(caches.open(CACHE).then(function(c){ return c.addAll(SHELL); }).then(function(){ return self.skipWaiting(); }));
});

self.addEventListener("activate", function(e){
  e.waitUntil(caches.keys().then(function(keys){
    return Promise.all(keys.map(function(k){ if(k!==CACHE) return caches.delete(k); }));
  }).then(function(){ return self.clients.claim(); }));
});

self.addEventListener("fetch", function(e){
  var url = new URL(e.request.url);
  // ニュース・企業データは常にネット優先（最新を表示）
  if(url.pathname.indexOf("news.json") >= 0 || url.pathname.indexOf("companies.json") >= 0){
    e.respondWith(fetch(e.request).catch(function(){ return caches.match(e.request); }));
    return;
  }
  // それ以外はキャッシュ優先
  e.respondWith(caches.match(e.request).then(function(r){ return r || fetch(e.request); }));
});

/* 废品回收报价助手 - Service Worker v2.4 */

var CACHE_NAME = 'scrap-price-cache-v9';

// 安装时预缓存的关键资源
const PRECACHE_URLS = [
  'index.html',
  'manifest.json',
  'xlsx.full.min.js'
];

// 安装事件：预缓存关键静态资源
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(PRECACHE_URLS).catch(function(err) {
        // 外部 CDN 资源可能失败，不影响主功能
        console.log('SW precache warning:', err);
      });
    })
  );
  self.skipWaiting();
});

// 激活事件：清理旧缓存，并立即接管页面
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames.map(function(name) {
          if (name !== CACHE_NAME) {
            return caches.delete(name);
          }
        })
      );
    }).then(function() {
      // clients.claim 必须在 waitUntil 内，否则新 SW 不一定能立即接管已打开的页面
      return self.clients.claim();
    })
  );
});

// 判断是否为 prices.json 请求
function isPricesJson(url) {
  return url.includes('prices.json');
}

// 去掉查询参数（如 ?t=时间戳）得到稳定的缓存 key。
// 页面每次用带时间戳的 URL 请求以绕过 HTTP 缓存，若直接拿它做 key，
// 离线时 caches.match 永远匹配不到，兜底失效。
function cacheKey(request) {
  var url = new URL(request.url);
  url.search = '';
  return url.toString();
}

// 请求拦截
self.addEventListener('fetch', function(event) {
  // 只处理 GET 请求
  if (event.request.method !== 'GET') return;

  // 不缓存 chrome-extension 等协议
  if (!event.request.url.startsWith('http')) return;

  // prices.json 采用 Network First 策略
  if (isPricesJson(event.request.url)) {
    var key = cacheKey(event.request);
    event.respondWith(
      fetch(event.request).then(function(response) {
        if (response && response.status === 200) {
          var responseClone = response.clone();
          caches.open(CACHE_NAME).then(function(cache) {
            cache.put(key, responseClone);
          });
        }
        return response;
      }).catch(function() {
        // 网络失败时用缓存兜底（用规范化后的 key 匹配）
        return caches.match(key).then(function(cachedResponse) {
          return cachedResponse || new Response(JSON.stringify({ "categories": {} }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
          });
        });
      })
    );
    return;
  }

  // 其他文件：Cache First 策略
  event.respondWith(
    caches.match(event.request).then(function(cachedResponse) {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(event.request).then(function(response) {
        // 只缓存成功的响应，且不缓存 CDN 失败结果
        if (!response || response.status !== 200 || response.type !== 'basic') {
          return response;
        }
        var responseClone = response.clone();
        caches.open(CACHE_NAME).then(function(cache) {
          cache.put(event.request, responseClone);
        });
        return response;
      }).catch(function() {
        // 离线且无缓存时，对于 HTML 页面返回 fallback
        if (event.request.mode === 'navigate') {
          return caches.match('index.html');
        }
      });
    })
  );
});

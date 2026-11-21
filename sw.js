/* 废品回收报价助手 - Service Worker v3.0 */

var CACHE_NAME = 'scrap-price-cache-v21';

// 安装时预缓存的关键资源
const PRECACHE_URLS = [
  'index.html',
  'admin.html',
  'manifest.json',
  'icon.png',
  'xlsx.full.min.js',
  'quotes.json',
  'forecast.json'
];
// 安装事件：预缓存关键静态资源
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      // 逐个缓存而不是 addAll：单个文件失败不会拖累其它文件，
      // 并且 cache:'reload' 强制绕过 HTTP 缓存，避免把旧页面写进新版本的缓存。
      return Promise.all(PRECACHE_URLS.map(function(url) {
        return cache.add(new Request(url, { cache: 'reload' })).catch(function(err) {
          console.log('SW precache skip:', url, err);
        });
      }));
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

// 判断是否为需要「网络优先」的数据文件
function isPricesJson(url) {
  return url.includes('prices.json') || url.includes('quotes.json') || url.includes('forecast.json');
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
          if (cachedResponse) return cachedResponse;
          // 没有缓存时返回空结构：页面会识别为空数据，不会谎报同步成功
          var empty = (event.request.url.indexOf('quotes.json') >= 0 || event.request.url.indexOf('forecast.json') >= 0) ? {} : { "categories": {} };
          return new Response(JSON.stringify(empty), {
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

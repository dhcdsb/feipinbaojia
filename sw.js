/* 废品回收报价助手 - Service Worker v1.0 */

const CACHE_NAME = 'scrap-price-cache-v1';

// 安装时预缓存的关键资源
const PRECACHE_URLS = [
  'index.html',
  'manifest.json',
  'https://cdn.sheetjs.com/xlsx-0.20.0/package/dist/xlsx.full.min.js'
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

// 激活事件：清理旧缓存
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
    })
  );
  // 立即控制所有打开的页面
  return self.clients.claim();
});

// 判断是否为 prices.json 请求
function isPricesJson(url) {
  return url.includes('prices.json');
}

// 请求拦截
self.addEventListener('fetch', function(event) {
  // 只处理 GET 请求
  if (event.request.method !== 'GET') return;

  // 不缓存 chrome-extension 等协议
  if (!event.request.url.startsWith('http')) return;

  // prices.json 采用 Network First 策略
  if (isPricesJson(event.request.url)) {
    event.respondWith(
      fetch(event.request).then(function(response) {
        if (response && response.status === 200) {
          var responseClone = response.clone();
          caches.open(CACHE_NAME).then(function(cache) {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      }).catch(function() {
        // 网络失败时用缓存兜底
        return caches.match(event.request).then(function(cachedResponse) {
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
          return caches.match('.');
        }
      });
    })
  );
});

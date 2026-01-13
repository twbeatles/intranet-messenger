/**
 * Service Worker for Push Notifications
 * [v4.4] 성능 최적화 업데이트
 */

const CACHE_NAME = 'messenger-v4';
const STATIC_ASSETS = [
    '/',
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/js/notification.js',
    '/static/js/storage.js',
    '/static/js/socket.io.min.js',
    '/static/js/crypto-js.min.js'
];

// 설치
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            console.log('Service Worker: 캐시 저장');
            return cache.addAll(STATIC_ASSETS);
        })
    );
    self.skipWaiting();
});

// 활성화
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames
                    .filter(name => name !== CACHE_NAME)
                    .map(name => caches.delete(name))
            );
        })
    );
    self.clients.claim();
});

// [v4.4] 페치 - Stale-While-Revalidate 전략
self.addEventListener('fetch', event => {
    // API 요청은 항상 네트워크 사용
    if (event.request.url.includes('/api/') ||
        event.request.url.includes('/socket.io/')) {
        return;
    }

    // 정적 자원은 stale-while-revalidate 전략
    event.respondWith(
        caches.match(event.request).then(cachedResponse => {
            // 캐시가 있으면 즉시 반환하고 백그라운드에서 업데이트
            const fetchPromise = fetch(event.request).then(networkResponse => {
                if (networkResponse && networkResponse.status === 200) {
                    const responseClone = networkResponse.clone();
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, responseClone);
                    });
                }
                return networkResponse;
            }).catch(() => cachedResponse);  // 네트워크 실패 시 캐시 반환

            return cachedResponse || fetchPromise;
        })
    );
});

// 푸시 알림 (서버 푸시용 - 선택사항)
self.addEventListener('push', event => {
    if (!event.data) return;

    try {
        const data = event.data.json();

        const options = {
            body: data.body || '새 메시지가 있습니다.',
            icon: '/static/icon.png',
            badge: '/static/badge.png',
            tag: data.tag || 'notification',
            requireInteraction: false,
            data: {
                url: data.url || '/'
            }
        };

        event.waitUntil(
            self.registration.showNotification(data.title || '사내 메신저', options)
        );
    } catch (err) {
        console.error('푸시 알림 오류:', err);
    }
});

// 알림 클릭
self.addEventListener('notificationclick', event => {
    event.notification.close();

    const notificationData = event.notification.data || {};
    const urlToOpen = notificationData.url || '/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then(windowClients => {
                // 이미 열린 창이 있으면 포커스
                for (const client of windowClients) {
                    if (client.url.includes(self.location.origin) && 'focus' in client) {
                        return client.focus();
                    }
                }
                // 없으면 새 창 열기
                return clients.openWindow(urlToOpen);
            })
    );
});

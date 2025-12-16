/**
 * Service Worker for Push Notifications
 */

const CACHE_NAME = 'messenger-v3';
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

// 페치 - 네트워크 우선 전략
self.addEventListener('fetch', event => {
    // API 요청은 항상 네트워크 사용
    if (event.request.url.includes('/api/') ||
        event.request.url.includes('/socket.io/')) {
        return;
    }

    event.respondWith(
        fetch(event.request)
            .then(response => {
                // 성공하면 캐시에 저장
                if (response.status === 200) {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, responseClone);
                    });
                }
                return response;
            })
            .catch(() => {
                // 네트워크 실패 시 캐시에서 반환
                return caches.match(event.request);
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

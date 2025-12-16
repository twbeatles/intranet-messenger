/**
 * 로컬 스토리지 모듈
 * IndexedDB를 사용한 오프라인 메시지 캐싱
 */

const MessengerStorage = {
    db: null,
    DB_NAME: 'MessengerDB',
    DB_VERSION: 1,

    /**
     * IndexedDB 초기화
     */
    async init() {
        return new Promise((resolve, reject) => {
            if (!window.indexedDB) {
                console.log('IndexedDB를 지원하지 않습니다.');
                resolve(false);
                return;
            }

            const request = indexedDB.open(this.DB_NAME, this.DB_VERSION);

            request.onerror = () => {
                console.error('IndexedDB 열기 실패');
                resolve(false);
            };

            request.onsuccess = (event) => {
                this.db = event.target.result;
                console.log('IndexedDB 초기화 완료');
                resolve(true);
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;

                // 메시지 저장소
                if (!db.objectStoreNames.contains('messages')) {
                    const messageStore = db.createObjectStore('messages', { keyPath: 'id' });
                    messageStore.createIndex('room_id', 'room_id', { unique: false });
                    messageStore.createIndex('created_at', 'created_at', { unique: false });
                }

                // 대화방 저장소
                if (!db.objectStoreNames.contains('rooms')) {
                    db.createObjectStore('rooms', { keyPath: 'id' });
                }

                // 설정 저장소
                if (!db.objectStoreNames.contains('settings')) {
                    db.createObjectStore('settings', { keyPath: 'key' });
                }
            };
        });
    },

    /**
     * 메시지 캐싱
     */
    async cacheMessages(roomId, messages) {
        if (!this.db) return;

        return new Promise((resolve, reject) => {
            try {
                const transaction = this.db.transaction(['messages'], 'readwrite');
                const store = transaction.objectStore('messages');

                messages.forEach(msg => {
                    store.put({ ...msg, room_id: roomId });
                });

                transaction.oncomplete = () => resolve(true);
                transaction.onerror = () => reject(transaction.error);
            } catch (err) {
                console.error('메시지 캐싱 실패:', err);
                resolve(false);
            }
        });
    },

    /**
     * 캐시된 메시지 조회
     */
    async getCachedMessages(roomId, limit = 50) {
        if (!this.db) return [];

        return new Promise((resolve, reject) => {
            try {
                const transaction = this.db.transaction(['messages'], 'readonly');
                const store = transaction.objectStore('messages');
                const index = store.index('room_id');
                const request = index.getAll(roomId);

                request.onsuccess = () => {
                    const messages = request.result || [];
                    // 최신 메시지 limit개만
                    messages.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
                    resolve(messages.slice(-limit));
                };

                request.onerror = () => {
                    console.error('메시지 조회 실패');
                    resolve([]);
                };
            } catch (err) {
                console.error('메시지 조회 실패:', err);
                resolve([]);
            }
        });
    },

    /**
     * 대화방 캐싱
     */
    async cacheRooms(rooms) {
        if (!this.db) return;

        return new Promise((resolve, reject) => {
            try {
                const transaction = this.db.transaction(['rooms'], 'readwrite');
                const store = transaction.objectStore('rooms');

                rooms.forEach(room => {
                    store.put(room);
                });

                transaction.oncomplete = () => resolve(true);
                transaction.onerror = () => reject(transaction.error);
            } catch (err) {
                console.error('대화방 캐싱 실패:', err);
                resolve(false);
            }
        });
    },

    /**
     * 캐시된 대화방 조회
     */
    async getCachedRooms() {
        if (!this.db) return [];

        return new Promise((resolve, reject) => {
            try {
                const transaction = this.db.transaction(['rooms'], 'readonly');
                const store = transaction.objectStore('rooms');
                const request = store.getAll();

                request.onsuccess = () => {
                    resolve(request.result || []);
                };

                request.onerror = () => {
                    console.error('대화방 조회 실패');
                    resolve([]);
                };
            } catch (err) {
                console.error('대화방 조회 실패:', err);
                resolve([]);
            }
        });
    },

    /**
     * 설정 저장
     */
    async setSetting(key, value) {
        if (!this.db) return;

        return new Promise((resolve, reject) => {
            try {
                const transaction = this.db.transaction(['settings'], 'readwrite');
                const store = transaction.objectStore('settings');
                store.put({ key, value });

                transaction.oncomplete = () => resolve(true);
                transaction.onerror = () => reject(transaction.error);
            } catch (err) {
                console.error('설정 저장 실패:', err);
                resolve(false);
            }
        });
    },

    /**
     * 설정 조회
     */
    async getSetting(key, defaultValue = null) {
        if (!this.db) return defaultValue;

        return new Promise((resolve, reject) => {
            try {
                const transaction = this.db.transaction(['settings'], 'readonly');
                const store = transaction.objectStore('settings');
                const request = store.get(key);

                request.onsuccess = () => {
                    resolve(request.result ? request.result.value : defaultValue);
                };

                request.onerror = () => {
                    resolve(defaultValue);
                };
            } catch (err) {
                console.error('설정 조회 실패:', err);
                resolve(defaultValue);
            }
        });
    },

    /**
     * 캐시 정리 (오래된 메시지 삭제)
     */
    async cleanup(daysToKeep = 7) {
        if (!this.db) return;

        const cutoffDate = new Date();
        cutoffDate.setDate(cutoffDate.getDate() - daysToKeep);

        return new Promise((resolve, reject) => {
            try {
                const transaction = this.db.transaction(['messages'], 'readwrite');
                const store = transaction.objectStore('messages');
                const index = store.index('created_at');

                const range = IDBKeyRange.upperBound(cutoffDate.toISOString());
                const request = index.openCursor(range);

                request.onsuccess = (event) => {
                    const cursor = event.target.result;
                    if (cursor) {
                        store.delete(cursor.primaryKey);
                        cursor.continue();
                    }
                };

                transaction.oncomplete = () => {
                    console.log('오래된 캐시 정리 완료');
                    resolve(true);
                };

                transaction.onerror = () => reject(transaction.error);
            } catch (err) {
                console.error('캐시 정리 실패:', err);
                resolve(false);
            }
        });
    }
};

// 전역으로 내보내기
window.MessengerStorage = MessengerStorage;

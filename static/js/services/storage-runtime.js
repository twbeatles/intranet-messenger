/**
 * 로컬 스토리지 모듈
 * IndexedDB를 사용한 오프라인 메시지 캐싱
 */

// ============================================================================
// E2E 암호화 폴백 (crypto-js 기반)
// ============================================================================
var E2E = window.E2E || (function () {
    function constantTimeEqual(a, b) {
        if (typeof a !== 'string' || typeof b !== 'string') return false;
        if (a.length !== b.length) return false;
        var diff = 0;
        for (var i = 0; i < a.length; i++) {
            diff |= (a.charCodeAt(i) ^ b.charCodeAt(i));
        }
        return diff === 0;
    }

    function deriveKeys(passphrase, salt) {
        // 64 bytes derived, split into encKey/macKey (32 bytes each)
        var dk = CryptoJS.PBKDF2(passphrase, salt, {
            keySize: 16,
            iterations: 10000,
            hasher: CryptoJS.algo.SHA256
        });
        var encKey = CryptoJS.lib.WordArray.create(dk.words.slice(0, 8), 32);
        var macKey = CryptoJS.lib.WordArray.create(dk.words.slice(8, 16), 32);
        return { encKey: encKey, macKey: macKey };
    }

    function encryptV2(text, key) {
        if (typeof CryptoJS === 'undefined' || !key) return text;
        try {
            var salt = CryptoJS.lib.WordArray.random(16);
            var iv = CryptoJS.lib.WordArray.random(16);
            var keys = deriveKeys(key, salt);

            var encrypted = CryptoJS.AES.encrypt(text, keys.encKey, {
                iv: iv,
                mode: CryptoJS.mode.CBC,
                padding: CryptoJS.pad.Pkcs7
            });
            var ct = encrypted.ciphertext;

            var macData = salt.clone().concat(iv).concat(ct);
            var hmac = CryptoJS.HmacSHA256(macData, keys.macKey);

            var saltB64 = CryptoJS.enc.Base64.stringify(salt);
            var ivB64 = CryptoJS.enc.Base64.stringify(iv);
            var ctB64 = CryptoJS.enc.Base64.stringify(ct);
            var hmacB64 = CryptoJS.enc.Base64.stringify(hmac);
            return 'v2:' + saltB64 + ':' + ivB64 + ':' + ctB64 + ':' + hmacB64;
        } catch (e) {
            console.error('Encrypt v2 error:', e);
            return text;
        }
    }

    function decryptV2(payload, key) {
        if (typeof CryptoJS === 'undefined' || !key) return payload;
        try {
            var parts = payload.split(':');
            if (parts.length !== 5) return null;
            var salt = CryptoJS.enc.Base64.parse(parts[1]);
            var iv = CryptoJS.enc.Base64.parse(parts[2]);
            var ct = CryptoJS.enc.Base64.parse(parts[3]);
            var hmacB64 = parts[4];

            var keys = deriveKeys(key, salt);
            var macData = salt.clone().concat(iv).concat(ct);
            var expectedHmac = CryptoJS.HmacSHA256(macData, keys.macKey);
            var expectedB64 = CryptoJS.enc.Base64.stringify(expectedHmac);
            if (!constantTimeEqual(expectedB64, hmacB64)) {
                return null;
            }

            var decrypted = CryptoJS.AES.decrypt({ ciphertext: ct }, keys.encKey, {
                iv: iv,
                mode: CryptoJS.mode.CBC,
                padding: CryptoJS.pad.Pkcs7
            });
            return decrypted.toString(CryptoJS.enc.Utf8) || '';
        } catch (e) {
            return null;
        }
    }

    function decryptV1(encrypted, key) {
        if (typeof CryptoJS !== 'undefined' && key) {
            try {
                var bytes = CryptoJS.AES.decrypt(encrypted, key);
                return bytes.toString(CryptoJS.enc.Utf8) || encrypted;
            } catch (e) {
                return encrypted;
            }
        }
        return encrypted;
    }

    return {
        encrypt: function (text, key) {
            return encryptV2(text, key);
        },
        decrypt: function (encrypted, key) {
            if (typeof encrypted === 'string' && encrypted.startsWith('v2:')) {
                return decryptV2(encrypted, key);
            }
            return decryptV1(encrypted, key);
        },
        generateKey: function () {
            if (typeof CryptoJS !== 'undefined') {
                return CryptoJS.lib.WordArray.random(32).toString();
            }
            var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
            var result = '';
            for (var i = 0; i < 64; i++) {
                result += chars.charAt(Math.floor(Math.random() * chars.length));
            }
            return result;
        }
    };
})();
window.E2E = E2E;

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
     * 드래프트(임시 저장) 저장
     */
    async saveDraft(roomId, content) {
        return this.setSetting('draft_' + roomId, content);
    },

    /**
     * 드래프트 조회
     */
    async getDraft(roomId) {
        return this.getSetting('draft_' + roomId, '');
    },

    /**
     * 드래프트 삭제 
     */
    async clearDraft(roomId) {
        if (!this.db) return;

        return new Promise((resolve, reject) => {
            try {
                const transaction = this.db.transaction(['settings'], 'readwrite');
                const store = transaction.objectStore('settings');
                store.delete('draft_' + roomId);

                transaction.oncomplete = () => resolve(true);
                transaction.onerror = () => reject(transaction.error);
            } catch (err) {
                console.error('드래프트 삭제 실패:', err);
                resolve(false);
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

// ============================================================================
// 드래프트 래퍼 함수 (전역 사용용)
// ============================================================================

/**
 * 드래프트 저장
 */
async function saveDraft(roomId, content) {
    return MessengerStorage.saveDraft(roomId, content);
}

/**
 * 드래프트 조회
 */
async function getDraft(roomId) {
    return MessengerStorage.getDraft(roomId);
}

/**
 * 드래프트 삭제
 */
async function clearDraft(roomId) {
    return MessengerStorage.clearDraft(roomId);
}

// 전역 노출
window.saveDraft = saveDraft;
window.getDraft = getDraft;
window.clearDraft = clearDraft;

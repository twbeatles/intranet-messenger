/**
 * Web Notification API 모듈
 * 새 메시지 알림 표시
 */

const MessengerNotification = {
    permission: 'default',

    /**
     * 알림 권한 요청
     */
    async requestPermission() {
        if (!('Notification' in window)) {
            console.log('이 브라우저는 알림을 지원하지 않습니다.');
            return false;
        }

        if (Notification.permission === 'granted') {
            this.permission = 'granted';
            return true;
        }

        if (Notification.permission !== 'denied') {
            const permission = await Notification.requestPermission();
            this.permission = permission;
            return permission === 'granted';
        }

        return false;
    },

    /**
     * 알림 표시
     */
    show(senderName, content, roomId) {
        if (this.permission !== 'granted') return;
        if (document.hasFocus()) return; // 창에 포커스가 있으면 알림 안 함

        try {
            const notification = new Notification('새 메시지', {
                body: `${senderName}: ${content.substring(0, 100)}`,
                icon: '/static/icon.png',
                tag: `room-${roomId}`, // 같은 방의 알림은 덮어쓰기
                requireInteraction: false,
                silent: false
            });

            // 알림 클릭 시 해당 대화방으로 이동
            notification.onclick = () => {
                window.focus();
                notification.close();

                // 대화방 열기 (app.js의 함수 호출)
                if (window.rooms && window.openRoom) {
                    const room = window.rooms.find(r => r.id === roomId);
                    if (room) {
                        window.openRoom(room);
                    }
                }
            };

            // 5초 후 자동 닫기
            setTimeout(() => notification.close(), 5000);

        } catch (err) {
            console.error('알림 표시 실패:', err);
        }
    },

    /**
     * 포커스 상태 확인
     */
    isWindowFocused() {
        return document.hasFocus();
    }
};

// 전역으로 내보내기
window.MessengerNotification = MessengerNotification;

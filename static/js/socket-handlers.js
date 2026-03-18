window.MessengerApp = window.MessengerApp || {};
window.MessengerApp.services = window.MessengerApp.services || {};
window.MessengerApp.services.socket = {
    initSocket: window.initSocket,
    updateConnectionStatus: window.updateConnectionStatus,
    handleNewMessage: window.handleNewMessage,
    handleReadUpdated: window.handleReadUpdated,
    updateUnreadCounts: window.updateUnreadCounts,
    handleUserTyping: window.handleUserTyping,
    handleUserStatus: window.handleUserStatus,
    handleRoomNameUpdated: window.handleRoomNameUpdated,
    handleRoomMembersUpdated: window.handleRoomMembersUpdated,
    handleUserProfileUpdated: window.handleUserProfileUpdated,
    handleReactionUpdated: window.handleReactionUpdated,
    clearTypingUsers: window.clearTypingUsers,
    updateTypingIndicator: window.updateTypingIndicator,
    showMentionNotification: window.showMentionNotification,
    resetReadReceiptCache: window.resetReadReceiptCache,
    rebuildReadReceiptIndex: window.rebuildReadReceiptIndex,
    indexSentMessageEl: window.indexSentMessageEl,
    seedReadReceiptProgress: window.seedReadReceiptProgress
};


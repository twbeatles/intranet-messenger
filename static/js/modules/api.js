// API 호출 모듈

export async function api(url, options = {}) {
    try {
        const res = await fetch(url, {
            ...options,
            headers: { 'Content-Type': 'application/json', ...options.headers }
        });

        const contentType = res.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return {};
        }

        return res.json();
    } catch (err) {
        console.error('API 오류:', url, err);
        throw err;
    }
}

export const AuthAPI = {
    login: (username, password) => api('/api/login', {
        method: 'POST',
        body: JSON.stringify({ username, password })
    }),
    register: (username, password, nickname) => api('/api/register', {
        method: 'POST',
        body: JSON.stringify({ username, password, nickname })
    }),
    logout: () => api('/api/logout', { method: 'POST' }),
    checkSession: () => api('/api/me')
};

export const UserAPI = {
    getUsers: () => api('/api/users'),
    getOnlineUsers: () => api('/api/users/online'),
    getProfile: () => api('/api/profile'),
    updateProfile: (data) => api('/api/profile', {
        method: 'PUT',
        body: JSON.stringify(data)
    }),
    deleteProfileImage: () => api('/api/profile/image', { method: 'DELETE' }),
    uploadProfileImage: async (file) => {
        const formData = new FormData();
        formData.append('file', file);

        const res = await fetch('/api/profile/image', {
            method: 'POST',
            body: formData
        });
        return res.json();
    }
};

export const RoomAPI = {
    getRooms: () => api('/api/rooms'),
    createRoom: (memberIds, name) => api('/api/rooms', {
        method: 'POST',
        body: JSON.stringify({ members: memberIds, name })
    }),
    getMessages: (roomId, beforeId) => {
        let url = `/api/rooms/${roomId}/messages`;
        if (beforeId) url += `?before_id=${beforeId}`;
        return api(url);
    },
    inviteMembers: (roomId, userIds) => api(`/api/rooms/${roomId}/members`, {
        method: 'POST',
        body: JSON.stringify({ user_ids: userIds }) // API expects user_ids array or single user_id
    }),
    // Single user invite wrapper if needed, though the route handles both
    inviteMember: (roomId, userId) => api(`/api/rooms/${roomId}/members`, {
        method: 'POST',
        body: JSON.stringify({ user_id: userId })
    }),
    leaveRoom: (roomId) => api(`/api/rooms/${roomId}/leave`, { method: 'POST' }),
    updateName: (roomId, name) => api(`/api/rooms/${roomId}/name`, {
        method: 'PUT',
        body: JSON.stringify({ name })
    }),
    pinRoom: (roomId, pinned) => api(`/api/rooms/${roomId}/pin`, {
        method: 'POST',
        body: JSON.stringify({ pinned })
    }),
    muteRoom: (roomId, muted) => api(`/api/rooms/${roomId}/mute`, {
        method: 'POST',
        body: JSON.stringify({ muted })
    }),
    getRoomInfo: (roomId) => api(`/api/rooms/${roomId}/info`)
};

export const MessageAPI = {
    deleteMessage: (messageId) => api(`/api/messages/${messageId}`, { method: 'DELETE' }),
    editMessage: (messageId, content) => api(`/api/messages/${messageId}`, {
        method: 'PUT',
        body: JSON.stringify({ content })
    }),
    uploadFile: async (file, roomId) => {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('room_id', roomId);

        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        return res.json();
    },
    search: (query) => api(`/api/search?q=${encodeURIComponent(query)}`)
};

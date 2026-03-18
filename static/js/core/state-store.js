(function (global) {
    var app = global.MessengerApp = global.MessengerApp || {};
    var store = app.state = app.state || {
        currentUser: null,
        currentRoom: null,
        currentRoomKey: null,
        rooms: [],
        socket: null
    };

    function bindStateProperty(name) {
        Object.defineProperty(global, name, {
            configurable: true,
            enumerable: true,
            get: function () {
                return store[name];
            },
            set: function (value) {
                store[name] = value;
            }
        });
    }

    ['currentUser', 'currentRoom', 'currentRoomKey', 'rooms', 'socket'].forEach(bindStateProperty);
})(window);


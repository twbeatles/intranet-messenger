# PyInstaller hook for engineio and flask-socketio
# This file tells PyInstaller which hidden modules to include

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('engineio.async_drivers')
hiddenimports += collect_submodules('socketio')
hiddenimports += ['simple_websocket']

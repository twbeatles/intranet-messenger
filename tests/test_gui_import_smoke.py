def test_gui_entrypoint_exports():
    from gui.server_window import ServerThread, ServerWindow, kill_process_on_port

    assert ServerWindow is not None
    assert ServerThread is not None
    assert callable(kill_process_on_port)

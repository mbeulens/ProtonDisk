from protondisk.mount.callers import is_preview_name, is_preview_process


def test_thumbnailers_and_indexers_are_preview_processes():
    for name in ("gdk-pixbuf-thumbnailer", "totem-video-thumbnailer",
                 "evince-thumbnailer", "gnome-thumbnail-factory", "tumblerd",
                 "tracker-extract-3", "localsearch-extractor-3", "baloo_file_extractor",
                 "gsf-office-thumbnailer"):
        assert is_preview_name(name), name


def test_real_applications_are_not_preview_processes():
    # the file manager itself must keep working (it also does copies), as must
    # ordinary apps that legitimately read a file the user opened
    for name in ("nautilus", "gnome-text-editor", "vim", "cp", "firefox", "mpv",
                 "gio", "code", "libreoffice"):
        assert not is_preview_name(name), name


def test_empty_or_unknown_name_is_not_preview():
    assert is_preview_name(None) is False
    assert is_preview_name("") is False


def _fake_tree(tree):
    # tree: pid -> (name, ppid)
    return (lambda pid: tree[pid][0]), (lambda pid: tree[pid][1])


def test_direct_caller_matches():
    name_of, parent_of = _fake_tree({42: ("gdk-pixbuf-thumbnailer", 7), 7: ("bwrap", 1)})
    assert is_preview_process(42, name_of=name_of, parent_of=parent_of)


def test_ancestor_within_reach_matches():
    # a helper spawned by a thumbnailer (wrapper scripts, sandbox launchers)
    name_of, parent_of = _fake_tree({
        99: ("sh", 42), 42: ("tumblerd", 7), 7: ("systemd", 1), 1: ("systemd", 0)})
    assert is_preview_process(99, name_of=name_of, parent_of=parent_of)


def test_ordinary_process_tree_is_allowed():
    name_of, parent_of = _fake_tree({
        99: ("cp", 42), 42: ("bash", 7), 7: ("gnome-terminal", 1), 1: ("systemd", 0)})
    assert not is_preview_process(99, name_of=name_of, parent_of=parent_of)


def test_walk_stops_at_init_without_error():
    name_of, parent_of = _fake_tree({5: ("cat", 1), 1: ("systemd", 0)})
    assert not is_preview_process(5, name_of=name_of, parent_of=parent_of)


def test_distant_ancestor_is_not_followed_forever():
    # only near ancestors count — a thumbnailer far up an unrelated chain must not
    # condemn a legitimate reader
    tree = {10: ("cp", 9), 9: ("sh", 8), 8: ("sh", 7), 7: ("sh", 6),
            6: ("tumblerd", 1), 1: ("systemd", 0)}
    name_of, parent_of = _fake_tree(tree)
    assert not is_preview_process(10, name_of=name_of, parent_of=parent_of)

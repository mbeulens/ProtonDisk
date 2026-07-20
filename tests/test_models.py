from protondisk.core.models import (
    Entry, AuthStatus, TransferResult, ShareInfo, _unwrap, _parse_iso, _basename,
)

# Real captured node (uid shortened):
FILE_NODE = {
    "uid": "ROOT~FILE",
    "parentUid": "ROOT~PARENT",
    "name": {"ok": True, "value": "kaas.txt"},
    "type": "file",
    "mediaType": "text/plain; charset=utf-8",
    "isShared": False,
    "creationTime": "2026-03-26T00:51:13.000Z",
    "modificationTime": "2026-03-26T00:51:13.000Z",
    "totalStorageSize": 95,
    "ownedBy": {"email": "m.beulens@syntec-one.nl"},
}
FOLDER_NODE = {
    "uid": "ROOT~DIR", "name": {"ok": True, "value": "Test map"},
    "type": "folder", "isShared": False,
    "modificationTime": "2026-03-26T02:17:11.000Z", "folder": {"isImported": False},
}


def test_unwrap_result_object():
    assert _unwrap({"ok": True, "value": "kaas.txt"}) == "kaas.txt"
    assert _unwrap({"ok": False}) is None
    assert _unwrap(None) is None


def test_parse_iso_to_epoch():
    assert _parse_iso("2026-03-26T00:51:13.000Z") == \
        __import__("datetime").datetime(2026, 3, 26, 0, 51, 13,
            tzinfo=__import__("datetime").timezone.utc).timestamp()
    assert _parse_iso(None) is None


def test_basename():
    assert _basename("/my-files/Reports") == "Reports"
    assert _basename("/") == "/"


def test_entry_section_stub_is_directory():
    e = Entry.from_json({"path": "/my-files"})
    assert e.name == "my-files" and e.path == "/my-files" and e.is_dir is True


def test_entry_file_from_list_derives_path_from_parent():
    e = Entry.from_json(FILE_NODE, parent="/my-files")
    assert e.name == "kaas.txt"
    assert e.path == "/my-files/kaas.txt"
    assert e.is_dir is False
    assert e.size == 95
    assert e.uid == "ROOT~FILE"
    assert e.mtime == _parse_iso("2026-03-26T00:51:13.000Z")


def test_entry_folder_type():
    e = Entry.from_json(FOLDER_NODE, parent="/my-files")
    assert e.is_dir is True and e.size is None


def test_entry_info_uses_explicit_path_override():
    # `filesystem info /my-files` returns name "root"; the path override wins.
    info = {"uid": "ROOT~PARENT", "name": {"ok": True, "value": "root"},
            "type": "folder", "ownedBy": {"email": "m.beulens@syntec-one.nl"}}
    e = Entry.from_json(info, path="/my-files")
    assert e.name == "my-files" and e.path == "/my-files" and e.is_dir is True


def test_entry_undecryptable_name_falls_back_to_uid():
    node = {"uid": "ROOT~X", "name": {"ok": False}, "type": "file"}
    e = Entry.from_json(node, parent="/my-files")
    assert e.name == "ROOT~X"


def test_transfer_result_from_json():
    t = TransferResult.from_json(
        {"transferredItems": 1, "transferredBytes": 17,
         "skippedItems": 0, "failedItems": 0, "failures": []})
    assert t.transferred_items == 1 and t.transferred_bytes == 17
    assert t.skipped_items == 0 and t.failed_items == 0 and t.failures == []


def test_share_info_unshared_from_empty():
    s = ShareInfo.from_json({}, path="/my-files/kaas.txt")
    assert s.shared is False and s.members == [] and s.path == "/my-files/kaas.txt"


def test_auth_status_dataclass():
    a = AuthStatus(logged_in=True, account="user@pm.me")
    assert a.logged_in is True and a.account == "user@pm.me"

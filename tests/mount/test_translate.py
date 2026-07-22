import os, stat as stat_mod
from protondisk.mount.translate import proton_path, is_write_flags, stat_dict, root_stat_dict
from protondisk.core.models import Entry


def test_proton_path():
    assert proton_path("/") == "/my-files"
    assert proton_path("/Reports") == "/my-files/Reports"
    assert proton_path("/Reports/q3.pdf") == "/my-files/Reports/q3.pdf"


def test_is_write_flags():
    assert is_write_flags(os.O_RDONLY) is False
    assert is_write_flags(os.O_WRONLY) is True
    assert is_write_flags(os.O_RDWR) is True
    assert is_write_flags(os.O_RDONLY | os.O_TRUNC) is True
    assert is_write_flags(os.O_RDONLY | os.O_APPEND) is True


def test_stat_dict_file_and_dir():
    f = Entry("a.txt", "/my-files/a.txt", False, 95, 1720000000.0, "u")
    sf = stat_dict(f, now=1.0)
    assert sf["st_mode"] == (stat_mod.S_IFREG | 0o644)
    assert sf["st_size"] == 95 and sf["st_nlink"] == 1 and sf["st_mtime"] == 1720000000.0
    d = Entry("Dir", "/my-files/Dir", True, None, None, "u")
    sd = stat_dict(d, now=7.0)
    assert sd["st_mode"] == (stat_mod.S_IFDIR | 0o755)
    assert sd["st_size"] == 0 and sd["st_nlink"] == 2 and sd["st_mtime"] == 7.0  # mtime None -> now


def test_root_stat_dict_is_dir():
    r = root_stat_dict(now=3.0)
    assert r["st_mode"] == (stat_mod.S_IFDIR | 0o755) and r["st_mtime"] == 3.0

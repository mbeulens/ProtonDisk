from protondisk.mount.ignore import is_ephemeral


def test_editor_and_os_temps_are_ephemeral():
    for name in [".kaas.txt.swp", ".notes.swo", ".x.swn", ".y.swpx",
                 ".#foo", "#foo#",
                 ".goutputstream-AB12CD",
                 ".~lock.report.odt#", "~$budget.xlsx",
                 ".DS_Store", "._resourcefork", "Thumbs.db", "desktop.ini", "4913"]:
        assert is_ephemeral(name) is True, name


def test_real_files_and_backups_are_not_ephemeral():
    for name in ["kaas.txt", "report.odt", "notes.md", "photo.jpg",
                 "backup~", "data.tmp", "archive.swp.txt",  # .swp not at the end
                 ".config", ".bashrc", ".hidden_but_real"]:
        assert is_ephemeral(name) is False, name

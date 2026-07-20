import protondisk


def test_package_exposes_version():
    assert isinstance(protondisk.__version__, str)
    assert protondisk.__version__ != ""

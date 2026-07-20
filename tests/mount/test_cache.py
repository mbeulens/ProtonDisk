from protondisk.mount.cache import ListingCache


class FakeClock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def test_put_get_hit():
    c = ListingCache(ttl=5.0, clock=FakeClock())
    c.put("/p", ["a", "b"])
    assert c.get("/p") == ["a", "b"]


def test_miss_returns_none():
    assert ListingCache(clock=FakeClock()).get("/nope") is None


def test_expiry():
    clk = FakeClock()
    c = ListingCache(ttl=5.0, clock=clk)
    c.put("/p", ["a"])
    clk.t = 4.9
    assert c.get("/p") == ["a"]      # still fresh
    clk.t = 5.0
    assert c.get("/p") is None       # expired (dropped)
    assert c.get("/p") is None


def test_invalidate():
    clk = FakeClock()
    c = ListingCache(clock=clk)
    c.put("/a", [1]); c.put("/b", [2])
    c.invalidate("/a")
    assert c.get("/a") is None and c.get("/b") == [2]
    c.invalidate()
    assert c.get("/b") is None

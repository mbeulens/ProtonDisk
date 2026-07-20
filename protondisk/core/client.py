"""ProtonDisk façade: typed methods over the CLIRunner."""
from __future__ import annotations

from .runner import CLIRunner
from .errors import AuthError, NotFoundError
from .models import AuthStatus, Entry, TransferResult, ShareInfo


class ProtonDisk:
    ROOT = "/my-files"

    def __init__(self, runner: CLIRunner | None = None) -> None:
        self._runner = runner or CLIRunner()

    # --- auth ---
    def auth_status(self) -> AuthStatus:
        try:
            data = self._runner.run("filesystem", "info", self.ROOT)
        except AuthError:
            return AuthStatus(logged_in=False, account=None)
        account = data.get("ownedBy", {}).get("email") if isinstance(data, dict) else None
        return AuthStatus(logged_in=True, account=account)

    def login(self) -> None:
        self._runner.run("auth", "login")

    def logout(self) -> None:
        self._runner.run("auth", "logout")

    # --- browsing ---
    def list(self, path: str) -> list[Entry]:
        data = self._runner.run("filesystem", "list", path)
        if not isinstance(data, list):
            return []
        return [Entry.from_json(item, parent=path) for item in data]

    def stat(self, path: str) -> Entry:
        data = self._runner.run("filesystem", "info", path)
        return Entry.from_json(data, path=path)

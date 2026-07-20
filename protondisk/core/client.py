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

    # --- transfer ---
    def upload(self, local: str, parent: str, *, conflict: str = "skip") -> TransferResult:
        data = self._runner.run(
            "filesystem", "upload", "--conflict-strategy", conflict, local, parent)
        return TransferResult.from_json(data)

    def download(self, remote: str, local_folder: str) -> TransferResult:
        data = self._runner.run("filesystem", "download", remote, local_folder)
        return TransferResult.from_json(data)

    # --- organize ---
    def mkdir(self, path: str) -> None:
        parent, _, name = path.rstrip("/").rpartition("/")
        self._runner.run("filesystem", "create-folder", parent or "/", name)

    def rename(self, path: str, new_name: str) -> None:
        self._runner.run("filesystem", "rename", path, new_name)

    def move(self, src: str, target_parent: str) -> None:
        self._runner.run("filesystem", "move", src, target_parent)

    def trash(self, path: str) -> None:
        self._runner.run("filesystem", "trash", path)

    # --- sharing ---
    def sharing_status(self, path: str) -> ShareInfo:
        data = self._runner.run("sharing", "status", path)
        return ShareInfo.from_json(data, path=path)

    def sharing_invite(self, path: str, user: str, role: str = "viewer",
                       message: str = "") -> None:
        args = ["sharing", "invite", "--user", user, "--role", role]
        if message:
            args += ["--message", message]
        args.append(path)
        self._runner.run(*args)

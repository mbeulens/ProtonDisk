"""ProtonDisk façade: typed methods over the CLIRunner."""
from __future__ import annotations

from .runner import CLIRunner
from .errors import AuthError
from .models import AuthStatus, Entry, TransferResult, ShareInfo
from .progress import parse_progress_line


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
    @staticmethod
    def _emit_progress(raw_line: str, progress) -> None:
        phase = parse_progress_line(raw_line)
        if phase is not None:
            progress(phase)

    def upload(self, local: str, parent: str, *, conflict: str = "skip",
               progress=None) -> TransferResult:
        if progress is None:
            data = self._runner.run(
                "filesystem", "upload", "--conflict-strategy", conflict, local, parent,
                timeout=None)  # a large upload legitimately runs longer than the metadata cap
        else:
            data = self._runner.run_streaming(
                "filesystem", "upload", "--verbose",
                "--conflict-strategy", conflict, local, parent,
                on_line=lambda raw: self._emit_progress(raw, progress))
        return TransferResult.from_json(data)

    def download(self, remote: str, local_folder: str, *, progress=None) -> TransferResult:
        if progress is None:
            data = self._runner.run(
                "filesystem", "download", remote, local_folder,
                timeout=None)  # a large download legitimately runs longer than the metadata cap
        else:
            data = self._runner.run_streaming(
                "filesystem", "download", "--verbose", remote, local_folder,
                on_line=lambda raw: self._emit_progress(raw, progress))
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

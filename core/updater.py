"""Safe self-update helpers for the Windows installer build.

The app downloads only an HTTPS installer described by a small release
manifest and verifies its SHA-256 before launching it. The installer performs
the actual replacement after the running process exits.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path


CURRENT_VERSION = "1.2.8"
_ENDPOINT_CANDIDATES = [Path(__file__).with_name("update_endpoint.txt")]
if getattr(sys, "frozen", False):
    _ENDPOINT_CANDIDATES.insert(0, Path(sys.executable).resolve().parent / "update_endpoint.txt")
_PACKAGED_UPDATE_URL = ""
for _endpoint in _ENDPOINT_CANDIDATES:
    try:
        _PACKAGED_UPDATE_URL = _endpoint.read_text(encoding="utf-8").strip()
    except OSError:
        continue
    if _PACKAGED_UPDATE_URL:
        break
UPDATE_MANIFEST_URL = os.environ.get("NETRUNNER_UPDATE_MANIFEST_URL", _PACKAGED_UPDATE_URL).strip()
_VERSION_RE = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-+].*)?$")


def _version_key(value):
    match = _VERSION_RE.match(str(value or "").strip())
    if not match:
        raise ValueError(f"Versão inválida: {value}")
    return tuple(int(part or 0) for part in match.groups())


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    download_url: str
    sha256: str
    notes_url: str = ""

    @classmethod
    def from_payload(cls, payload):
        if not isinstance(payload, dict):
            raise ValueError("Manifesto de atualização inválido.")
        version = str(payload.get("version", "")).strip()
        download_url = str(payload.get("download_url", payload.get("url", ""))).strip()
        sha256 = str(payload.get("sha256", payload.get("installer_sha256", ""))).strip().lower()
        if not version or not download_url or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("Manifesto de atualização incompleto.")
        _version_key(version)
        if not download_url.lower().startswith("https://"):
            raise ValueError("O download da atualização precisa usar HTTPS.")
        return cls(version, download_url, sha256, str(payload.get("notes_url", "")).strip())


def check_for_update(manifest_url=None, current_version=CURRENT_VERSION, timeout=8):
    """Return UpdateInfo when a newer release is available, otherwise None."""
    url = (manifest_url or UPDATE_MANIFEST_URL).strip()
    if not url:
        return None
    if not url.lower().startswith("https://"):
        raise ValueError("A URL do manifesto precisa usar HTTPS.")
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "NetrunnerOverlay/1.2"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    info = UpdateInfo.from_payload(payload)
    return info if _version_key(info.version) > _version_key(current_version) else None


def download_and_verify(update, destination_dir=None, timeout=60):
    """Download an installer, verify it, and return its local path."""
    if not isinstance(update, UpdateInfo):
        raise TypeError("update precisa ser UpdateInfo")
    target_dir = Path(destination_dir or tempfile.gettempdir()) / "NetrunnerOverlay-update"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"NetrunnerOverlay-Setup-v{update.version.lstrip('v')}.exe"
    temporary_path = target_path.with_suffix(".download")
    request = urllib.request.Request(
        update.download_url,
        headers={"User-Agent": "NetrunnerOverlay/1.2"},
    )
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, open(temporary_path, "wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest().lower() != update.sha256.lower():
            raise ValueError("O SHA-256 do instalador não confere com o manifesto.")
        os.replace(temporary_path, target_path)
        return str(target_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def launch_installer(installer_path):
    """Start Inno Setup and let it close/replace the current app."""
    path = Path(installer_path).resolve()
    if path.suffix.lower() != ".exe" or not path.is_file():
        raise ValueError("Instalador inválido.")
    return subprocess.Popen(
        [str(path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
        cwd=str(path.parent),
        close_fds=True,
    )

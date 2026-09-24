"""bewerbungdb://-Links auswerten und Links an eine bereits laufende App weitergeben."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from .config import find_home

SCHEME = "bewerbungdb"
JOB_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def parse_link(arg: str) -> Optional[str]:
    """'bewerbungdb://create-application/c876474e3c' → 'c876474e3c'; alles andere → None.

    Tolerant gegenüber Schreibweisen wie 'bewerbungdb:create-application/ID', abschließendem '/'
    und von Windows angehängten Anführungszeichen; streng bei der ID selbst.
    """
    arg = (arg or "").strip().strip('"').strip()
    prefix = SCHEME + ":"
    if not arg.lower().startswith(prefix):
        return None
    rest = arg[len(prefix):].lstrip("/")
    rest = rest.split("?", 1)[0].split("#", 1)[0]
    parts = [p for p in rest.split("/") if p]
    if len(parts) != 2 or parts[0].lower() != "create-application":
        return None
    return parts[1] if JOB_ID_RE.fullmatch(parts[1]) else None


# ── Laufende Instanz finden / ansprechen ─────────────────────────────────────
def instance_file() -> Path:
    return find_home() / "instance.json"


def write_instance(port: int, secret: str) -> None:
    f = instance_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"port": port, "secret": secret}), encoding="utf-8")


def clear_instance(port: int) -> None:
    f = instance_file()
    try:
        if json.loads(f.read_text(encoding="utf-8")).get("port") == port:
            f.unlink()
    except (OSError, ValueError):
        pass


def send_to_running_instance(job_id: Optional[str]) -> bool:
    """Bittet eine laufende App, ein Fenster (für job_id) zu öffnen. False = keine laufende App."""
    try:
        info = json.loads(instance_file().read_text(encoding="utf-8"))
        port, secret = int(info["port"]), str(info["secret"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/ipc/open",
        data=json.dumps({"job": job_id}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Ipc-Secret": secret},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False  # veraltete Datei (App wurde beendet oder ist abgestürzt)

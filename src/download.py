"""Download helper: skip if present, fail loudly with manual instructions."""
from __future__ import annotations

import logging
from pathlib import Path

import requests
from tqdm import tqdm

log = logging.getLogger(__name__)


class DownloadError(RuntimeError):
    pass


def download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        log.info("[download] present, skipping: %s", dest)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0)) or None
            with open(tmp, "wb") as f, tqdm(total=total, unit="B", unit_scale=True,
                                            desc=dest.name) as bar:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
                    bar.update(len(chunk))
    except requests.RequestException as e:
        tmp.unlink(missing_ok=True)
        raise DownloadError(
            f"\n\nDOWNLOAD FAILED: {url}\n  reason: {e}\n"
            f"  -> Download this file manually (browser / other network) and put it at:\n"
            f"     {dest}\n  then re-run the script.\n"
        ) from e
    tmp.rename(dest)  # only complete files get the final name -> safe to resume
    return dest

"""Data utilities package."""

from __future__ import annotations

import hashlib
from pathlib import Path


def compute_sha256(path: Path) -> str:
    """Compute SHA256 hash of a file.

    Args:
        path: Path to the file to hash.

    Returns:
        Hex digest of the file contents.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not path.exists():
        msg = f"File not found for hashing: {path}"
        raise FileNotFoundError(msg)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

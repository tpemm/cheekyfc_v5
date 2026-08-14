"""Shared safeguards for Unicode-capable Fantrax command-line output."""

from __future__ import annotations

import sys
from typing import Any, TextIO


def configure_unicode_console() -> None:
    """Prefer UTF-8 with replacement semantics for Windows and redirected CLIs."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, OSError, ValueError):
                # Test doubles, detached streams, and some embedded hosts may
                # expose reconfigure without permitting a runtime change.
                pass


def safe_console_print(*values: Any, stream: TextIO | None = None, **kwargs: Any) -> bool:
    """Best-effort diagnostics that can never invalidate completed data work."""
    target = stream or sys.stdout
    try:
        print(*values, file=target, **kwargs)
        return True
    except UnicodeEncodeError:
        try:
            separator = str(kwargs.get("sep", " "))
            ending = str(kwargs.get("end", "\n"))
            text = separator.join(str(value) for value in values)
            encoding = getattr(target, "encoding", None) or "ascii"
            safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
            target.write(safe + ending)
            return True
        except Exception:
            return False
    except Exception:
        return False

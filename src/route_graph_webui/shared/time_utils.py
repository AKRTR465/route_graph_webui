from __future__ import annotations

import time


def timestamp_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


__all__ = ["timestamp_now"]

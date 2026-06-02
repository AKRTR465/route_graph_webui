from __future__ import annotations

import runpy
import sys


if __name__ == "__main__":
    runpy.run_module("tools.media.resample", run_name="__main__")
else:
    from tools.media import resample as _impl

    sys.modules[__name__] = _impl

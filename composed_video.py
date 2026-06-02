from __future__ import annotations

import runpy
import sys


if __name__ == "__main__":
    runpy.run_module("tools.media.composed_video", run_name="__main__")
else:
    from tools.media import composed_video as _impl

    sys.modules[__name__] = _impl

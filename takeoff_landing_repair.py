from __future__ import annotations

import runpy
import sys


if __name__ == "__main__":
    runpy.run_module("tools.mission.takeoff_landing_repair", run_name="__main__")
else:
    from tools.mission import takeoff_landing_repair as _impl

    sys.modules[__name__] = _impl

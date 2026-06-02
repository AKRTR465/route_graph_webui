# Optional Tools

These tools are not required for the base WebUI runtime. Install `requirements-media.txt` only when using media conversion.

## Media

- `tools/media/resample.py`，兼容入口 `resample.py`：distance-based mission position resampling.
- `tools/media/composed_video.py`，兼容入口 `composed_video.py`：compose image sequences into mp4 videos.

`composed_video.py` defaults to `data/data_photos_videos/photos` and writes to `data/data_photos_videos/videos`. The legacy `phtots` input folder is read-only fallback until `2026-12-31`.

`ffmpeg` is a system dependency. Set `ROUTE_GRAPH_WEBUI_FFMPEG` or pass `--ffmpeg-path` if it is not on `PATH`.

## Mission Repair

- `tools/mission/mission_repair.py`，兼容入口 `mission_repair.py`：library helpers for takeoff/landing repair.
- `tools/mission/takeoff_landing_repair.py`，兼容入口 `takeoff_landing_repair.py`：batch repair CLI.

`takeoff_landing_repair.py --photos-root` defaults to `data/data_photos_videos/photos/<missions-root-name>` with the same legacy `phtots` fallback.

## Dependency Files

- `requirements-runtime.txt`：base WebUI backend runtime.
- `requirements-webui.txt`：compatibility entry that references runtime requirements.
- `requirements-dev.txt`：runtime plus test/development dependencies.
- `requirements-media.txt`：media tool dependencies such as `numpy` and `Pillow`.


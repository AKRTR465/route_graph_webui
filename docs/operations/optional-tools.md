# Optional Tools

These tools are not required for the base WebUI runtime. Install `requirements/media.txt` or `.[media]` only when using media conversion.

## Media

- `python -m route_graph_webui.tools.media.resample`：distance-based mission position resampling.
- `python -m route_graph_webui.tools.media.composed_video`：compose image sequences into mp4 videos.

The composed-video tool defaults to `data/data_photos_videos/photos` and writes to `data/data_photos_videos/videos`. The legacy `phtots` input folder is read-only fallback until `2026-12-31`.

`ffmpeg` is a system dependency. Set `ROUTE_GRAPH_WEBUI_FFMPEG` or pass `--ffmpeg-path` if it is not on `PATH`.

## Mission Repair

- `route_graph_webui.tools.mission.mission_repair`：library helpers for takeoff/landing repair.
- `python -m route_graph_webui.tools.mission.takeoff_landing_repair`：batch repair CLI.

`python -m route_graph_webui.tools.mission.takeoff_landing_repair --photos-root` defaults to `data/data_photos_videos/photos/<missions-root-name>` with the same legacy `phtots` fallback.

## Dependency Files

- `requirements/runtime.txt`：base WebUI backend runtime.
- `requirements/dev.txt`：runtime plus test/development dependencies.
- `requirements/media.txt`：media tool dependencies such as `numpy` and `Pillow`.

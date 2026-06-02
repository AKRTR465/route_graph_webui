from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[2]
STYLE_CSS = ROOT / "webui_frontend" / "src" / "style.css"
PREVIEW_DIR = Path(__file__).resolve().parent
IMPORT_RE = re.compile(r"@import\s+\"([^\"]+)\";")


def iter_css_sources(path: Path, seen: set[Path] | None = None) -> list[tuple[Path, str]]:
    if seen is None:
        seen = set()
    path = path.resolve()
    if path in seen:
        return []
    seen.add(path)
    css_text = path.read_text(encoding="utf-8")
    sources = [(path, css_text)]
    for import_path in IMPORT_RE.findall(css_text):
        if not import_path.startswith("."):
            continue
        sources.extend(iter_css_sources(path.parent / import_path, seen))
    return sources


def extract_svg_var(css_sources: list[tuple[Path, str]], var_name: str) -> str:
    pattern = re.compile(
        rf"{re.escape(var_name)}\s*:\s*url\([\"']?([^\"')]+)[\"']?\)\s*;",
        re.DOTALL,
    )
    for css_path, css_text in css_sources:
        match = pattern.search(css_text)
        if not match:
            continue
        url = match.group(1)
        if url.startswith("data:image/svg+xml,"):
            return unquote(url.removeprefix("data:image/svg+xml,"))
        asset_path = (css_path.parent / url).resolve()
        return asset_path.read_text(encoding="utf-8")
    raise RuntimeError(f"Could not find CSS variable: {var_name}")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def build_preview_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Background Contours Preview</title>
  <style>
    :root {
      color-scheme: light;
      font-family: "PingFang SC", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(14, 116, 144, 0.18), transparent 32%),
        radial-gradient(circle at top right, rgba(249, 115, 22, 0.16), transparent 28%),
        linear-gradient(180deg, #f7f0e3 0%, #edf5f4 100%);
      color: #102a43;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      padding: 32px;
      background:
        radial-gradient(circle at top left, rgba(14, 116, 144, 0.18), transparent 32%),
        radial-gradient(circle at top right, rgba(249, 115, 22, 0.16), transparent 28%),
        linear-gradient(180deg, #f7f0e3 0%, #edf5f4 100%);
    }

    .page {
      max-width: 1480px;
      margin: 0 auto;
    }

    .header {
      margin-bottom: 24px;
    }

    .header h1 {
      margin: 0 0 8px;
      font-size: 28px;
      line-height: 1.15;
    }

    .header p {
      margin: 0;
      color: #486581;
      font-size: 15px;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 24px;
    }

    .card {
      border-radius: 28px;
      border: 1px solid rgba(16, 42, 67, 0.08);
      background: rgba(255, 255, 255, 0.72);
      backdrop-filter: blur(16px);
      box-shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
      overflow: hidden;
    }

    .card__meta {
      padding: 18px 22px 14px;
      border-bottom: 1px solid rgba(16, 42, 67, 0.08);
      background: rgba(255, 255, 255, 0.64);
    }

    .card__meta h2 {
      margin: 0 0 6px;
      font-size: 16px;
    }

    .card__meta p {
      margin: 0;
      color: #486581;
      font-size: 13px;
    }

    .scene {
      position: relative;
      height: 880px;
      overflow: hidden;
      isolation: isolate;
      background:
        radial-gradient(circle at top left, rgba(14, 116, 144, 0.18), transparent 32%),
        radial-gradient(circle at top right, rgba(249, 115, 22, 0.16), transparent 28%),
        linear-gradient(180deg, #f7f0e3 0%, #edf5f4 100%);
    }

    .base-glow,
    .contours {
      position: absolute;
      pointer-events: none;
    }

    .base-glow {
      inset: -6.6rem -6.8rem -5.2rem;
      background:
        radial-gradient(circle at 14% 16%, rgba(28, 104, 124, 0.12), transparent 28%),
        radial-gradient(circle at 86% 14%, rgba(47, 111, 103, 0.14), transparent 26%),
        radial-gradient(circle at 82% 62%, rgba(214, 177, 120, 0.09), transparent 28%),
        radial-gradient(circle at 18% 84%, rgba(196, 154, 96, 0.08), transparent 27%);
      opacity: 0.92;
    }

    .contours {
      inset: -6.6rem -6.8rem -5.2rem;
      background-repeat: no-repeat;
      background-position: center center;
      background-size: 118% 118%;
      opacity: 1;
      filter: contrast(1.06);
      mix-blend-mode: multiply;
      -webkit-mask-image: radial-gradient(
        ellipse 156% 112% at 50% 50%,
        rgba(0, 0, 0, 0.94) 0%,
        rgba(0, 0, 0, 0.97) 56%,
        rgba(0, 0, 0, 0.99) 84%,
        #000 100%
      );
      mask-image: radial-gradient(
        ellipse 156% 112% at 50% 50%,
        rgba(0, 0, 0, 0.94) 0%,
        rgba(0, 0, 0, 0.97) 56%,
        rgba(0, 0, 0, 0.99) 84%,
        #000 100%
      );
    }

    .scene--desktop .contours {
      background-image: url("./page-contours-major-extracted.svg");
    }

    .scene--mobile .contours {
      inset: -4.8rem -4.2rem -3.8rem;
      background-image: url("./page-contours-major-mobile-extracted.svg");
      -webkit-mask-image: radial-gradient(
        ellipse 156% 116% at 50% 50%,
        rgba(0, 0, 0, 0.94) 0%,
        rgba(0, 0, 0, 0.97) 56%,
        rgba(0, 0, 0, 0.99) 84%,
        #000 100%
      );
      mask-image: radial-gradient(
        ellipse 156% 116% at 50% 50%,
        rgba(0, 0, 0, 0.94) 0%,
        rgba(0, 0, 0, 0.97) 56%,
        rgba(0, 0, 0, 0.99) 84%,
        #000 100%
      );
    }
  </style>
</head>
<body>
  <main class="page">
    <section class="header">
      <h1>Route Graph WebUI 背景等高线预览</h1>
      <p>从 webui_frontend/src/style.css 提取当前桌面端与移动端的等高线 SVG，并按页面实际背景样式重建。</p>
    </section>
    <section class="grid">
      <article class="card">
        <div class="card__meta">
          <h2>Desktop Major Contours</h2>
          <p>对应 CSS 变量: <code>--page-contours-major-svg</code></p>
        </div>
        <div class="scene scene--desktop">
          <div class="base-glow"></div>
          <div class="contours"></div>
        </div>
      </article>
      <article class="card">
        <div class="card__meta">
          <h2>Mobile Major Contours</h2>
          <p>对应 CSS 变量: <code>--page-contours-major-svg-mobile</code></p>
        </div>
        <div class="scene scene--mobile">
          <div class="base-glow"></div>
          <div class="contours"></div>
        </div>
      </article>
    </section>
  </main>
</body>
</html>
"""


def main() -> None:
    css_sources = iter_css_sources(STYLE_CSS)

    desktop_svg = extract_svg_var(css_sources, "--page-contours-major-svg")
    mobile_svg = extract_svg_var(css_sources, "--page-contours-major-svg-mobile")

    write_text(PREVIEW_DIR / "page-contours-major-extracted.svg", desktop_svg)
    write_text(PREVIEW_DIR / "page-contours-major-mobile-extracted.svg", mobile_svg)
    write_text(PREVIEW_DIR / "background-contours-preview.html", build_preview_html())

    print("Generated:")
    print(PREVIEW_DIR / "page-contours-major-extracted.svg")
    print(PREVIEW_DIR / "page-contours-major-mobile-extracted.svg")
    print(PREVIEW_DIR / "background-contours-preview.html")


if __name__ == "__main__":
    main()

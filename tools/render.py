#!/usr/bin/env python3
"""Render the 19 November 2026 World Chronicle front page.

Reads stories.json from the repository root, lays out a one-page newspaper
in plain HTML/CSS, and screenshots it at exactly 1024x1024 with headless
Chromium through Playwright. The output is assets/entry.png.

Deterministic by construction: the HTML is static (no timestamps, no
random numbers, no JavaScript that mutates the layout, no network), so
two runs produce identical bytes.

The build FAILS with exit code 1 if anything is clipped or the page runs
taller than 1024px, so a broken layout can never ship silently. The
checks are:
  * page scrollHeight must be <= 1024 (nothing pushed below the fold)
  * page scrollWidth must be <= 1024 (nothing pushed off the side)
  * the ticker's scrollWidth must be <= its clientWidth (no ticker
    text cut off at the right edge)
  * every element marked class "clip" must not have scrollHeight above
    its clientHeight (no line-clamped headline or fact losing a line)

Usage:
    python3 tools/render.py [--out PATH]
"""

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
PAGE_W, PAGE_H = 1024, 1024

GUARD_JS = """() => {
  const bad = [];
  const page = document.getElementById('page');
  if (page.scrollHeight > 1024) {
    bad.push(`page too tall: scrollHeight=${page.scrollHeight} > 1024`);
  }
  if (page.scrollWidth > 1024) {
    bad.push(`page too wide: scrollWidth=${page.scrollWidth} > 1024`);
  }
  const ticker = document.getElementById('ticker');
  if (ticker.scrollWidth > ticker.clientWidth) {
    bad.push(`ticker overflows: scrollWidth=${ticker.scrollWidth} > clientWidth=${ticker.clientWidth}`);
  }
  document.querySelectorAll('.clip').forEach((el, i) => {
    if (el.scrollHeight - el.clientHeight > 1) {
      bad.push(`clipped text in .${el.className.split(' ')[0]} #${i}: ` +
        `"${el.textContent.trim().slice(0, 60)}..." ` +
        `scrollHeight=${el.scrollHeight} clientHeight=${el.clientHeight}`);
    }
  });
  return bad;
}"""


def esc(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def lead_html(lead):
    return f"""
    <section class="lead">
      <div class="kicker">{esc(lead['kicker'])}</div>
      <h1>{esc(lead['headline'])}</h1>
      <p class="dek">{esc(lead['dek'])}</p>
      <p class="lead-body">{esc(lead['body'])}</p>
      <p class="attribution">{esc(lead['attribution'])}</p>
    </section>"""


def second_html(second):
    return f"""
    <section class="second">
      <div class="kicker">{esc(second['kicker'])}</div>
      <h2 class="clip clamp1">{esc(second['headline'])}</h2>
      <p class="clip clamp3">{esc(second['body'])}</p>
    </section>"""


def mains_html(mains):
    cells = "".join(
        f"""
      <article class="main">
        <div class="region">{esc(m['region'])}</div>
        <h3 class="clip clamp2">{esc(m['headline'])}</h3>
        <p class="clip clamp3">{esc(m['fact'])}</p>
      </article>"""
        for m in mains
    )
    return f"""
    <div class="section-head">The day&rsquo;s main stories</div>
    <section class="mains">{cells}
    </section>"""


def briefs_html(briefs):
    cells = "".join(
        f"""
      <article class="brief clip clamp2"><b>{esc(b['headline'])}</b> — {esc(b['fact'])}</article>"""
        for b in briefs
    )
    return f"""
    <div class="section-head">More of the day</div>
    <section class="briefs">{cells}
    </section>"""


def build_html(data):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #fff; font-family: "DejaVu Sans", sans-serif; color: #111; }}
  #page {{
    width: {PAGE_W}px; height: {PAGE_H}px; overflow: hidden;
    padding: 16px 26px 12px; background: #fdfcf7;
  }}
  .serif {{ font-family: "Noto Serif", "DejaVu Serif", serif; }}
  .masthead {{ text-align: center; border-bottom: 3px solid #111; padding-bottom: 8px; }}
  .masthead h1 {{
    font-family: "Noto Serif", "DejaVu Serif", serif; font-weight: 800;
    font-size: 43px; letter-spacing: 1px; line-height: 1.05;
  }}
  .dateline {{
    display: flex; justify-content: space-between; margin-top: 6px;
    font-size: 10.5px; font-weight: bold; letter-spacing: 1.5px; text-transform: uppercase;
  }}
  .dateline .mid {{ color: #9b1c1c; }}
  .kicker {{
    color: #9b1c1c; font-size: 11px; font-weight: bold; letter-spacing: 2px;
  }}
  .lead {{ padding: 9px 0 8px; border-bottom: 1px solid #999; }}
  .lead h1 {{
    font-family: "Noto Serif", "DejaVu Serif", serif; font-weight: 800;
    font-size: 36px; line-height: 1.12; margin: 3px 0 4px;
  }}
  .dek {{
    font-family: "Noto Serif", "DejaVu Serif", serif; font-style: italic;
    font-size: 16px; color: #333; margin-bottom: 6px;
  }}
  .lead-body {{ font-size: 14.5px; line-height: 1.5; }}
  .attribution {{ font-size: 10.5px; color: #666; margin-top: 5px; }}
  .second {{
    background: #f3ede0; border-left: 5px solid #9b1c1c;
    padding: 9px 12px; margin: 7px 0;
  }}
  .second h2 {{
    font-family: "Noto Serif", "DejaVu Serif", serif; font-weight: 800;
    font-size: 20px; line-height: 1.2; margin: 2px 0 4px;
  }}
  .second p {{ font-size: 13px; line-height: 1.45; }}
  .section-head {{
    font-size: 11px; font-weight: bold; letter-spacing: 2px; text-transform: uppercase;
    border-bottom: 2px solid #111; padding-bottom: 3px; margin: 6px 0 8px;
  }}
  .mains {{
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 10px 16px; margin-bottom: 4px;
  }}
  .main .region {{
    color: #9b1c1c; font-size: 9.5px; font-weight: bold; letter-spacing: 1.5px;
    margin-bottom: 2px;
  }}
  .main h3 {{
    font-family: "Noto Serif", "DejaVu Serif", serif; font-weight: 800;
    font-size: 15px; line-height: 1.25; margin-bottom: 3px;
  }}
  .main p {{ font-size: 12px; line-height: 1.4; color: #222; }}
  .briefs {{
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 7px 18px;
  }}
  .brief {{ font-size: 10px; line-height: 1.35; color: #222; }}
  .brief b {{ color: #111; }}
  .ticker {{
    background: #111; color: #fff; font-size: 12px; font-weight: bold;
    letter-spacing: 0.5px; padding: 7px 10px; margin-top: 8px;
    white-space: nowrap; overflow: hidden; text-align: center;
  }}
  .footer {{
    display: flex; justify-content: space-between; margin-top: 5px;
    font-size: 10px; color: #666; letter-spacing: 0.5px;
  }}
  .clip {{ overflow: hidden; display: -webkit-box; -webkit-box-orient: vertical; }}
  .clamp1 {{ -webkit-line-clamp: 1; }}
  .clamp2 {{ -webkit-line-clamp: 2; }}
  .clamp3 {{ -webkit-line-clamp: 3; }}
</style>
</head>
<body>
<div id="page">
  <header class="masthead">
    <h1>{esc(data['paper'])}</h1>
    <div class="dateline">
      <span>{esc(data['edition'])}</span>
      <span class="mid">{esc(data['date_label'])}</span>
      <span>{esc(data['tagline'])}</span>
    </div>
  </header>
  {lead_html(data['lead'])}
  {second_html(data['second_lead'])}
  {mains_html(data['mains'])}
  {briefs_html(data['briefs'])}
  <div class="ticker" id="ticker">{esc(data['ticker'])}</div>
  <div class="footer">
    <span>{esc(data['footer']['count'])}</span>
    <span>{esc(data['footer']['sources'])}</span>
  </div>
</div>
</body>
</html>"""


def render(out_path):
    data = json.loads((REPO / "stories.json").read_text(encoding="utf-8"))
    n = 1 + 1 + len(data["mains"]) + len(data["briefs"])
    print(f"stories: {n} (1 lead + 1 second lead + "
          f"{len(data['mains'])} mains + {len(data['briefs'])} briefs)")
    html = build_html(data)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".html", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(html)
        tmp_path = tmp.name
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage",
                      "--force-color-profile=srgb"]
            )
            page = browser.new_page(
                viewport={"width": PAGE_W, "height": PAGE_H},
                device_scale_factor=1,
            )
            page.goto(Path(tmp_path).as_uri())
            page.wait_for_load_state("load")
            failures = page.evaluate(GUARD_JS)
            if failures:
                print("LAYOUT GUARD FAILED:", file=sys.stderr)
                for f in failures:
                    print(f"  - {f}", file=sys.stderr)
                browser.close()
                return 1
            out_path.parent.mkdir(parents=True, exist_ok=True)
            page.locator("#page").screenshot(path=str(out_path))
            browser.close()
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    with Image.open(out_path) as img:
        if img.format != "PNG" or img.size != (PAGE_W, PAGE_H):
            print(f"BAD PNG: format={img.format} size={img.size}", file=sys.stderr)
            return 1
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    print(f"wrote {out_path}  {out_path.stat().st_size} bytes  sha256={digest}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path,
                        default=REPO / "assets" / "entry.png")
    args = parser.parse_args()
    return render(args.out)


if __name__ == "__main__":
    raise SystemExit(main())

# THE WORLD CHRONICLE — 19 November 2026

A one-page newspaper front page summing up Thursday 19 November 2026,
built for make.fun competition `news-image-20261119` (deadline 21 Nov 2026
07:00 WIB). 38 verified stories: 1 lead + 1 second lead + 8 mains + 28
briefs. Every story is verified in `VERIFICATION.md` with its source and
its 19 November date evidence.

## How it is built

- `stories.json` — every story the image shows (headline + one fact line).
- `tools/render.py` — reads `stories.json`, lays out the page in HTML/CSS
  and screenshots it at exactly 1024×1024 with headless Chromium
  (Playwright). The build **fails** if any text is clipped, the ticker
  overflows its box, or the page runs taller than 1024px.
- `assets/entry.png` — the rendered image (1024×1024, ≤ 1 MiB).
- `main.ts` — the entry program: copies `assets/entry.png` to
  `/output/entry.png`. Node 22 standard library only, no network.

## Reproduce

```sh
python3 tools/render.py            # renders assets/entry.png
mkdir -p out && MAKEFUN_OUTPUT_DIR=out node main.ts   # copies it to out/entry.png
```

Run the render twice and compare sha256 — the bytes must be identical.

## License

MIT — see `LICENSE`.

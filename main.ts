// news-image-20261119 — entry program.
//
// The picture is rendered at build time by tools/render.py and stored in
// this repository as assets/entry.png. At grading time this program only
// copies that file to the output directory, so it needs no network, no
// clock and no randomness, and always writes identical bytes.
//
// The harness sets MAKEFUN_OUTPUT_DIR; without it we fall back to /output,
// the path the competition rules name.

import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { join, resolve } from "node:path";

const source = resolve(import.meta.dirname, "assets", "entry.png");
if (!existsSync(source)) {
  throw new Error(`entry image missing: ${source}`);
}

const outDir = process.env.MAKEFUN_OUTPUT_DIR ?? "/output";
mkdirSync(outDir, { recursive: true });

const target = join(outDir, "entry.png");
copyFileSync(source, target);
console.log(`wrote ${target}`);

#!/usr/bin/env python3
"""Simula o corte central 1:1 que o Instagram (desktop) aplica a um 4:5 e diz se o conteúdo crítico sobrevive.

Uso:
  python3 check_crop.py OUT_DIR                 # usa OUT_DIR/manifest.json (caixas exatas de cada texto)
  python3 check_crop.py arte.png [--preview p]  # qualquer PNG (ex.: arte antiga): varre pixels das faixas cortadas

Saída: JSON + código 0 (sobrevive) | 1 (perde conteúdo) | 2 (erro de uso)
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw


def center_square(w, h):
    s = min(w, h)
    return ((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)


def band_content(img: Image.Image, box) -> dict:
    """Quantos pixels 'de conteúdo' (diferentes do fundo) existem numa faixa."""
    reg = img.crop(box).convert("RGB")
    bg = img.getpixel((2, 2))
    diff = ImageChops.difference(reg, Image.new("RGB", reg.size, bg)).convert("L").point(lambda v: 255 if v > 28 else 0)
    bb = diff.getbbox()
    n = diff.histogram()[255]
    return {"content_pixels": n, "content_bbox": None if not bb else [bb[0] + box[0], bb[1] + box[1], bb[2] + box[0], bb[3] + box[1]]}


def write_preview(img, sq, path):
    w, h = img.size
    prev = img.convert("RGB").copy()
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rectangle([0, 0, w, sq[1]], fill=(255, 0, 0, 90))
    d.rectangle([0, sq[3], w, h], fill=(255, 0, 0, 90))
    prev = Image.alpha_composite(prev.convert("RGBA"), ov).convert("RGB")
    out = Image.new("RGB", (w + 40 + (sq[2] - sq[0]), h), (136, 136, 136))
    out.paste(prev, (0, 0))
    out.paste(img.convert("RGB").crop(sq), (w + 40, (h - (sq[3] - sq[1])) // 2))
    out.thumbnail((1400, 1400))
    out.save(path)


def check(path: Path, preview: Path | None = None) -> dict:
    manifest = None
    if path.is_dir():
        mp = path / "manifest.json"
        manifest = json.loads(mp.read_text(encoding="utf-8"))
        path = path / "feed.png"
    elif path.suffix == ".json":
        manifest = json.loads(path.read_text(encoding="utf-8"))
        path = path.parent / "feed.png"
    img = Image.open(path)
    w, h = img.size
    sq = center_square(w, h)
    res = {"image": str(path), "size": [w, h], "aspect_w_over_h": round(w / h, 4), "center_square": list(sq)}
    if w == h:
        res.update({"survives_center_square": True, "note": "imagem já é 1:1"})
        return res
    top, bot = (0, 0, w, sq[1]), (0, sq[3], w, h)
    res["cut_bands"] = {"top": list(top), "bottom": list(bot)}
    if manifest:
        entry = manifest["files"][path.name]
        lost, kept = [], []
        for b in entry["boxes"]:
            x0, y0, x1, y1 = b["box"]
            inside = y0 >= sq[1] and y1 <= sq[3] and x0 >= sq[0] and x1 <= sq[2]
            if b["critical"]:
                (kept if inside else lost).append(b["name"])
        res.update({"method": "manifest_boxes", "critical_kept": kept, "critical_lost": lost, "survives_center_square": not lost})
        dec = [b["name"] for b in entry["boxes"] if not b["critical"] and (b["box"][1] < sq[1] or b["box"][3] > sq[3])]
        res["decorative_cut"] = dec
    else:
        t, b = band_content(img, top), band_content(img, bot)
        res.update({"method": "pixel_scan", "top_band": t, "bottom_band": b,
                    "survives_center_square": t["content_pixels"] == 0 and b["content_pixels"] == 0,
                    "note": "sem manifest: qualquer conteúdo nas faixas é tratado como perdido"})
    if preview:
        write_preview(img, sq, preview)
        res["preview"] = str(preview)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="OUT_DIR do prisma_render, manifest.json, ou um PNG")
    ap.add_argument("--preview", default="", help="salva PNG com as faixas cortadas em vermelho + o quadrado resultante")
    a = ap.parse_args()
    p = Path(a.target)
    if not p.exists():
        print(json.dumps({"error": f"não existe: {p}"})); return 2
    r = check(p, Path(a.preview) if a.preview else None)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r["survives_center_square"] else 1


if __name__ == "__main__":
    sys.exit(main())

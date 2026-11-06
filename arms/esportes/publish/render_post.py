#!/usr/bin/env python3
"""Prisma Esportes — VARIANT nobars (Marketing review).

Cópia de prisma-eletrico-unico-v1 SEM as faixas coloridas de topo/rodapé.
NÃO é o arquivo de produção (publish/render_post.py permanece intacto).

Mudanças vs patched único:
- Remove spectrum + barra magenta no topo e no rodapé (feed e Stories).
- Marca "PRISMA · ESPORTES" vira wordmark tipográfico (accent magenta) no topo limpo.
- Conteúdo sobe/rebalanceia o espaço liberado pelas barras (pill, frame, manchete).
- Identidade viva permanece via pill ciano, AGORA, kicker tipográfico, anel laranja do frame e assinatura.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path("/workspace/prisma-esportes")
FONT = ROOT / "v3" / "fonts"
OUT = ROOT / "publish" / "out"
OUT.mkdir(parents=True, exist_ok=True)

P = {
    "bg": "#FAFBFF",
    "surface": "#FFFFFF",
    "surface2": "#EEF3FF",
    "text": "#0B1220",
    "muted": "#4B5568",
    "line": "#D8DEE9",
    "accent": "#E11D74",
    "accent2": "#0095E8",
    "accent3": "#FF6A00",
    "signal": "#FF3B00",
    "on_accent": "#FFFFFF",
    "spectrum": ["#0095E8", "#E11D74", "#FF6A00", "#B8F000"],
}


def hex_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def fnt(name: str, size: int):
    return ImageFont.truetype(str(FONT / name), size)


def wrap(text: str, font, max_w: float):
    words = (text or "").split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if font.getlength(trial) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def spectrum(draw, x, y, w, h, colors):
    segs = len(colors) - 1
    for i in range(max(w, 1)):
        t = i / max(w - 1, 1)
        seg = min(int(t * segs), segs - 1)
        local = (t * segs) - seg
        c0, c1 = hex_rgb(colors[seg]), hex_rgb(colors[seg + 1])
        c = tuple(int(c0[j] + (c1[j] - c0[j]) * local) for j in range(3))
        draw.line([(x + i, y), (x + i, y + h - 1)], fill=c)


def cover_crop(im: Image.Image, tw: int, th: int) -> Image.Image:
    """Center-crop then resize to target (no stretch)."""
    iw, ih = im.size
    scale = max(tw / iw, th / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return im.crop((left, top, left + tw, top + th))


def fit_headline(title: str, max_w: float, size_max: int, size_min: int, max_lines: int):
    chosen = (fnt("Outfit-Bold.ttf", size_min), wrap(title, fnt("Outfit-Bold.ttf", size_min), max_w)[:max_lines], size_min)
    for size in range(size_max, size_min - 1, -2):
        font = fnt("Outfit-Bold.ttf", size)
        lines = wrap(title, font, max_w)
        if len(lines) <= max_lines:
            return font, lines, size
        chosen = (font, lines[:max_lines], size)
    return chosen


def _header(d, W, brand_y=44, brand_size=30, bar_h=(22, 110)):
    """Wordmark only — no colored top bar / spectrum strip."""
    # small orange accent tick beside the brand (family ring color), not a full bar
    d.rounded_rectangle([80, brand_y + 6, 80 + 10, brand_y + brand_size - 2], radius=3, fill=hex_rgb(P["accent3"]))
    d.text((104, brand_y), "PRISMA · ESPORTES", font=fnt("Inter-SemiBold.ttf", brand_size), fill=hex_rgb(P["accent"]))


def _pill(d, pill: str, y=140):
    pill_u = (pill or "FUTEBOL").upper()
    fp = fnt("Inter-SemiBold.ttf", 26)
    pw = fp.getlength(pill_u) + 44
    d.rounded_rectangle([80, y, 80 + pw, y + 52], radius=10, fill=hex_rgb(P["accent2"]))
    d.text((102, y + 10), pill_u, font=fp, fill=hex_rgb(P["on_accent"]))


def _draw_photo_credit(d, inner, credit: str):
    if not credit:
        return
    label = credit if credit.lower().startswith("foto:") else f"Foto: {credit}"
    font = fnt("Inter-Medium.ttf", 22)
    pad_x, pad_y = 14, 8
    tw = font.getlength(label)
    x1, y1 = inner[2] - 12, inner[3] - 12
    x0, y0 = x1 - tw - 2 * pad_x, y1 - 22 - 2 * pad_y
    # translucent dark plate for legibility
    d.rounded_rectangle([x0, y0, x1, y1], radius=8, fill=(11, 18, 32, 180) if False else hex_rgb(P["text"]))
    # use semi-opaque via overlay handled by caller when RGBA; for RGB use solid dark + white text
    d.rounded_rectangle([x0, y0, x1, y1], radius=8, fill=hex_rgb(P["text"]))
    d.text((x0 + pad_x, y0 + pad_y), label, font=font, fill=hex_rgb(P["on_accent"]))


def _draw_typo_fallback(d, inner, competition: str, kicker: str):
    """Accent block + competition name + big score/number. Never prints FRAME."""
    x0, y0, x1, y1 = inner
    # fill inner with soft surface2, then accent panel
    d.rounded_rectangle(inner, radius=14, fill=hex_rgb(P["surface2"]))
    panel = [x0 + 28, y0 + 28, x1 - 28, y1 - 28]
    d.rounded_rectangle(panel, radius=18, fill=hex_rgb(P["accent3"]))
    comp = (competition or "FUTEBOL").upper()
    fc = fnt("Inter-SemiBold.ttf", 28)
    kick = (kicker or "•").strip() or "•"
    size = 140
    while size >= 56:
        fk = fnt("Outfit-Bold.ttf", size)
        if fk.getlength(kick) <= (panel[2] - panel[0] - 48):
            break
        size -= 4
    fk = fnt("Outfit-Bold.ttf", size)
    # vertically center competition + kicker as a stack inside the orange panel
    stack_h = 36 + 16 + int(size * 1.05)
    top = panel[1] + ((panel[3] - panel[1]) - stack_h) / 2
    cw = fc.getlength(comp)
    d.text(((panel[0] + panel[2] - cw) / 2, top), comp, font=fc, fill=hex_rgb(P["on_accent"]))
    kw = fk.getlength(kick)
    d.text(((panel[0] + panel[2] - kw) / 2, top + 36 + 16), kick, font=fk, fill=hex_rgb(P["on_accent"]))


def _frame(
    d,
    box,
    photo: Path | None = None,
    *,
    competition: str = "",
    kicker: str = "",
    photo_credit: str = "",
):
    x0, y0, x1, y1 = box
    d.rounded_rectangle([x0, y0, x1, y1], radius=20, fill=hex_rgb(P["surface2"]))
    # accent ring bar left (family orange)
    d.rectangle([x0, y0 + 8, x0 + 16, y1 - 8], fill=hex_rgb(P["accent3"]))
    inner = [x0 + 16, y0 + 8, x1 - 8, y1 - 8]
    d.rounded_rectangle(inner, radius=14, fill=hex_rgb(P["surface"]))
    if photo and Path(photo).exists():
        iw, ih = inner[2] - inner[0], inner[3] - inner[1]
        im = cover_crop(Image.open(photo).convert("RGB"), iw, ih)
        return im, (inner[0], inner[1]), inner
    _draw_typo_fallback(d, inner, competition, kicker)
    return None, None, inner


def render_feed(
    title: str,
    pill: str,
    source: str,
    stamp: str,
    photo: str | None = None,
    *,
    kicker: str = "",
    photo_credit: str = "",
    slides: int = 1,
) -> Path:
    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), hex_rgb(P["bg"]))
    d = ImageDraw.Draw(img)
    _header(d, W)
    # Content pulled up into the space the magenta top bar used to occupy
    _pill(d, pill, 100)
    # Taller frame: reclaim top + a bit of bottom margin from removed bars
    pasted, pos, inner = _frame(
        d,
        [80, 176, W - 80, 820],
        Path(photo) if photo else None,
        competition=pill,
        kicker=kicker,
        photo_credit=photo_credit,
    )
    if pasted is not None:
        img.paste(pasted, pos)
        d = ImageDraw.Draw(img)
        _draw_photo_credit(d, inner, photo_credit)

    ft, lines, size = fit_headline(title, W - 160, size_max=70, size_min=46, max_lines=3)
    y = 852
    line_h = int(size * 1.18)
    for line in lines:
        d.text((80, y), line, font=ft, fill=hex_rgb(P["text"]))
        y += line_h

    meta = f"Fonte: {source}  ·  Prisma · Esportes"
    meta_y = min(1220, y + 36)
    d.text((80, meta_y), meta, font=fnt("Inter-Regular.ttf", 28), fill=hex_rgb(P["muted"]))

    # Carousel dots ONLY when there is more than one slide (clean bottom, no bar)
    if slides > 1:
        n = min(int(slides), 5)
        span = (n - 1) * 30
        start = W // 2 - span // 2
        for i in range(n):
            x = start + i * 30
            fill = P["accent"] if i == 0 else P["line"]
            d.ellipse([x - 7, H - 48, x + 7, H - 34], fill=hex_rgb(fill))

    path = OUT / f"feed-{stamp}.png"
    img.save(path, "PNG")
    return path


def render_stories(
    title: str,
    subtitle: str,
    source: str,
    stamp: str,
    photo: str | None = None,
    *,
    kicker: str = "",
    photo_credit: str = "",
    pill: str = "",
) -> Path:
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), hex_rgb(P["bg"]))
    d = ImageDraw.Draw(img)
    # Wordmark (no colored top bar)
    d.rounded_rectangle([80, 50, 90, 78], radius=3, fill=hex_rgb(P["accent3"]))
    d.text((104, 44), "PRISMA · ESPORTES", font=fnt("Inter-SemiBold.ttf", 32), fill=hex_rgb(P["accent"]))
    badge = "AGORA"
    fbadge = fnt("Inter-SemiBold.ttf", 30)
    bw = fbadge.getlength(badge) + 52
    d.rounded_rectangle([80, 110, 80 + bw, 174], radius=12, fill=hex_rgb(P["signal"]))
    d.text((106, 122), badge, font=fbadge, fill=hex_rgb(P["on_accent"]))
    ft, lines, size = fit_headline(title, W - 160, size_max=78, size_min=52, max_lines=4)
    y = 210
    line_h = int(size * 1.15)
    for line in lines:
        d.text((80, y), line, font=ft, fill=hex_rgb(P["text"]))
        y += line_h
    fs = fnt("Inter-Regular.ttf", 38)
    y += 12
    for line in wrap(subtitle or "", fs, W - 160)[:3]:
        d.text((80, y), line, font=fs, fill=hex_rgb(P["muted"]))
        y += 50
    # Frame shifted up into freed header space; slightly taller
    pasted, pos, inner = _frame(
        d,
        [80, 860, W - 80, 1560],
        Path(photo) if photo else None,
        competition=pill or "Futebol",
        kicker=kicker,
        photo_credit=photo_credit,
    )
    if pasted is not None:
        img.paste(pasted, pos)
        d = ImageDraw.Draw(img)
        _draw_photo_credit(d, inner, photo_credit)
    d.text((80, 1640), f"Fonte: {source}", font=fnt("Inter-Regular.ttf", 30), fill=hex_rgb(P["muted"]))
    d.text((80, 1690), "@prismaesportesbr", font=fnt("Inter-Regular.ttf", 30), fill=hex_rgb(P["accent2"]))
    # no bottom spectrum / magenta bar
    path = OUT / f"stories-{stamp}.png"
    img.save(path, "PNG")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--pill", default="Futebol")
    ap.add_argument("--source", required=True)
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--photo", default="")
    ap.add_argument("--photo-credit", default="", help='Ex.: "Fulano / CC BY 4.0" → "Foto: Fulano / CC BY 4.0"')
    ap.add_argument("--kicker", default="", help="Placar ou número-chave no fallback tipográfico (ex.: 6×1)")
    ap.add_argument("--slides", type=int, default=1, help="Qtd de slides do carrossel; dots só se > 1")
    ap.add_argument("--stamp", required=True)
    ap.add_argument("--out-dir", default="", help="Override output dir (review previews)")
    ap.add_argument("--bullet", action="append", default=[])  # backward compat; ignored in art
    args = ap.parse_args()
    global OUT
    if args.out_dir:
        OUT = Path(args.out_dir)
        OUT.mkdir(parents=True, exist_ok=True)
    photo = args.photo or None
    feed = render_feed(
        args.title,
        args.pill,
        args.source,
        args.stamp,
        photo,
        kicker=args.kicker,
        photo_credit=args.photo_credit,
        slides=args.slides,
    )
    stories = render_stories(
        args.title,
        args.subtitle or args.title,
        args.source,
        args.stamp,
        photo,
        kicker=args.kicker,
        photo_credit=args.photo_credit,
        pill=args.pill,
    )
    print(
        json.dumps(
            {
                "feed": str(feed),
                "stories": str(stories),
                "template": "prisma-eletrico-unico-v1-nobars",
            }
        )
    )


if __name__ == "__main__":
    main()

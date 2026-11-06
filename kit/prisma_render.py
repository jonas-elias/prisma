#!/usr/bin/env python3
"""Prisma — renderizador padronizado e determinístico (família Prisma).

Uso:
  python3 prisma_render.py --segment esportes --post post.json --out-dir DIR

Lê SOMENTE family.json + segments/<segment>.json + post.json. Não há flags de estilo.
Saídas em DIR (nomes fixos):
  feed.png (1080x1350, slide 1)   feed-02.png ... (carrossel)   stories.png (1080x1920)
  caption.txt (legenda montada pelo template)   manifest.json (hashes, caixas, crop check)

Códigos de saída: 0 ok | 2 post/config inválido | 3 duplicado (já publicado) | 4 falha de layout/crop (bug)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import PIL
from PIL import Image, ImageDraw, ImageFont, ImageOps, features

KIT = Path(__file__).resolve().parent
FONTS = KIT / "fonts"
TEMPLATE_VERSION = "prisma-family-v1"
FEED_W, FEED_H = 1080, 1350
STORY_W, STORY_H = 1080, 1920
# Corte central 1:1 de um 4:5 remove 135 px em cima e embaixo.
SQUARE_CUT = (FEED_H - FEED_W) // 2  # 135
SAFE_MARGIN = 16  # folga mínima dentro do quadrado central
STORY_SAFE_TOP, STORY_SAFE_BOTTOM = 250, 1670  # áreas cobertas pela UI dos Stories
MARGIN_X = 80
FONT_FILES = ["Outfit-Bold.ttf", "Outfit-SemiBold.ttf", "Inter-SemiBold.ttf", "Inter-Regular.ttf", "Inter-Medium.ttf"]


class PostError(Exception):
    pass


class DuplicateError(Exception):
    pass


class LayoutError(Exception):
    pass


# ---------------------------------------------------------------- utilidades
_font_cache: dict = {}


def fnt(name: str, size: int):
    key = (name, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(FONTS / name), size, layout_engine=ImageFont.Layout.BASIC)
    return _font_cache[key]


def rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(Path(p).read_bytes())


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
    return lines


def fits_words(lines, font, max_w):
    return all(font.getlength(l) <= max_w for l in lines)


def fit_text(text: str, font_name: str, max_w: float, size_max: int, size_min: int, max_lines: int, step: int = 2):
    """Maior tamanho em que o texto cabe em max_lines sem estourar a largura. None se não couber."""
    for size in range(size_max, size_min - 1, -step):
        f = fnt(font_name, size)
        lines = wrap(text, f, max_w)
        if 0 < len(lines) <= max_lines and fits_words(lines, f, max_w):
            return f, lines, size
    return None


def host_of(url: str) -> str:
    try:
        h = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def domain_match(host: str, domains) -> bool:
    host = host.lower()
    for d in domains:
        d = d.lower()
        d = d[4:] if d.startswith("www.") else d
        if host == d or host.endswith("." + d):
            return True
    return False


def norm_url(url: str) -> str:
    s = urlsplit(url.strip())
    host = (s.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    path = s.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, "", ""))


def norm_title(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")


def parse_iso(s: str, field: str) -> dt.datetime:
    try:
        d = dt.datetime.fromisoformat(s)
    except (TypeError, ValueError):
        raise PostError(f"{field}: data inválida '{s}'. Use ISO 8601 com fuso, ex.: 2026-11-05T22:10:00-03:00")
    if d.tzinfo is None:
        raise PostError(f"{field}: falta o fuso horário (ex.: -03:00) em '{s}'")
    return d


def normalize_license(s: str) -> str:
    t = re.sub(r"[\s_-]+", " ", (s or "").strip()).upper()
    t = t.replace("ATTRIBUTION SHAREALIKE", "BY SA").replace("ATTRIBUTION", "BY")
    m = re.fullmatch(r"(?:CC )?(BY SA|BY) ?(\d\.\d)(?: INTERNATIONAL| GENERIC| UNPORTED| BR)?", t)
    if m:
        return f"CC {m.group(1).replace(' ', '-')} {m.group(2)}"
    if t in ("CC0", "CC0 1.0", "CC ZERO", "CC 0", "CC 0 1.0", "PUBLIC DOMAIN DEDICATION CC0"):
        return "CC0 1.0"
    if t in ("UNSPLASH", "UNSPLASH LICENSE"):
        return "Unsplash License"
    if t in ("PEXELS", "PEXELS LICENSE"):
        return "Pexels License"
    return (s or "").strip()


# ---------------------------------------------------------------- configuração
def _strip_comments(obj):
    if isinstance(obj, dict):
        return {k: _strip_comments(v) for k, v in obj.items() if not k.startswith("$comment")}
    if isinstance(obj, list):
        return [_strip_comments(v) for v in obj]
    return obj


HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
SEGMENT_KEYS = {"segment_id", "name", "wordmark", "signature", "handle", "accents", "hashtags", "pills", "key_label",
                "known_sources", "official_source_domains", "official_photo_origins", "state"}


def load_config(segment: str):
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,30}", segment or ""):
        raise PostError(f"--segment inválido: '{segment}' (use o id em minúsculas, ex.: esportes). Arquivos '_*.json' são modelos.")
    fam_raw = json.loads((KIT / "family.json").read_text(encoding="utf-8"))
    p = KIT / "segments" / f"{segment}.json"
    if not p.exists():
        avail = sorted(x.stem for x in (KIT / "segments").glob("*.json") if not x.stem.startswith("_"))
        raise PostError(f"segmento '{segment}' não existe. Disponíveis: {', '.join(avail)}")
    raw_text = p.read_text(encoding="utf-8")
    if "TROCAR" in raw_text:
        raise PostError(f"segments/{segment}.json ainda tem valores 'TROCAR' do modelo; complete e aprove antes de usar")
    fam = _strip_comments(fam_raw)
    seg = _strip_comments(json.loads(raw_text))
    unknown = set(seg) - SEGMENT_KEYS
    missing = SEGMENT_KEYS - set(seg)
    if unknown or missing:
        raise PostError(f"segments/{segment}.json: chaves desconhecidas {sorted(unknown)} / faltando {sorted(missing)}")
    if seg["segment_id"] != segment:
        raise PostError(f"segments/{segment}.json: segment_id '{seg['segment_id']}' difere do nome do arquivo")
    for k, v in list(seg["accents"].items()) + list(fam["base_palette"].items()):
        if not HEX_RE.match(v):
            raise PostError(f"cor inválida '{k}': {v}")
    if set(seg["accents"]) != {"wordmark", "pill", "ring"}:
        raise PostError("accents deve ter exatamente wordmark, pill, ring")
    if not seg["handle"].startswith("@"):
        raise PostError("handle deve começar com @")
    return fam, seg


# ---------------------------------------------------------------- validação do post
POST_KEYS = {"title", "dek", "caption_body", "source", "source_url", "competition", "kind", "key", "photo",
             "published_at", "slides", "sample", "source_exception"}
PHOTO_KEYS = {"path", "author", "origin", "license", "generic"}


def validate_post(post: dict, fam: dict, seg: dict, post_dir: Path, now: dt.datetime) -> dict:
    errs: list[str] = []

    def err(m):
        errs.append(m)

    if not isinstance(post, dict):
        raise PostError("post.json deve ser um objeto JSON")
    unknown = set(post) - POST_KEYS
    if unknown:
        err(f"campos desconhecidos: {sorted(unknown)} (sem campos livres de estilo; veja post.schema.json)")
    for k in ("title", "caption_body", "source", "source_url", "competition", "kind", "published_at"):
        if k not in post or post[k] in (None, "", []):
            err(f"campo obrigatório ausente: {k}")
    if errs:
        raise PostError("\n".join(errs))

    out: dict = {}
    banned = [b.lower() for b in fam["banned_terms"]]

    def check_text(field, s, min_len, max_len):
        if not isinstance(s, str):
            err(f"{field}: deve ser texto"); return ""
        s2 = re.sub(r"\s+", " ", s).strip()
        if not (min_len <= len(s2) <= max_len):
            err(f"{field}: {len(s2)} caracteres (permitido {min_len}–{max_len})")
        if EMOJI_RE.search(s2):
            err(f"{field}: sem emoji na arte/legenda gerada")
        low = norm_title(s2)
        for b in banned:
            if re.search(r"(?<![a-z0-9])" + re.escape(norm_title(b)) + r"(?![a-z0-9])", low):
                err(f"{field}: termo proibido (clickbait/rumor): '{b}'")
        if "!!" in s2 or "??" in s2:
            err(f"{field}: pontuação de clickbait ('!!'/'??')")
        letters = [c for c in s2 if c.isalpha()]
        if len(letters) > 12 and sum(c.isupper() for c in letters) / len(letters) > 0.6:
            err(f"{field}: não usar CAIXA ALTA")
        return s2

    out["title"] = check_text("title", post["title"], 20, 140)
    out["dek"] = check_text("dek", post["dek"], 10, 200) if post.get("dek") else ""
    body = post["caption_body"]
    out["caption_body"] = ""
    if not isinstance(body, str):
        err("caption_body: deve ser texto")
    else:
        b = "\n".join(re.sub(r"[ \t]+", " ", l).strip() for l in body.strip().splitlines())
        b = re.sub(r"\n{3,}", "\n\n", b)
        cmin, cmax = fam["caption"]["body_min_chars"], fam["caption"]["body_max_chars"]
        if not (cmin <= len(b) <= cmax):
            err(f"caption_body: {len(b)} caracteres (permitido {cmin}–{cmax})")
        if "#" in b:
            err("caption_body: sem hashtags (o template adiciona as oficiais)")
        if re.search(r"(?im)^\s*(fonte|foto|cr[eé]dito)s?\s*:", b) or re.search(r"(?i)\bfonte\s*:", b):
            err("caption_body: não escreva 'Fonte:'/'Foto:' (o template adiciona)")
        if re.search(r"https?://|www\.", b, re.I):
            err("caption_body: sem links (Instagram não deixa clicar; a fonte vai por nome)")
        if re.search(r"(?<![\w.])@\w", b):
            err("caption_body: sem @menções (não inventar handles)")
        if seg["signature"].lower() in b.lower():
            err("caption_body: não escreva a assinatura (o template adiciona)")
        if EMOJI_RE.search(b):
            err("caption_body: sem emoji")
        for t in banned:
            if re.search(r"(?<![a-z0-9])" + re.escape(norm_title(t)) + r"(?![a-z0-9])", norm_title(b)):
                err(f"caption_body: termo proibido (clickbait/rumor): '{t}'")
        out["caption_body"] = b

    # fontes
    src = post["source"]
    names = [src] if isinstance(src, str) else src if isinstance(src, list) else None
    if not names or not all(isinstance(n, str) and 2 <= len(n.strip()) <= 40 for n in names) or len(names) > 3:
        err("source: texto (ou lista de até 3) com 2–40 caracteres cada, ex.: \"ge\" ou [\"Folha\", \"CNN Brasil\"]")
        names = []
    names = [n.strip() for n in names]
    if any(re.search(r"https?://|\.com|\.br", n, re.I) for n in names):
        err("source: use o NOME da fonte (ex.: ge), não a URL")
    out["sources"] = names
    out["source_label"] = " / ".join(names)
    su = post["source_url"]
    if not isinstance(su, str) or not re.match(r"^https?://[^\s/]+\.[^\s/]+/\S*$", su.strip()):
        err("source_url: URL http(s) completa da matéria")
        out["source_url"] = ""
        out["source_url_norm"] = ""
    else:
        out["source_url"] = su.strip()
        out["source_url_norm"] = norm_url(su)
        h = host_of(su)
        if domain_match(h, ["instagram.com", "facebook.com", "x.com", "twitter.com", "tiktok.com", "youtube.com"]):
            err("source_url: rede social não é fonte de notícia; use a matéria do veículo/órgão oficial")
        if names:
            canon_name = canonical_source(names[0], seg)
            ent = seg["known_sources"].get(canon_name)
            if ent and not domain_match(h, ent["domains"]):
                err(f"source_url: domínio '{h}' não é de '{names[0]}' ({', '.join(ent['domains'])}). O 1º nome em source deve ser o da URL")

    # editoria
    comp = post["competition"]
    canon = {norm_title(p): p for p in seg["pills"]}
    if not isinstance(comp, str) or norm_title(comp) not in canon:
        err(f"competition '{comp}' não permitida. Use uma de: {', '.join(seg['pills'])}")
        out["competition"] = ""
    else:
        out["competition"] = canon[norm_title(comp)]

    # data / AGORA
    try:
        pub = parse_iso(post["published_at"], "published_at")
        age_min = (now - pub).total_seconds() / 60
        out["published_at"] = pub.isoformat()
        if age_min < -fam["news"]["future_tolerance_minutes"]:
            err(f"published_at está no futuro ({pub.isoformat()} > agora {now.isoformat()})")
        if age_min > fam["news"]["max_age_hours"] * 60:
            err(f"notícia velha: {age_min/60:.1f} h (máx. {fam['news']['max_age_hours']} h). Não publicar")
        out["agora"] = bool(age_min <= fam["news"]["agora_max_age_minutes"])
        out["age_minutes"] = round(age_min, 1)
    except PostError as e:
        err(str(e))
        out["agora"] = False

    # tipo
    kind = post["kind"]
    out["kind"] = kind
    if kind not in ("typo", "photo"):
        err("kind: 'typo' ou 'photo'")
    key = post.get("key")
    if kind == "typo":
        if not isinstance(key, str) or not key.strip():
            err(f"key obrigatório em kind=typo ({seg['key_label']})")
            out["key"] = ""
        else:
            k = key.strip()
            m = re.fullmatch(r"(\d{1,2})\s*[x×X]\s*(\d{1,2})", k)
            if m:
                k = f"{m.group(1)}×{m.group(2)}"
            if len(k) > 12:
                err("key: máx. 12 caracteres (ex.: 3×1, 19 anos)")
            out["key"] = k
        if post.get("photo"):
            err("kind=typo não leva photo (use kind=photo)")
    elif kind == "photo":
        if key:
            err("key só existe em kind=typo")
        out["key"] = ""
        out["photo"] = validate_photo(post.get("photo"), fam, seg, post_dir, out.get("source_url", ""), err)

    # carrossel
    slides = post.get("slides", [])
    out["slides"] = []
    if slides:
        if not isinstance(slides, list) or len(slides) > 9:
            err("slides: lista de até 9 slides extras [{\"text\": \"...\"}]")
        else:
            for i, s in enumerate(slides, start=2):
                if not isinstance(s, dict) or set(s) != {"text"}:
                    err(f"slides[{i-2}]: formato {{\"text\": \"...\"}}")
                    continue
                out["slides"].append(check_text(f"slides[{i-2}].text", s["text"], 20, 420))

    sample = post.get("sample", False)
    if not isinstance(sample, bool):
        err("sample: true/false")
    out["sample"] = bool(sample)

    # exceção da regra de rotação de fontes
    out["source_key"] = canonical_source(names[0], seg) if names else ""
    out["source_official"] = bool(names) and is_official_source(names[0], out.get("source_url", ""), seg)
    out["source_exception"] = None
    exc = post.get("source_exception")
    if exc is not None:
        rot = fam["source_rotation"]
        if not isinstance(exc, dict) or set(exc) != {"type", "reason"}:
            err('source_exception: formato {"type": "breaking"|"official_exclusive", "reason": "..."}')
        else:
            if exc["type"] not in rot["exception_types"]:
                err(f"source_exception.type '{exc['type']}' inválido. Use: {', '.join(rot['exception_types'])}")
            reason = re.sub(r"\s+", " ", str(exc.get("reason") or "")).strip()
            if len(reason) < rot["exception_reason_min_chars"]:
                err(f"source_exception.reason: explique em pelo menos {rot['exception_reason_min_chars']} caracteres por que só essa fonte serve")
            if exc["type"] == "official_exclusive" and not out["source_official"]:
                err(f"source_exception official_exclusive só vale para fonte OFICIAL (CBF, clube, atleta: domínio em official_source_domains ou fonte official=true). '{names[0] if names else '?'}' / {host_of(out.get('source_url', ''))} não é oficial")
            out["source_exception"] = {"type": exc["type"], "reason": reason}

    if errs:
        raise PostError("\n".join(errs))
    return out


def validate_photo(ph, fam, seg, post_dir: Path, source_url: str, err):
    pol = fam["photo_policy"]
    if not isinstance(ph, dict):
        err("kind=photo exige photo {path, author, origin, license}. Sem foto liberada => use kind=typo")
        return None
    unknown = set(ph) - PHOTO_KEYS
    if unknown:
        err(f"photo: campos desconhecidos {sorted(unknown)}")
    for k in ("path", "author", "origin", "license"):
        if not isinstance(ph.get(k), str) or not ph.get(k).strip():
            err(f"photo.{k} obrigatório")
    if any(not isinstance(ph.get(k), str) or not ph.get(k).strip() for k in ("path", "author", "origin", "license")):
        return None
    res = {"author": ph["author"].strip(), "origin": ph["origin"].strip()}
    a = res["author"].lower()
    for t in pol["blocked_author_terms"]:
        if t in a:
            err(f"photo.author '{res['author']}': '{t}' não é autor com licença (foto de agência/portal/reprodução proibida)")
    if len(res["author"]) > 40:
        err("photo.author: máx. 40 caracteres")
    origin = res["origin"]
    if not re.match(r"^https://\S+$", origin):
        err("photo.origin: URL https da PÁGINA da foto com a licença (ex.: https://commons.wikimedia.org/wiki/File:...)")
        return None
    h = host_of(origin)
    if domain_match(h, pol["blocked_photo_domains"]):
        err(f"photo.origin '{h}': foto de portal/agência/rede social/busca é PROIBIDA. Use Wikimedia/Unsplash/Pexels/oficial com CC ou kind=typo")
    if source_url and host_of(source_url) and domain_match(h, [host_of(source_url)]):
        err("photo.origin é do mesmo domínio da fonte da notícia: foto da matéria é PROIBIDA")
    lic = normalize_license(ph["license"])
    res["license"] = lic
    origin_cls, label, allowed, generic_only = None, None, [], False
    for name, o in pol["origins"].items():
        if domain_match(h, o["domains"]):
            origin_cls, label, allowed, generic_only = name, o["label"], o["licenses"], o["generic_only"]
    off = seg["official_photo_origins"]
    if origin_cls is None and domain_match(h, off["label_by_domain"].keys()):
        origin_cls = "official"
        label = next(v for k, v in off["label_by_domain"].items() if domain_match(h, [k]))
        allowed = off["licenses"]
    if origin_cls is None:
        err(f"photo.origin '{h}' não está na lista de origens permitidas (Wikimedia Commons, Unsplash, Pexels, oficiais do segmento)")
        return None
    if lic not in allowed:
        err(f"photo.license '{ph['license']}' não permitida para {label}. Aceitas: {', '.join(allowed)} (NC/ND/'Divulgação' não servem)")
    if generic_only and ph.get("generic") is not True:
        err(f"photo de {label}: só imagem genérica (sem pessoa real/clube/escudo identificável). Declare photo.generic=true")
    res["origin_label"] = label
    res["origin_class"] = origin_cls
    res["adapted"] = lic.startswith("CC BY-SA")  # o render recorta/redimensiona
    p = Path(ph["path"])
    p = p if p.is_absolute() else (post_dir / p)
    res["path"] = str(p.resolve())
    if not p.exists():
        err(f"photo.path não existe: {p}")
        return res
    try:
        with Image.open(p) as im:
            im = ImageOps.exif_transpose(im)
            w, h2 = im.size
    except Exception as e:  # noqa: BLE001
        err(f"photo.path não é imagem legível: {e}")
        return res
    if w < pol["min_width"] or h2 < pol["min_height"]:
        err(f"photo: {w}x{h2} é pequena demais (mín. {pol['min_width']}x{pol['min_height']})")
    res["sha256"] = sha256_file(p)
    res["size"] = [w, h2]
    return res


# ---------------------------------------------------------------- desenho
class Canvas:
    def __init__(self, w, h, pal):
        self.img = Image.new("RGB", (w, h), rgb(pal["bg"]))
        self.d = ImageDraw.Draw(self.img)
        self.boxes: list[dict] = []  # caixas de tinta dos elementos

    def text(self, xy, s, font, fill, name, critical=True):
        self.d.text(xy, s, font=font, fill=fill)
        x0, y0, x1, y1 = self.d.textbbox(xy, s, font=font)
        self.boxes.append({"name": name, "box": [int(x0), int(y0), int(x1), int(y1)], "critical": critical})
        return (x0, y0, x1, y1)

    def add_box(self, name, box, critical=True):
        self.boxes.append({"name": name, "box": [int(v) for v in box], "critical": critical})


def palette(fam, seg):
    p = dict(fam["base_palette"])
    p.update({"accent": seg["accents"]["wordmark"], "accent2": seg["accents"]["pill"], "accent3": seg["accents"]["ring"]})
    return p


def draw_wordmark(c: Canvas, seg, pal, y, size):
    f = fnt("Inter-SemiBold.ttf", size)
    asc = f.getbbox("PRISMA")[1]
    c.d.rounded_rectangle([MARGIN_X, y + asc, MARGIN_X + 10, y + size - 2], radius=3, fill=rgb(pal["accent3"]))
    c.add_box("tick", [MARGIN_X, y + asc, MARGIN_X + 10, y + size - 2], critical=False)
    c.text((MARGIN_X + 24, y), seg["wordmark"], f, rgb(pal["accent"]), "wordmark")


def draw_agora(c: Canvas, pal, right_x, y, size=24):
    f = fnt("Inter-SemiBold.ttf", size)
    w = f.getlength("AGORA") + 40
    h = size + 22
    c.d.rounded_rectangle([right_x - w, y, right_x, y + h], radius=10, fill=rgb(pal["signal"]))
    c.add_box("agora_badge", [right_x - w, y, right_x, y + h])
    tb = f.getbbox("AGORA")
    c.d.text((right_x - w + 20, y + (h - (tb[3] + tb[1])) / 2), "AGORA", font=f, fill=rgb(pal["on_accent"]))


def draw_pill(c: Canvas, pal, label, x, y, size=26, h=50):
    f = fnt("Inter-SemiBold.ttf", size)
    s = label.upper()
    w = f.getlength(s) + 44
    c.d.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=rgb(pal["accent2"]))
    tb = f.getbbox(s)
    c.d.text((x + 22, y + (h - (tb[3] + tb[1])) / 2), s, font=f, fill=rgb(pal["on_accent"]))
    c.add_box("pill", [x, y, x + w, y + h])
    return x + w


def cover_crop(im: Image.Image, tw: int, th: int) -> Image.Image:
    iw, ih = im.size
    scale = max(tw / iw, th / ih)
    nw, nh = max(tw, round(iw * scale)), max(th, round(ih * scale))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left, top = (nw - tw) // 2, (nh - th) // 2
    return im.crop((left, top, left + tw, top + th))


def draw_frame(c: Canvas, pal, box, post, credit_size=22):
    x0, y0, x1, y1 = box
    c.d.rounded_rectangle(box, radius=20, fill=rgb(pal["surface2"]))
    c.d.rectangle([x0, y0 + 8, x0 + 16, y1 - 8], fill=rgb(pal["accent3"]))
    inner = [x0 + 16, y0 + 8, x1 - 8, y1 - 8]
    c.add_box("frame", box, critical=False)
    iw, ih = inner[2] - inner[0], inner[3] - inner[1]
    if post["kind"] == "photo":
        ph = post["photo"]
        with Image.open(ph["path"]) as src:
            im = ImageOps.exif_transpose(src).convert("RGB")
            im = cover_crop(im, iw, ih)
        mask = Image.new("L", (iw, ih), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, iw - 1, ih - 1], radius=14, fill=255)
        c.img.paste(im, (inner[0], inner[1]), mask)
        c.d = ImageDraw.Draw(c.img)
        label = f"Foto: {ph['author']} / {ph['license']}"
        f = fnt("Inter-Medium.ttf", credit_size)
        tw = f.getlength(label)
        if tw + 28 > iw - 24:
            raise PostError(f"crédito da foto não cabe na arte: '{label}'. Encurte photo.author")
        px1, py1 = inner[2] - 12, inner[3] - 12
        px0, py0 = px1 - tw - 28, py1 - credit_size - 18
        c.d.rounded_rectangle([px0, py0, px1, py1], radius=8, fill=rgb(pal["text"]))
        c.text((px0 + 14, py0 + 7), label, f, rgb(pal["on_accent"]), "photo_credit")
    else:
        c.d.rounded_rectangle(inner, radius=14, fill=rgb(pal["surface"]))
        panel = [inner[0] + 24, inner[1] + 24, inner[2] - 24, inner[3] - 24]
        c.d.rounded_rectangle(panel, radius=18, fill=rgb(pal["accent3"]))
        comp = post["competition"].upper()
        fc = fnt("Inter-SemiBold.ttf", 28)
        pw, ph_ = panel[2] - panel[0], panel[3] - panel[1]
        fit = fit_text(post["key"], "Outfit-Bold.ttf", pw - 64, 150, 72, 1, step=4)
        if fit is None:
            raise PostError(f"key '{post['key']}' não cabe no destaque nem a 72 px; encurte")
        fk, _, ks = fit
        kb = fk.getbbox(post["key"])
        cb = fc.getbbox(comp)
        gap = 40
        stack = (cb[3] - cb[1]) + gap + (kb[3] - kb[1])
        top = panel[1] + (ph_ - stack) / 2
        cw = fc.getlength(comp)
        c.text(((panel[0] + panel[2] - cw) / 2, top - cb[1]), comp, fc, rgb(pal["on_accent"]), "key_competition", critical=False)
        kw = fk.getlength(post["key"])
        c.text(((panel[0] + panel[2] - kw) / 2, top + (cb[3] - cb[1]) + gap - kb[1]), post["key"], fk, rgb(pal["on_accent"]), "key")
    return inner


def draw_lines(c: Canvas, x, y, lines, font, size, lh, fill, name):
    for i, line in enumerate(lines):
        c.text((x, y + i * lh), line, font, fill, f"{name}[{i}]")
    return y + len(lines) * lh


def draw_dots(c: Canvas, pal, n, active, W, y):
    span = (n - 1) * 30
    start = W // 2 - span // 2
    for i in range(n):
        x = start + i * 30
        c.d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=rgb(pal["accent"] if i == active else pal["line"]))
    c.add_box("dots", [start - 7, y - 7, start + span + 7, y + 7], critical=False)


# Layout do feed 4:5: todo conteúdo crítico entre y=SQUARE_CUT+SAFE_MARGIN e FEED_H-SQUARE_CUT-SAFE_MARGIN
FEED = {"wordmark_y": 168, "row_h": 46, "pill_y": 222, "frame": [MARGIN_X, 296, FEED_W - MARGIN_X, 790],
        "headline_y": 824, "head_max": 68, "head_min": 46, "head_lines": 3, "meta_gap": 22, "dots_y": 1272}


def meta_text(post, seg):
    return f"Fonte: {post['source_label']}  ·  {seg['signature']}"


def render_feed_cover(post, seg, pal, n_slides):
    c = Canvas(FEED_W, FEED_H, pal)
    draw_wordmark(c, seg, pal, FEED["wordmark_y"], 30)
    if post["agora"]:
        draw_agora(c, pal, FEED_W - MARGIN_X, FEED["wordmark_y"] - 8)
    draw_pill(c, pal, post["competition"], MARGIN_X, FEED["pill_y"])
    draw_frame(c, pal, FEED["frame"], post)
    fit = fit_text(post["title"], "Outfit-Bold.ttf", FEED_W - 2 * MARGIN_X, FEED["head_max"], FEED["head_min"], FEED["head_lines"])
    if fit is None:
        raise PostError(f"title não cabe em {FEED['head_lines']} linhas nem a {FEED['head_min']} px: encurte a manchete")
    ft, lines, size = fit
    lh = int(size * 1.16)
    y = draw_lines(c, MARGIN_X, FEED["headline_y"], lines, ft, size, lh, rgb(pal["text"]), "headline")
    fm = fnt("Inter-Regular.ttf", 28)
    meta = meta_text(post, seg)
    if fm.getlength(meta) > FEED_W - 2 * MARGIN_X:
        raise PostError(f"linha 'Fonte' longa demais para a arte: '{meta}'. Reduza source")
    c.text((MARGIN_X, y + FEED["meta_gap"]), meta, fm, rgb(pal["muted"]), "meta_fonte")
    if n_slides > 1:
        draw_dots(c, pal, min(n_slides, 10), 0, FEED_W, FEED["dots_y"])
    return c, {"headline_size": size, "headline_lines": len(lines)}


def render_feed_slide(post, seg, pal, text, idx, n_slides):
    c = Canvas(FEED_W, FEED_H, pal)
    draw_wordmark(c, seg, pal, FEED["wordmark_y"], 30)
    draw_pill(c, pal, post["competition"], MARGIN_X, FEED["pill_y"])
    fc = fnt("Inter-SemiBold.ttf", 26)
    cnt = f"{idx + 1}/{n_slides}"
    c.text((FEED_W - MARGIN_X - fc.getlength(cnt), FEED["pill_y"] + 10), cnt, fc, rgb(pal["muted"]), "counter", critical=False)
    top, bottom = 320, 1080
    x_text = MARGIN_X + 40
    fit = fit_text(text, "Outfit-SemiBold.ttf", FEED_W - MARGIN_X - x_text, 56, 34, 12)
    if fit is None:
        raise PostError(f"slides[{idx-1}].text não cabe no slide; encurte")
    f, lines, size = fit
    lh = int(size * 1.3)
    while len(lines) * lh > bottom - top:
        size -= 2
        if size < 34:
            raise PostError(f"slides[{idx-1}].text não cabe no slide; encurte")
        f = fnt("Outfit-SemiBold.ttf", size)
        lines = wrap(text, f, FEED_W - MARGIN_X - x_text)
        lh = int(size * 1.3)
    block_h = len(lines) * lh
    y0 = top + (bottom - top - block_h) // 2
    c.d.rounded_rectangle([MARGIN_X, y0 + 6, MARGIN_X + 12, y0 + block_h - 6], radius=4, fill=rgb(pal["accent3"]))
    draw_lines(c, x_text, y0, lines, f, size, lh, rgb(pal["text"]), "slide_text")
    fm = fnt("Inter-Regular.ttf", 28)
    c.text((MARGIN_X, 1120), meta_text(post, seg), fm, rgb(pal["muted"]), "meta_fonte")
    draw_dots(c, pal, min(n_slides, 10), idx, FEED_W, FEED["dots_y"])
    return c


def render_stories(post, seg, pal):
    c = Canvas(STORY_W, STORY_H, pal)
    y = STORY_SAFE_TOP + 20
    draw_wordmark(c, seg, pal, y, 32)
    px = draw_pill(c, pal, post["competition"], MARGIN_X, y + 64)
    if post["agora"]:
        draw_agora(c, pal, px + 16 + fnt("Inter-SemiBold.ttf", 26).getlength("AGORA") + 40, y + 64, size=26)
    fit = fit_text(post["title"], "Outfit-Bold.ttf", STORY_W - 2 * MARGIN_X, 76, 50, 4)
    if fit is None:
        raise PostError("title não cabe nos Stories em 4 linhas")
    ft, lines, size = fit
    lh = int(size * 1.15)
    yy = draw_lines(c, MARGIN_X, y + 150, lines, ft, size, lh, rgb(pal["text"]), "headline")
    if post["dek"]:
        fs = fnt("Inter-Regular.ttf", 36)
        dl = wrap(post["dek"], fs, STORY_W - 2 * MARGIN_X)
        if len(dl) > 3:
            raise PostError("dek não cabe em 3 linhas nos Stories; encurte")
        yy = draw_lines(c, MARGIN_X, yy + 14, dl, fs, 36, 48, rgb(pal["muted"]), "dek")
    frame_top = yy + 44
    if 1530 - frame_top < 420:
        raise PostError("title+dek longos demais para os Stories; encurte o dek")
    draw_frame(c, pal, [MARGIN_X, frame_top, STORY_W - MARGIN_X, 1530], post)
    fm = fnt("Inter-Regular.ttf", 30)
    c.text((MARGIN_X, 1566), f"Fonte: {post['source_label']}", fm, rgb(pal["muted"]), "meta_fonte")
    c.text((MARGIN_X, 1612), seg["handle"], fm, rgb(pal["accent2"]), "handle")
    return c


# ---------------------------------------------------------------- checagens de layout
def overlaps(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def layout_check(c: Canvas, kind: str):
    """Retorna dict com resultado; kind 'feed' (testa corte central 1:1) ou 'stories'."""
    W, H = c.img.size
    problems = []
    crit = [b for b in c.boxes if b["critical"]]
    for b in c.boxes:
        x0, y0, x1, y1 = b["box"]
        if x0 < 40 or x1 > W - 40 or y0 < 0 or y1 > H:
            problems.append(f"{b['name']} sai da área útil {b['box']}")
    texts = [b for b in crit if b["name"] not in ("pill", "agora_badge")]
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if overlaps(texts[i]["box"], texts[j]["box"]) and not (texts[i]["name"] in ("key",) or texts[j]["name"] in ("key",)):
                problems.append(f"sobreposição: {texts[i]['name']} x {texts[j]['name']}")
    if kind == "feed":
        lo, hi = SQUARE_CUT + SAFE_MARGIN, H - SQUARE_CUT - SAFE_MARGIN
        lost = [b["name"] for b in crit if b["box"][1] < lo or b["box"][3] > hi]
        res = {"square_crop_window": [0, SQUARE_CUT, W, H - SQUARE_CUT], "critical_lost_on_center_square": lost,
               "survives_center_square": not lost}
        if lost:
            problems.append(f"no corte central 1:1 perderia: {lost}")
    else:
        lost = [b["name"] for b in crit if b["box"][1] < STORY_SAFE_TOP or b["box"][3] > STORY_SAFE_BOTTOM]
        res = {"ui_safe_zone": [0, STORY_SAFE_TOP, W, STORY_SAFE_BOTTOM], "critical_under_ui": lost}
        if lost:
            problems.append(f"Stories: sob a UI do Instagram: {lost}")
    res["problems"] = problems
    res["ok"] = not problems
    return res


# ---------------------------------------------------------------- legenda
def build_caption(post, seg, fam):
    parts = [post["caption_body"], ""]
    parts.append(f"Fonte: {post['source_label']}")
    if post["kind"] == "photo":
        ph = post["photo"]
        extra = ", adaptada" if ph["adapted"] else ""
        parts.append(f"Foto: {ph['author']} ({ph['origin_label']}, {ph['license']}{extra})")
    parts.append(seg["signature"])
    parts.append(" ".join(seg["hashtags"]))
    cap = "\n".join(parts) + "\n"
    if len(cap) > fam["caption"]["instagram_max_chars"]:
        raise PostError(f"legenda final com {len(cap)} caracteres (> {fam['caption']['instagram_max_chars']})")
    return cap


# ---------------------------------------------------------------- dedupe
def read_published(path: Path):
    rows = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def canonical_source(name: str, seg) -> str:
    """'ge' / 'GE' / 'globo esporte' -> 'ge'. Desconhecida -> nome normalizado (minúsculas, sem acento)."""
    n = norm_title(name or "")
    for canon, ent in seg["known_sources"].items():
        if n == norm_title(canon) or any(n == norm_title(a) for a in ent.get("aliases", [])):
            return canon
    return n


def source_from_url(url: str, seg) -> str:
    h = host_of(url or "")
    best, blen = "", -1
    for canon, ent in seg["known_sources"].items():
        for d in ent["domains"]:
            if domain_match(h, [d]) and len(d) > blen:
                best, blen = canon, len(d)
    return best


def is_official_source(name: str, url: str, seg) -> bool:
    ent = seg["known_sources"].get(canonical_source(name, seg))
    if ent and ent.get("official"):
        return True
    return bool(url) and domain_match(host_of(url), seg.get("official_source_domains", []))


def row_source_key(r: dict, seg) -> str:
    src = r.get("source_key") or r.get("source") or (r.get("sources") or [None])[0]
    if isinstance(src, list):
        src = src[0] if src else None
    if src:
        return canonical_source(re.split(r"\s+/\s+", str(src))[0], seg)
    return source_from_url(r.get("source_url") or "", seg) or "?"


def recent_sources(seg, fam):
    """Últimos (janela-1) posts publicados (ordem do arquivo) e o que fica bloqueado para o próximo."""
    rot = fam["source_rotation"]
    log = KIT / seg["state"]["published_log"]
    rows = [r for r in read_published(log) if r.get("segment", seg["segment_id"]) == seg["segment_id"]]
    lastn = rows[-rot["window_posts"]:]
    prev = rows[-(rot["window_posts"] - 1):] if rot["window_posts"] > 1 else []
    keys = [row_source_key(r, seg) for r in prev]
    blocked = {}
    for k in set(keys):
        c = keys.count(k)
        if c + 1 > rot["max_same_source_in_window"]:
            blocked[k] = f"já tem {c} nos últimos {len(prev)} posts (máx. {rot['max_same_source_in_window']} em {rot['window_posts']} contando o novo)"
    if rot["no_consecutive_same_source"] and keys:
        blocked.setdefault(keys[-1], "foi a fonte do post anterior (não pode repetir em seguida)")
        if keys[-1] in blocked and "anterior" not in blocked[keys[-1]]:
            blocked[keys[-1]] += "; e foi a fonte do post anterior"
    suggest = [c for c, e in seg["known_sources"].items() if e.get("suggest", True) and c not in blocked]
    return {"log": str(log), "last": [{"published_at": r.get("published_at"), "source": row_source_key(r, seg),
                                        "title": r.get("title"), "post_url": r.get("post_url"),
                                        "exception": r.get("source_exception")} for r in lastn],
            "window_prev_keys": keys, "blocked": blocked, "allowed_suggestions": suggest}


def check_source_rotation(post, seg, fam):
    info = recent_sources(seg, fam)
    k = post["source_key"]
    res = {"source_key": k, "recent": info["window_prev_keys"], "violation": info["blocked"].get(k), "exception_used": False}
    if res["violation"]:
        exc = post["source_exception"]
        if exc:
            res["exception_used"] = True
            return res
        recent = ", ".join(f"{x['source']}" for x in info["last"]) or "(nenhum)"
        raise PostError(
            f"ROTAÇÃO DE FONTES: '{post['sources'][0]}' (= {k}) bloqueada agora: {res['violation']}.\n"
            f"Últimas fontes publicadas (antiga -> recente): {recent}.\n"
            f"Fontes liberadas para este post: {', '.join(info['allowed_suggestions'])}.\n"
            "Troque a pauta/fonte. Só use source_exception se for notícia urgente (breaking) ou exclusiva de fonte oficial (official_exclusive: CBF/clube/atleta) que só ela confirma.")
    return res


def check_duplicate(post, seg):
    log = KIT / seg["state"]["published_log"]
    t = norm_title(post["title"])
    for r in read_published(log):
        if r.get("source_url") and norm_url(r["source_url"]) == post["source_url_norm"]:
            raise DuplicateError(f"DUPLICADO: source_url já publicado em {r.get('post_url') or r.get('published_at') or '?'} ({log})")
        if r.get("title") and norm_title(r["title"]) == t:
            raise DuplicateError(f"DUPLICADO: mesma manchete já publicada em {r.get('post_url') or '?'} ({log})")
    return str(log)


# ---------------------------------------------------------------- main
def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def code_fingerprint():
    h = hashlib.sha256()
    h.update((KIT / "prisma_render.py").read_bytes())
    for f in FONT_FILES:
        h.update((FONTS / f).read_bytes())
    return h.hexdigest()[:16]


def render_all(segment: str, post_path: Path, out_dir: Path, now: dt.datetime):
    fam, seg = load_config(segment)
    try:
        raw = json.loads(post_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PostError(f"post não encontrado: {post_path}")
    except json.JSONDecodeError as e:
        raise PostError(f"post.json não é JSON válido: {e}")
    post = validate_post(raw, fam, seg, post_path.parent, now)
    log_path = None
    rotation = {"skipped": "sample"}
    if not post["sample"]:
        log_path = check_duplicate(post, seg)
        rotation = check_source_rotation(post, seg, fam)
    pal = palette(fam, seg)
    n = 1 + len(post["slides"])
    caption = build_caption(post, seg, fam)

    cover, cover_info = render_feed_cover(post, seg, pal, n)
    canvases = [("feed.png", cover, "feed")]
    for i, t in enumerate(post["slides"], start=1):
        canvases.append((f"feed-{i+1:02d}.png", render_feed_slide(post, seg, pal, t, i, n), "feed"))
    canvases.append(("stories.png", render_stories(post, seg, pal), "stories"))

    files, problems = {}, []
    blobs = {}
    for name, cv, kind in canvases:
        chk = layout_check(cv, kind)
        problems += [f"{name}: {p}" for p in chk["problems"]]
        b = png_bytes(cv.img)
        blobs[name] = b
        w, h = cv.img.size
        files[name] = {"sha256": sha256_bytes(b), "size": [w, h], "aspect": f"{w//_gcd(w,h)}:{h//_gcd(w,h)}",
                       "role": "stories" if kind == "stories" else ("feed_cover" if name == "feed.png" else "feed_slide"),
                       "boxes": cv.boxes, "check": chk}
    if problems:
        raise LayoutError("\n".join(problems))

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("feed-*.png"):
        old.unlink()
    for name, b in blobs.items():
        (out_dir / name).write_bytes(b)
    (out_dir / "caption.txt").write_text(caption, encoding="utf-8")
    photo = None
    if post["kind"] == "photo":
        ph = post["photo"]
        photo = {k: ph.get(k) for k in ("path", "author", "origin", "origin_label", "license", "adapted", "sha256", "size")}
        photo["credit_art"] = f"Foto: {ph['author']} / {ph['license']}"
        photo["credit_caption"] = f"Foto: {ph['author']} ({ph['origin_label']}, {ph['license']}{', adaptada' if ph['adapted'] else ''})"
    manifest = {
        "template_version": TEMPLATE_VERSION,
        "code_fingerprint": code_fingerprint(),
        "pillow": PIL.__version__,
        "freetype": features.version("freetype2"),
        "segment": seg["segment_id"],
        "handle": seg["handle"],
        "publishable": not post["sample"],
        "sample": post["sample"],
        "post_json": str(post_path.resolve()),
        "post_json_sha256": sha256_file(post_path),
        "title": post["title"],
        "kind": post["kind"],
        "competition": post["competition"],
        "key": post.get("key", ""),
        "sources": post["sources"],
        "source_key": post["source_key"],
        "source_official": post["source_official"],
        "source_exception": post["source_exception"],
        "source_rotation": rotation,
        "source_url": post["source_url"],
        "source_url_norm": post["source_url_norm"],
        "published_at": post["published_at"],
        "rendered_at": now.isoformat(),
        "agora_badge": post["agora"],
        "photo": photo,
        "slides": n,
        "upload_order": [k for k in files if k.startswith("feed")],
        "caption_file": "caption.txt",
        "caption_sha256": sha256_bytes(caption.encode("utf-8")),
        "published_log": log_path,
        "headline": cover_info,
        "files": files,
        "crop_decision": "4:5 com zona segura: todo conteúdo crítico do feed fica dentro do quadrado central 1080x1080 (y 151–1199). Publicar SEMPRE em 'Original' (4:5); se o Instagram cortar 1:1, a manchete, a assinatura e a Fonte sobrevivem.",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def main(argv=None):
    ap = argparse.ArgumentParser(description="Renderizador padronizado da família Prisma (sem flags de estilo).")
    ap.add_argument("--segment", required=True, help="id do segmento (segments/<id>.json), ex.: esportes")
    ap.add_argument("--post", help="post.json (ver post.schema.json)")
    ap.add_argument("--out-dir", help="pasta de saída (nomes de arquivo fixos)")
    ap.add_argument("--recent-sources", action="store_true", help="mostra as últimas fontes publicadas e quais estão bloqueadas para o próximo post")
    ap.add_argument("--now", default="", help="(testes) relógio de referência ISO 8601 para AGORA/idade; padrão: agora")
    a = ap.parse_args(argv)
    if a.recent_sources:
        try:
            fam, seg = load_config(a.segment)
        except PostError as e:
            print("ERRO: " + str(e), file=sys.stderr); return 2
        info = recent_sources(seg, fam)
        rot = fam["source_rotation"]
        print(f"Últimos {len(info['last'])} posts publicados ({info['log']}), antigo -> recente:")
        for x in info["last"]:
            ex = f"  [exceção: {x['exception']['type']}]" if x.get("exception") else ""
            print(f"  {x['published_at']}  {x['source']:<16} {(x['title'] or '')[:60]}{ex}")
        print(f"Regra: sem repetir a fonte do post anterior; máx. {rot['max_same_source_in_window']} da mesma fonte em {rot['window_posts']} posts (contando o novo).")
        if info["blocked"]:
            print("BLOQUEADAS para o próximo post:")
            for k, why in info["blocked"].items():
                print(f"  - {k}: {why}")
        else:
            print("BLOQUEADAS para o próximo post: nenhuma")
        print("Liberadas: " + ", ".join(info["allowed_suggestions"]))
        print(json.dumps({"blocked": sorted(info["blocked"]), "allowed": info["allowed_suggestions"]}, ensure_ascii=False))
        return 0
    if not a.post or not a.out_dir:
        ap.error("--post e --out-dir são obrigatórios (ou use --recent-sources)")
    now = parse_iso(a.now, "--now") if a.now else dt.datetime.now().astimezone()
    try:
        m = render_all(a.segment, Path(a.post), Path(a.out_dir), now)
    except PostError as e:
        print("ERRO DE VALIDAÇÃO (nada foi gerado):\n- " + str(e).replace("\n", "\n- "), file=sys.stderr)
        return 2
    except DuplicateError as e:
        print(str(e) + "\nNada foi gerado. Escolha outra pauta.", file=sys.stderr)
        return 3
    except LayoutError as e:
        print("FALHA DE LAYOUT (bug do kit, avise o Prisma Marketing):\n- " + str(e).replace("\n", "\n- "), file=sys.stderr)
        return 4
    print(json.dumps({"ok": True, "out_dir": str(Path(a.out_dir).resolve()), "publishable": m["publishable"],
                      "upload_order": m["upload_order"], "caption": "caption.txt", "agora": m["agora_badge"],
                      "survives_center_square": m["files"]["feed.png"]["check"]["survives_center_square"],
                      "feed_sha256": m["files"]["feed.png"]["sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

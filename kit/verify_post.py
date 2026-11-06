#!/usr/bin/env python3
"""Confere, depois de publicar, se o Instagram mostra a arte inteira (4:5) ou cortou.

Uso:
  python3 verify_post.py https://www.instagram.com/<handle>/p/<CODE>/ OUT_DIR/manifest.json [--record]
  python3 verify_post.py URL --image arte.png          # arte antiga sem manifest

Como funciona (melhor esforço, sem login):
  1. Baixa /p/<CODE>/embed/ com UA facebookexternalhit/1.1 e pega a imagem "cheia" do post
     (URL do CDN sem crop/escala) -> mede a proporção REAL armazenada pelo Instagram.
  2. Lê og:image da página do post (stp=c<x>.<y>.<w>.<h> é só o recorte da miniatura de
     link-preview; é reportado, mas NÃO decide nada).
  3. Compara a imagem armazenada com a arte local: inteira (4:5) x corte central (1:1).
  4. Se cortou, usa as caixas do manifest para dizer se manchete/Fonte/assinatura sobreviveram.

Códigos: 0 OK (4:5 inteiro) | 5 cortado mas TODO conteúdo crítico visível (avisar, não apagar)
         1 conteúdo crítico perdido (PARAR e avisar) | 3 imagem não confere com a arte (PARAR e avisar)
         2 não verificável (avisar; conferir a olho no navegador)
"""
from __future__ import annotations
import argparse, datetime as dt, html, io, json, re, subprocess, sys
from pathlib import Path
from PIL import Image, ImageChops, ImageOps

KIT = Path(__file__).resolve().parent
sys.path.insert(0, str(KIT))
UA = "facebookexternalhit/1.1"


def curl(url: str, timeout=25) -> bytes:
    r = subprocess.run(["curl", "-sL", "--max-time", str(timeout), "-A", UA, url], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl falhou ({r.returncode}) em {url}")
    return r.stdout


def shortcode(url: str) -> str:
    m = re.search(r"instagram\.com/(?:[^/]+/)?(?:p|reel)/([A-Za-z0-9_-]+)", url)
    if not m:
        raise ValueError(f"URL de post do Instagram inválida: {url}")
    return m.group(1)


def media_urls(page: str):
    urls = {html.unescape(u) for u in re.findall(r'https://scontent[^"\s\\]+', page)}
    urls |= {html.unescape(u.replace("\\/", "/")) for u in re.findall(r'https:\\/\\/scontent[^"\s]+', page)}
    return [u for u in urls if re.search(r"/t51\.[0-9]+-15/", u)]  # -15 = mídia do post; -19 = foto de perfil


def pick_full(urls):
    def score(u):
        stp = (re.search(r"stp=([^&]+)", u) or [None, ""])[1]
        if re.search(r"(^|_)c\d+\.\d+\.\d+\.\d+", stp):
            return -1
        m = re.search(r"_s(\d+)x(\d+)", stp)
        return 100000 if not m else int(m.group(1))
    best = sorted(urls, key=score, reverse=True)
    return best[0] if best and score(best[0]) >= 0 else None


def diff_score(a: Image.Image, b: Image.Image) -> float:
    a = a.convert("L").resize((256, 256), Image.Resampling.BILINEAR)
    b = b.convert("L").resize((256, 256), Image.Resampling.BILINEAR)
    h = ImageChops.difference(a, b).histogram()
    return sum(i * n for i, n in enumerate(h)) / (256 * 256)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("manifest", nargs="?", default="")
    ap.add_argument("--image", default="", help="arte local sem manifest (modo legado)")
    ap.add_argument("--record", action="store_true", help="grava no published.jsonl do segmento (dedupe)")
    ap.add_argument("--save-dir", default="", help="onde salvar a imagem baixada (padrão: pasta do manifest)")
    a = ap.parse_args()
    rep: dict = {"post_url": a.url, "checked_at": dt.datetime.now().astimezone().isoformat(timespec="seconds")}
    manifest = None
    if a.manifest:
        manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
        art = Path(a.manifest).parent / "feed.png"
    elif a.image:
        art = Path(a.image)
    else:
        print("informe manifest.json ou --image", file=sys.stderr); return 2
    local = Image.open(art).convert("RGB")
    rep["local_art"] = str(art)
    code = 2
    try:
        sc = shortcode(a.url)
        rep["shortcode"] = sc
        page = curl(f"https://www.instagram.com/p/{sc}/").decode("utf-8", "replace")
        og = re.search(r'property="og:image"\s+content="([^"]+)"', page)
        if og:
            ogu = html.unescape(og.group(1))
            stp = (re.search(r"stp=([^&]+)", ogu) or [None, ""])[1]
            c = re.search(r"(?:^|_)c(\d+)\.(\d+)\.(\d+)\.(\d+)", stp)
            rep["og_image_stp"] = stp
            rep["og_image_crop_hint"] = [int(x) for x in c.groups()] if c else None
            rep["og_image_note"] = "miniatura de link-preview; recorte próprio do Instagram, não decide o veredito"
        emb = curl(f"https://www.instagram.com/p/{sc}/embed/").decode("utf-8", "replace")
        full = pick_full(media_urls(emb))
        if not full:
            raise RuntimeError("embed sem URL de mídia do post (login wall, post apagado ou layout mudou)")
        blob = curl(full)
        stored = Image.open(io.BytesIO(blob))
        stored = ImageOps.exif_transpose(stored).convert("RGB")
        sw, sh = stored.size
        save_dir = Path(a.save_dir) if a.save_dir else art.parent
        save_dir.mkdir(parents=True, exist_ok=True)
        sp = save_dir / f"ig-stored-{sc}.jpg"
        sp.write_bytes(blob)
        rep.update({"stored_image": str(sp), "stored_size": [sw, sh], "stored_aspect_w_over_h": round(sw / sh, 4)})
        lw, lh = local.size
        s = min(lw, lh)
        sq = ((lw - s) // 2, (lh - s) // 2, (lw - s) // 2 + s, (lh - s) // 2 + s)
        cands = {"full_4x5": local, "center_square_1x1": local.crop(sq)}
        scores = {k: round(diff_score(stored, v), 2) for k, v in cands.items()}
        rep["match_scores_lower_is_better"] = scores
        best = min(scores, key=scores.get)
        aspect_ok = abs(sw / sh - lw / lh) < 0.02
        if scores[best] > 12:
            rep["verdict"] = "MISMATCH"
            rep["message"] = "A imagem publicada não confere com a arte local (arquivo errado, outro slide ou edição). PARAR e avisar."
            code = 3
        elif aspect_ok and best == "full_4x5":
            rep["verdict"] = "OK_FULL"
            rep["message"] = "Arte publicada inteira em 4:5 (assinatura, manchete e Fonte visíveis)."
            code = 0
        else:
            sys.path.insert(0, str(KIT))
            from check_crop import check
            cr = check(Path(a.manifest) if manifest else art)
            rep["crop_check"] = {k: cr.get(k) for k in ("method", "critical_lost", "critical_kept", "survives_center_square", "top_band", "bottom_band")}
            if cr["survives_center_square"]:
                rep["verdict"] = "CROPPED_1x1_CONTENT_OK"
                rep["message"] = "Instagram cortou para 1:1 (faltou escolher 'Original'), mas todo conteúdo crítico ficou visível. Não apagar; avisar e usar 'Original' no próximo."
                code = 5
            else:
                rep["verdict"] = "CROPPED_1x1_CONTENT_LOST"
                rep["message"] = "Instagram cortou para 1:1 e conteúdo crítico sumiu. PARAR a rotina e avisar Jonas + Prisma Marketing. Não apagar/republicar sem ok do Jonas."
                code = 1
    except Exception as e:  # noqa: BLE001
        rep["verdict"] = "UNVERIFIED"
        rep["message"] = f"Não deu para verificar automaticamente: {e}. Abrir o post no navegador e conferir a olho (manchete + Fonte)."
        code = 2
    rep["exit_code"] = code
    if a.record:
        if not manifest:
            rep["record"] = "ignorado: --record exige manifest"
        elif not manifest.get("publishable"):
            rep["record"] = "ignorado: manifest de amostra (publishable=false)"
        else:
            from prisma_render import load_config
            _, seg = load_config(manifest["segment"])
            log = KIT / seg["state"]["published_log"]
            log.parent.mkdir(parents=True, exist_ok=True)
            row = {"segment": manifest["segment"], "title": manifest["title"], "source_url": manifest["source_url"],
                   "source_url_norm": manifest["source_url_norm"], "post_url": a.url, "published_at": rep["checked_at"],
                   "verdict": rep["verdict"], "feed_sha256": manifest["files"]["feed.png"]["sha256"],
                   "template_version": manifest["template_version"], "photo": manifest.get("photo"),
                   "source": (manifest.get("sources") or [None])[0], "sources": manifest.get("sources"),
                   "source_key": manifest.get("source_key"), "source_exception": manifest.get("source_exception")}
            with log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            rep["record"] = str(log)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())

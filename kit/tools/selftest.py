#!/usr/bin/env python3
"""Autoteste do kit: determinismo (2 renders => mesmos bytes), validações negativas, crop check.
Uso: python3 tools/selftest.py   (sai != 0 se algo falhar)"""
import copy, hashlib, json, subprocess, sys, tempfile
from pathlib import Path
KIT = Path(__file__).resolve().parents[1]
INP = KIT / "samples" / "inputs"
NOW = "2026-11-05T22:40:00-03:00"
fails = 0


def run(post: dict | Path, out: Path, now=NOW):
    if isinstance(post, dict):
        p = out.parent / (out.name + ".json")
        p.write_text(json.dumps(post, ensure_ascii=False))
        # caminho da foto relativo => absolutiza
    else:
        p = post
    r = subprocess.run([sys.executable, str(KIT / "prisma_render.py"), "--segment", "esportes", "--post", str(p), "--out-dir", str(out), "--now", now],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def hashes(d: Path):
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(list(d.glob("feed*.png")) + [d / "stories.png"])} | {"caption.txt": hashlib.sha256((d / "caption.txt").read_bytes()).hexdigest()}


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails += 1


with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    for k in ("typo", "photo", "carousel"):
        c1, o1 = run(INP / f"vasco-{k}.json", td / f"{k}-a")
        c2, o2 = run(INP / f"vasco-{k}.json", td / f"{k}-b")
        ok(c1 == 0 and c2 == 0, f"{k}: render ok")
        if c1 == 0 and c2 == 0:
            h1, h2 = hashes(td / f"{k}-a"), hashes(td / f"{k}-b")
            ok(h1 == h2, f"{k}: determinístico ({len(h1)} arquivos idênticos byte a byte)")
            if (KIT / "samples" / k).exists():
                ok(h1 == hashes(KIT / "samples" / k), f"{k}: igual às amostras salvas em samples/{k}")
            r = subprocess.run([sys.executable, str(KIT / "check_crop.py"), str(td / f"{k}-a")], capture_output=True)
            ok(r.returncode == 0, f"{k}: sobrevive ao corte central 1:1")

    base = json.loads((INP / "vasco-typo.json").read_text())
    photo = json.loads((INP / "vasco-photo.json").read_text())
    photo["photo"]["path"] = str(INP / photo["photo"]["path"])
    neg = []

    def case(name, mutate, src=base, expect=2):
        p = copy.deepcopy(src)
        mutate(p)
        neg.append((name, p, expect))

    case("sem source", lambda p: p.pop("source"))
    case("sem source_url", lambda p: p.pop("source_url"))
    case("source_url de outro veículo", lambda p: p.update(source_url="https://www.uol.com.br/esporte/x.htm"))
    case("competition fora da lista", lambda p: p.update(competition="Champions League"))
    case("manchete longa demais (não cabe em 3 linhas)", lambda p: p.update(title="Vasco quebra tabu de dezenove anos, vira sobre o Athletico na Arena da Baixada e abre folga enorme para a zona de rebaixamento do Brasileirão"))
    case("manchete com <=140 caracteres mas que não cabe em 3 linhas a 46 px", lambda p: p.update(title="Vasco quebra tabu histórico, vira sobre o Athletico na Baixada e se distancia definitivamente da zona de rebaixamento no Brasileirão"))
    case("clickbait/termo proibido", lambda p: p.update(title="URGENTE: Vasco quebra tabu de 19 anos na Baixada"))
    case("CAIXA ALTA", lambda p: p.update(title="VASCO QUEBRA TABU DE 19 ANOS NA BAIXADA"))
    case("legenda com hashtag", lambda p: p.update(caption_body=p["caption_body"] + " #Vasco"))
    case("legenda com Fonte: escrita pelo bot", lambda p: p.update(caption_body=p["caption_body"] + "\n\nFonte: ge"))
    case("notícia velha (>12h)", lambda p: p.update(published_at="2026-11-04T08:00:00-03:00"))
    case("data sem fuso", lambda p: p.update(published_at="2026-11-05T22:15:00"))
    case("typo sem key", lambda p: p.pop("key"))
    case("campo de estilo livre", lambda p: p.update(color="#000000"))
    case("foto sem licença", lambda p: p["photo"].pop("license"), src=photo)
    case("foto sem autor", lambda p: p["photo"].pop("author"), src=photo)
    case("licença NC", lambda p: p["photo"].update(license="CC BY-NC 4.0"), src=photo)
    case("foto de portal (ge)", lambda p: p["photo"].update(origin="https://ge.globo.com/foto/abc.jpg"), src=photo)
    case("foto 'Reprodução'", lambda p: p["photo"].update(author="Reprodução/TV Globo"), src=photo)
    case("Unsplash sem generic=true", lambda p: p["photo"].update(origin="https://unsplash.com/photos/abc", license="Unsplash License"), src=photo)
    case("foto inexistente", lambda p: p["photo"].update(path="/nao/existe.jpg"), src=photo)
    case("duplicado (já publicado)", lambda p: p.pop("sample"), expect=3)
    for i, (name, p, exp) in enumerate(neg):
        code, out = run(p, td / f"neg{i}")
        first = next((l for l in out.splitlines() if l.startswith("- ") or "DUPLICADO" in l), out.strip()[:120])
        ok(code == exp and not (td / f"neg{i}" / "feed.png").exists(), f"recusa: {name} (exit {code}) -> {first}")

# ---------------------------------------------------------------- rotação de fontes (kit copiado + histórico controlado)
import shutil
URLS = {"ge": "https://ge.globo.com/futebol/x{n}.ghtml", "ESPN Brasil": "https://www.espn.com.br/futebol/x{n}",
        "CNN Esportes": "https://www.cnnbrasil.com.br/esportes/x{n}/", "Lance!": "https://www.lance.com.br/x{n}.html",
        "CBF": "https://www.cbf.com.br/a-cbf/noticias/x{n}", "Folha Esporte": "https://www1.folha.uol.com.br/esporte/x{n}.shtml"}
with tempfile.TemporaryDirectory() as td2:
    kit2 = Path(td2) / "kit"
    shutil.copytree(KIT, kit2, ignore=shutil.ignore_patterns("samples", "__pycache__", "*.bak-*"))
    log2 = kit2 / "state" / "esportes" / "published.jsonl"
    counter = [0]

    def rot_case(name, history, source, url_key, expect, exception=None, check=None):
        counter[0] += 1
        n = counter[0]
        log2.write_text("".join(json.dumps({"segment": "esportes", "title": f"Histórico {n}-{i} de teste da rotação", "source": h,
                                            "source_url": URLS.get(h, "https://ge.globo.com/x").format(n=f"h{n}-{i}"),
                                            "published_at": "2026-11-05T22:00:00-03:00"}, ensure_ascii=False) + "\n" for i, h in enumerate(history)))
        p = copy.deepcopy(base)
        p.pop("sample")
        p["title"] = f"Teste de rotação de fontes número {n} no Brasileirão"
        p["source"] = source
        p["source_url"] = URLS[url_key].format(n=f"new{n}")
        if exception:
            p["source_exception"] = exception
        pj = Path(td2) / f"rot{n}.json"
        pj.write_text(json.dumps(p, ensure_ascii=False))
        out = Path(td2) / f"rot{n}"
        r = subprocess.run([sys.executable, str(kit2 / "prisma_render.py"), "--segment", "esportes", "--post", str(pj), "--out-dir", str(out), "--now", NOW],
                           capture_output=True, text=True)
        extra = True
        if check and r.returncode == 0:
            extra = check(json.loads((out / "manifest.json").read_text()))
        if check and r.returncode != 0:
            extra = check(r.stderr)
        first = (r.stderr.strip().splitlines() or [r.stdout.strip()[:80]])
        first = next((l for l in first if "ROTA" in l or l.startswith("- ")), first[0])
        ok(r.returncode == expect and extra, f"rotação: {name} (exit {r.returncode}) -> {first[:150]}")

    rot_case("repetir fonte do post anterior ('GE' = ge)", ["ESPN Brasil", "CNN Esportes", "Lance!", "ge"], "GE", "ge", 2)
    rot_case("3ª da mesma fonte em 5 ('globo esporte' = ge)", ["ge", "ESPN Brasil", "ge", "CNN Esportes"], "globo esporte", "ge", 2)
    rot_case("mensagem lista fontes recentes e sugere outras", ["ge", "ESPN Brasil", "ge", "CNN Esportes"], "ge", "ge", 2,
             check=lambda err: "Últimas fontes publicadas" in err and "ESPN Brasil, ge, CNN Esportes" in err and "Lance!" in err and "Fontes liberadas" in err)
    rot_case("ge liberado (1 nos últimos 4, não consecutivo)", ["ge", "ESPN Brasil", "CNN Esportes", "Lance!"], "ge", "ge", 0)
    rot_case("alias 'CNN Brasil' = CNN Esportes do post anterior", ["ge", "ESPN Brasil", "Lance!", "CNN Esportes"], "CNN Brasil", "CNN Esportes", 2)
    rot_case("multi-fonte: vale a 1ª (Folha), CNN só secundária", ["ge", "ESPN Brasil", "Lance!", "CNN Esportes"], ["Folha", "CNN Brasil"], "Folha Esporte", 0)
    rot_case("exceção breaking libera e fica no manifest", ["ge", "ESPN Brasil", "ge", "CNN Esportes"], "ge", "ge", 0,
             exception={"type": "breaking", "reason": "Demissão do técnico confirmada agora, só o ge publicou até o momento"},
             check=lambda m: m["source_exception"]["type"] == "breaking" and m["source_rotation"]["exception_used"] is True)
    rot_case("official_exclusive recusada para fonte não oficial (ge)", ["ESPN Brasil", "CNN Esportes", "Lance!", "ge"], "ge", "ge", 2,
             exception={"type": "official_exclusive", "reason": "Só o ge confirmou a informação até agora"})
    rot_case("official_exclusive aceita para CBF", ["ESPN Brasil", "CBF", "Lance!", "CBF"], "CBF", "CBF", 0,
             exception={"type": "official_exclusive", "reason": "Convocação oficial divulgada apenas no site da CBF"})
    rot_case("exceção com motivo curto", ["ESPN Brasil", "CNN Esportes", "Lance!", "ge"], "ge", "ge", 2,
             exception={"type": "breaking", "reason": "urgente"})
    rot_case("tipo de exceção inválido", ["ESPN Brasil", "CNN Esportes", "Lance!", "ge"], "ge", "ge", 2,
             exception={"type": "porque_sim", "reason": "motivo qualquer bem comprido aqui"})
    log2.write_text("".join(json.dumps({"segment": "esportes", "title": f"h{i}", "source": s}) + "\n" for i, s in enumerate(["CNN Brasil", "ge", "ge", "ge", "ge"])))
    r = subprocess.run([sys.executable, str(kit2 / "prisma_render.py"), "--segment", "esportes", "--recent-sources"], capture_output=True, text=True)
    last = json.loads(r.stdout.strip().splitlines()[-1])
    ok(r.returncode == 0 and last["blocked"] == ["ge"] and "CNN Esportes" in last["allowed"], f"--recent-sources: bloqueadas={last['blocked']}")

print("\nRESULTADO:", "TUDO OK" if fails == 0 else f"{fails} FALHA(S)")
sys.exit(1 if fails else 0)

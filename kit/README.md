> Espelho canônico no GitHub do gerador que roda no box em `/workspace/prisma-kit`. No Mac/clone: use os caminhos relativos a `kit/`. O log `state/*/published.jsonl` fica só no box.

# prisma-kit — renderização padronizada da família Prisma

Gerador único e determinístico de posts para as páginas Prisma (hoje: Prisma Esportes @prismaesportesbr;
depois: Política, Saúde… via `segments/<id>.json`). O bot só fornece **conteúdo** (post.json); estilo,
legenda final, crédito e checagens são do kit.

## Uso
```bash
cd /workspace/prisma-kit
python3 prisma_render.py --segment esportes --post post.json --out-dir out/<stamp>   # arte + caption.txt + manifest.json
python3 check_crop.py out/<stamp> --preview out/<stamp>/crop.png                      # simula corte 1:1 (já roda dentro do render)
python3 verify_post.py https://www.instagram.com/prismaesportesbr/p/<CODE>/ out/<stamp>/manifest.json --record   # depois de publicar
python3 prisma_render.py --segment esportes --recent-sources                           # últimas 5 fontes + bloqueadas p/ o próximo
python3 tools/selftest.py                                                             # determinismo + recusas + rotação de fontes
```
Exemplos de post.json: `samples/inputs/`. Campos: `post.schema.json`. Publicação: `PUBLISH.md`.

## Arquivos
- `family.json`: paleta base, regras de notícia (AGORA ≤ 2 h, máx. 12 h), política de foto, termos proibidos (todas as páginas).
- `segments/esportes.json`: wordmark, assinatura, handle, 3 acentos, hashtags, pills permitidas, fontes conhecidas e o log de publicados.
- `segments/_template.json`: modelo comentado para novo segmento (o render recusa enquanto houver "TROCAR").
- `prisma_render.py`: valida, renderiza, checa layout e corte, e escreve as saídas.
- `check_crop.py`: simulação do corte central 1:1 (por caixas do manifest ou varredura de pixels em PNG antigo).
- `verify_post.py`: verificação pós-publicação pela imagem real armazenada pelo Instagram (via /embed/).
- `state/<segmento>/published.jsonl`: dedupe (importado do histórico do Prisma Esportes).
- `fonts/`: Outfit + Inter, cópia fixa (o hash entra no `code_fingerprint`).

## Rotação de fontes (regra editorial oficial)
Parâmetros em `family.json` → `source_rotation`: não repetir a fonte do post anterior; máx. 2 da mesma fonte em 5 posts (contando o novo).
Vale para posts publicáveis e lê `state/<segmento>/published.jsonl` (gravado por `verify_post.py --record`).
A fonte é a 1ª de `source`, normalizada pelos aliases de `known_sources` (ge/GE/globo esporte = ge; CNN Brasil = CNN Esportes).
Exceção `source_exception` {type: breaking|official_exclusive, reason ≥15}. `official_exclusive` só vale com fonte oficial (`official: true` ou domínio em `official_source_domains`).
A exceção fica no manifest e no published.jsonl.

## Saídas (nomes fixos em --out-dir)
`feed.png` 1080×1350 (capa) · `feed-02.png…` slides do carrossel · `stories.png` 1080×1920 · `caption.txt` · `manifest.json`.

## Decisão de corte
A arte 4:5 continua sendo o formato (melhor área no feed). O layout tem uma **zona segura**: todo conteúdo crítico
(assinatura, pill, AGORA, manchete, Fonte, crédito da foto, placar) fica dentro do quadrado central 1080×1080
(y 151–1199). As faixas de 135 px em cima e embaixo só têm respiro e os pontinhos do carrossel. Assim:
- publicado em "Original": aparece tudo, com respiro;
- se o desktop cortar 1:1 por engano: manchete, assinatura e Fonte continuam visíveis.

O render **falha** (exit 4) se algum elemento crítico sair da zona. Não exportamos um 1:1 separado para não haver dois
arquivos "certos" e o bot escolher o errado.

Stories: conteúdo entre y 250 e 1670 (fora da área da UI do Instagram).

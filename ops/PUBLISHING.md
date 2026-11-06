# Publicação

## Alvo (Esportes) — regra oficial

- Feed + Stories a cada **1 hora**
- Pausa **01:00–07:00** America/Sao_Paulo
- Canal: navegador do box do bot

O alvo acima permanece a regra oficial até Jonas mudar. O estado operacional abaixo registra pausas e limites temporários.

## Estado operacional (5 nov 2026, America/Sao_Paulo)

Fonte: consenso Marketing + Esportes / decisões Jonas; gerador `kit/` (`prisma-family-v1`).

- **Gerador oficial:** `kit/prisma_render.py` (família Prisma). Legado: `arms/esportes/publish/render_post.py`.
- **Checklist fixo:** `kit/PUBLISH.md` (proporção Original, caption do kit, `verify_post.py --record`).
- **Cadência automática:** alvo 1h com pausa 01h–07h; liberação/pausa fina no chat do Prisma Esportes (teste 10 min + limpeza/template único já ocorreram; posts noturnos de 5 nov saíram via kit com veredito `OK_FULL`).
- **Canal web desktop:** feed only. Stories bloqueado no composer desktop (`blocked_desktop_no_composer`).
- **Fila em lote:** DESCARTADA (notícia envelhece). Cada rodada busca + publica na hora.
- **Dedupe:** por URL da fonte + manchete (`kit/state/<segmento>/published.jsonl` no box).
- **Rotação de fontes:** regra dura oficial — sem fonte consecutiva igual; ≤2 da mesma nos últimos 5 posts de feed (`kit/family.json` → `source_rotation`; ver `arms/esportes/contrato-fontes.md`).
- **Dispatch:** 1 navegador curto por post.
- **Arte:** 4:5. No composer desktop: proporção **Original** antes de Avançar. Conferir o post inteiro após Share. Não apagar post cortado sem ok do Jonas.
- **Template:** `prisma-family-v1` — ver `ops/TEMPLATE.md`.
- **Foto / frame:** ver `arms/esportes/politica-foto-frame.md`.

## Checklist curto (quando publicar)

1. `python3 kit/prisma_render.py --segment esportes --recent-sources` → escolher fonte liberada.
2. Renderizar com o kit; conferir `publishable: true` e zona segura no manifest.
3. Upload feed 4:5 com proporção **Original** no composer; colar `caption.txt` sem editar.
4. `verify_post.py <URL> <manifest> --record`. Se `CROPPED_1x1_CONTENT_LOST` ou `MISMATCH`: parar e avisar Jonas + Marketing.

# Contrato editorial — diversificação de fontes (Prisma Esportes)

Oficial a partir de 2026-11-05 (Jonas via Prisma marca-mãe). Travado no prisma-kit (`family.json` → `source_rotation`).

Antes de escolher a pauta:
`python3 /workspace/prisma-kit/prisma_render.py --segment esportes --recent-sources`

Regras:
1. Sem repetir a fonte do post anterior.
2. No máximo 2 da mesma fonte nas últimas 5 (contando o novo).
3. Fonte = 1ª de `source` (aliases em known_sources).
4. Exceção só com `source_exception` {type: breaking|official_exclusive, reason ≥15}.
5. `Fonte:` na legenda obrigatório (kit gera).
6. Exit 2 ROTAÇÃO DE FONTES → troque fonte/pauta; não edite o kit.

Ver PUBLISH.md passo 0 do prisma-kit.

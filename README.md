# Prisma

Repositório canônico do ecossistema **Prisma** — marca-mãe de notícias no Instagram (Brasil).

Fonte de verdade para identidade, tom, regras editoriais, naming, visual e operação dos braços (bots e contas). Escalável: cada novo braço (Política, Saúde…) entra como pasta sob `arms/` sem reescrever a marca-mãe.

## Mapa

| Pasta | Conteúdo |
| --- | --- |
| `brand/` | Contexto de marca-mãe (tom, modelo editorial, regras comuns) |
| `visual/` | Sistema de imagem (paleta, família de logo, tokens) |
| `arms/esportes/` | Braço Prisma Esportes (conta, bio, fontes, filtros, cadência) |
| `arms/marketing/` | Prisma Marketing (presença IG, assets, templates) |
| `bots/` | Papéis dos bots do time e handoffs |
| `ops/` | Operação (publicação, pausas, checklists) |
| `kit/` | Gerador oficial da família (`prisma-family-v1`) + checklist de publish |

## Princípios

1. **Curadoria com ângulo Prisma** — grandes fontes → filtros → reescrita → crédito obrigatório na legenda; **diversificar entre publicações** (sem fonte consecutiva igual; ≤2/5).
2. **Marca-mãe governa** — braços executam editoria sem reinventar tom/visual.
3. **Proposta vs oficial** — tudo não aprovado fica marcado; não inventar handles/cores.

## Links vivos

- Conta Esportes: https://www.instagram.com/prismaesportesbr/
- Page marca: ver `brand/CONTEXT.md` (espelho da Page Cursor)
- Page visual: ver `visual/SYSTEM.md`

## Como contribuir

1. Mudanças de marca → `brand/` + checklist de pendências.
2. Novo braço → `arms/<slug>/` + entrada em `bots/` + cor de acento só se aprovada.
3. Assets binários → `visual/assets/` (não commitar segredos de conta).

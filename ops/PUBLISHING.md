# Publicação

## Alvo (Esportes) — regra oficial

- Feed + Stories a cada **1 hora**
- Pausa **01:00–07:00** America/Sao_Paulo
- Canal: navegador do box do bot

O alvo acima permanece a regra oficial até Jonas mudar. O estado operacional abaixo registra pausas e limites temporários.

## Estado operacional (5 nov 2026, America/Sao_Paulo)

Fonte: consenso Marketing + Esportes / decisões Jonas via chats (ver `arms/esportes/politica-foto-frame.md`).

- **Cadência automática:** PAUSADA até liberação direta do Jonas no chat do Prisma Esportes (pedido de teste 10 min + limpeza/template único antes de retomar).
- **Canal web desktop:** feed only. Stories bloqueado no composer desktop (`blocked_desktop_no_composer`).
- **Fila em lote:** DESCARTADA (notícia envelhece). Cada rodada busca + publica na hora.
- **Dedupe:** por URL da fonte (não repetir notícia; não reprocessar fontes já vistas).
- **Dispatch:** 1 navegador curto por post.
- **Arte:** 4:5. No composer desktop: proporção **Original** ou **4:5** antes de Avançar. Conferir o post inteiro após Share. Não apagar post cortado sem ok do Jonas.
- **Template:** `prisma-eletrico-unico-v1` — ver `ops/TEMPLATE.md`.
- **Foto / frame:** ver `arms/esportes/politica-foto-frame.md`.

## Checklist curto (quando a cadência estiver liberada)

1. Renderizar com o gerador oficial do braço.
2. Upload feed 4:5 com proporção correta no composer.
3. Legenda com fato → `Fonte:` → crédito de foto (se houver) → assinatura/hashtags (proposta).
4. Verificar o post publicado; se cortado com perda de conteúdo, pausar e avisar Jonas + Marketing.

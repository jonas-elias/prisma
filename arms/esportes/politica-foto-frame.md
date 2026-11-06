# Política de foto no frame + template (consenso Marketing + Esportes)

Atualizado 2026-11-05 22:18 (decisões Jonas via Prisma Marketing).

## Template oficial
prisma-eletrico-unico-v1 — em uso em `publish/render_post.py`.
Ajustes a–d já aplicados (sem FRAME; tipográfico; manchete; dots só em carrossel; AGORA ≤~2h).

Pendente Marketing: versão sem faixas coloridas de cima/baixo (Jonas não gostou). Até o Jonas aprovar o novo gerador, seguir com o `render_post.py` atual.

## Foto PERMITIDO (só com licença liberada + crédito)
- Wikimedia Commons CC0 / CC BY / CC BY-SA, conferida na página do arquivo
- Clube / CBF com licença explícita de reuso
- Unsplash / Pexels só imagem genérica (bola, gramado, arquibancada) — nunca como se fosse o jogo/jogador da notícia
- Arte tipográfica própria (padrão quando não houver foto segura)

## PROIBIDO
- Foto de matéria/portal (ge, ESPN, UOL, Lance! etc.), mesmo com crédito
- Print de TV/streaming ou rede social de terceiros
- Google Imagens sem licença verificada; marca d'água
- IA retratando jogador, técnico ou jogo real
- Escudos/logos de clubes ou competições
- Exposição negativa indevida de pessoa

## Crédito
Arte: `Foto: <Autor> / <Licença>` (faixa escura, canto inferior direito do frame).
Legenda: fato → Fonte → Foto → Prisma · Esportes → hashtags.
Log por post: URL da foto, autor, licença, data da checagem.

## Operação de publicação (Jonas 22:18)
- Fila em lote: DESCARTADA (notícia envelhece).
- Cada rodada: busca + publica na hora.
- Dedupe por URL da fonte (não repetir notícia; não reprocessar fontes já vistas).
- 1 dispatch curto de navegador por post.
- Feed only no web desktop (Stories bloqueado: blocked_desktop_no_composer).
- Cadência automática: PAUSADA até liberação direta do Jonas no chat do Prisma Esportes (ele pediu 10 min ao Marketing; confirmar antes de retomar).

## Upload Instagram (2026-11-05)
Arte 4:5. No composer desktop: proporção Original ou 4:5 antes de Avançar. Conferir post inteiro após Share. Não apagar post cortado sem ok Jonas.

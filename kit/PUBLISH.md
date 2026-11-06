# PUBLISH.md — checklist fixo de publicação (feed, Instagram desktop)

Vale para todo segmento Prisma. Siga na ordem e não pule passo. Stories não saem pelo desktop; não tente.

## 0. Antes do navegador (shell)
0. **Antes de escolher a pauta**, rode:
   `python3 kit/prisma_render.py --segment esportes --recent-sources`
   e escolha uma matéria de uma fonte **liberada**. A regra: não repetir a fonte do post anterior, e no máximo 2 posts da mesma fonte a cada 5 (contando o novo). A fonte que conta é a 1ª de `source`.
   Exceção (`source_exception`) só para notícia urgente (`breaking`) ou exclusiva de fonte oficial (`official_exclusive`: CBF/clube/atleta). Precisa de um motivo real de pelo menos 15 caracteres e fica registrada.
1. Renderize:
   `python3 kit/prisma_render.py --segment esportes --post post.json --out-dir OUT`
   - exit 2 = post inválido, inclusive "ROTAÇÃO DE FONTES" (leia o erro, troque a fonte ou a pauta, NÃO contorne);
   - exit 3 = duplicado, troque de pauta;
   - exit 4 = bug do kit, pare e avise o Prisma Marketing.
2. Abra `OUT/manifest.json` e confira:
   - `"publishable": true` (se for false é amostra e NÃO publica);
   - `files["feed.png"].check.survives_center_square: true`.
3. Use somente os arquivos de `OUT/` na ordem de `manifest.upload_order` (feed.png, feed-02.png…). Não edite PNG nem legenda.

## 1. Upload
4. Instagram → Criar → Post → selecione os arquivos de `upload_order` (carrossel: todos de uma vez, na ordem).
5. **Tela de corte, OBRIGATÓRIO antes de Avançar:** clique no ícone de proporção (canto inferior esquerdo da imagem) e escolha **Original**. A prévia tem que ficar vertical (4:5). Se ficou quadrada, NÃO avance.
   - Não arraste nem dê zoom na imagem.
   - Carrossel: a proporção escolhida vale para todos. Confira que o slide 1 está vertical.
6. Avançar → (sem filtro/ajuste) → Avançar.

## 2. Legenda
7. Cole o conteúdo de `OUT/caption.txt` **exatamente**, sem acrescentar, tirar ou reformatar nada (ele já traz Fonte, Foto, assinatura e hashtags).
8. Sem marcação de pessoas, local ou colaboração.
9. Compartilhar.

## 3. Verificação (obrigatória)
10. Pegue o link do post (`https://www.instagram.com/<handle>/p/<CODE>/`).
11. Rode:
    `python3 kit/verify_post.py <URL> OUT/manifest.json --record`

    | exit | veredito | o que fazer |
    |---|---|---|
    | 0 | OK_FULL | ok, segue a rotina |
    | 5 | CROPPED_1x1_CONTENT_OK | o Instagram cortou em 1:1, mas manchete, assinatura e Fonte aparecem. Não apague. Registre o aviso no relatório e reforce o passo 5 no próximo post |
    | 1 | CROPPED_1x1_CONTENT_LOST | **PARE a rotina** e avise o Jonas e o Prisma Marketing. Não apague nem republique sem ok do Jonas |
    | 3 | MISMATCH | a imagem publicada não é a do manifest. **PARE** e avise |
    | 2 | UNVERIFIED | abra o post no navegador e confira a olho: arte vertical, manchete inteira e "Fonte: …" visíveis. Se algo faltar, trate como exit 1 |

    `--record` grava o post no `published.jsonl` do segmento (dedupe por source_url e manchete), com qualquer veredito, para nunca repostar a mesma pauta.
12. O relatório da rodada inclui: URL, veredito, `feed_sha256` e `source_url`.

## Proibido
- Gerar arte por outro script, editar PNG, mudar cor/fonte/posição, escrever "Fonte:"/hashtags à mão.
- Usar foto de portal, TV, rede social, agência ou "Reprodução/Divulgação". Sem foto liberada, use `kind: "typo"`.
- Publicar manifest com `publishable: false`.
- Apagar ou republicar post sem ok do Jonas.

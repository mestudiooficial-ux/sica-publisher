# SiCa Publisher: publicar sem o PC ligado (sem cartão de crédito)

## Como funciona
1. A SiCa cria o post, o Mister M aprova e a linha vai para a **Fila de publicação** (Notion): Status "Aprovado", data/hora em "Publicar em", legenda, URLs públicas das imagens e a caixa **Auto** marcada.
2. Um agendador gratuito (**GitHub Actions**) roda o `publisher.py` a cada 30 minutos, na nuvem.
3. O script lê o Notion, publica no Instagram só o que está aprovado, com Auto marcado e com a hora vencida, e marca "Publicado" (ou "Erro") no Notion.
4. O PC pode estar desligado. Quem não tiver "Auto" marcado continua sendo publicado à mão pelo Mister M.

Segurança embutida: sem `--live` e sem `SICA_LIVE=1` nada é publicado; linhas com Auto desmarcado são ignoradas; um erro em um post não trava os outros.

## O que já está pronto
- Fila no Notion: **Fila de publicação · SiCa** (dentro da página "Agente de Marketing SiCa"), já com os posts desta semana (todos com Auto desmarcado).
- `publisher.py` testado offline (`python publisher.py --mock mock_queue.json --now 2026-11-18T19:00:00-03:00`).

## O que falta (ordem)
1. **Meta liberada** (checkpoint resolvido, token novo no `.env`). Sem isso não publica.
2. **Integração do Notion** (feita pelo Mister M, 3 minutos):
   - notion.so/my-integrations > Nova integração interna > copie o token (começa com `ntn_` ou `secret_`). Não cole no chat.
   - Abra a página "Fila de publicação · SiCa" > menu `...` > Conexões > adicione a integração.
   - O ID do banco é `41a74be6e5ad81949043f47792d414d6`.
3. **Hospedagem das imagens (URL pública):** o Instagram só aceita imagem por link público. Opção gratuita e sem cartão: um repositório **público** no GitHub (ex.: `sc-media`) com GitHub Pages ligado. Só se sobe ali a arte já aprovada para publicar. Cole os links na coluna "Imagens (URLs públicas)" (um por linha, na ordem dos slides).
4. **Repositório do código no GitHub** (pode ser privado) com estes arquivos, e em Settings > Secrets and variables > Actions criar: `NOTION_TOKEN`, `NOTION_DB_ID`, `META_ACCESS_TOKEN`, `INSTAGRAM_BUSINESS_ACCOUNT_ID`.
5. O arquivo `.github/workflows/publisher.yml` (já incluído) liga o agendamento.

## Limites a conhecer
- O GitHub pode atrasar tarefas agendadas por alguns minutos. A hora exata não é garantida ao minuto.
- Repositório privado no plano grátis tem 2.000 minutos por mês; rodar a cada 30 minutos usa cerca de 1.500. Repositório público não tem esse limite. O script não contém segredos, então pode ser público.
- Repositório sem atividade por 60 dias pode ter o agendamento pausado pelo GitHub.
- Só publica imagem: Feed, Carrossel e Stories. Reel (vídeo) e LinkedIn ainda não.
- Para o LinkedIn e para o WhatsApp o plano é outro (abaixo).

## WhatsApp e aprovação sem PC (etapa seguinte)
- Um **Cloudflare Worker** (plano gratuito, sem cartão, a confirmar) receberia as respostas do WhatsApp ("aprovado") e mudaria o Status no Notion.
- Depende da Meta liberada e de um número dedicado para a API do WhatsApp Business.

## Segurança
- Tokens só em Secrets do GitHub ou em `.env` local. Nunca no código nem no chat.
- Troque os tokens se algum vazar.

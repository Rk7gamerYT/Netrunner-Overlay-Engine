# Plataformas e capacidades

O Netrunner mantém um adaptador por plataforma, mas entrega mensagens e eventos para o restante do aplicativo no mesmo formato. A tabela abaixo descreve o que o modo atual consegue capturar sem transformar o dashboard em um gerenciador de credenciais.

| Plataforma | Transporte atual | Eventos no modo atual | Limitações conhecidas |
|---|---|---|---|
| Twitch | IRC + Helix opcional | Chat, inscrições, resubs, raids, Bits e espectadores | Contagem e envio exigem credenciais; follows, Channel Points e eventos avançados precisam de EventSub. |
| YouTube Live | `pytchat` + leitura da página | Chat, Super Chat, membros e espectadores | Envio não está disponível no modo atual; a contagem pode ficar indisponível se o markup não a fornecer. |
| TikTok Live | TikTokLive WebSocket | Chat, gifts, follows, likes, shares e espectadores | Envio exige `NETRUNNER_TIKTOK_SESSIONID`; a disponibilidade depende da live e do transporte. |
| Kick | Pusher + API pública do canal | Chat, subscriptions, gifts, follows, raids, doações e espectadores | Envio não está disponível no modo atual; nomes e payloads de eventos podem variar. |

## Contrato dos eventos

Todos os adaptadores tentam preencher os mesmos campos em `event.data`:

- `eventId` para deduplicação;
- `user`, `displayName` e `userId`;
- `message` e `title`;
- `count`, `amount`, `giftName` e `months` quando existirem;
- `duration` quando o alerta precisar de uma duração específica.

## Reconexão e saúde

Twitch, TikTok, YouTube e Kick mantêm o cancelamento pelo dashboard. Twitch e TikTok usam o heartbeat de seus transportes; YouTube mantém polling; Kick usa o keepalive do Pusher. YouTube e Kick reconectam com backoff progressivo, enquanto todos os eventos de status, chat e alertas atualizam `lastActivity` no estado do dashboard.

O estado de cada plataforma está disponível em `GET /api/state` e o registro de capacidades em `GET /api/platforms`. Cada item de plataforma inclui `viewerCount`, `viewerCountUpdatedAt` e as capacidades `viewerCount`, `chatSend` e `chatSendAvailable`. O dashboard usa `POST /api/chat/send` para enviar uma mensagem pela plataforma selecionada.

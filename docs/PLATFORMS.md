# Plataformas e capacidades

O Netrunner mantém um adaptador por plataforma, mas entrega mensagens e eventos para o restante do aplicativo no mesmo formato. A tabela abaixo descreve o que o modo atual consegue capturar sem transformar o dashboard em um gerenciador de credenciais.

| Plataforma | Transporte atual | Eventos no modo atual | Limitações conhecidas |
|---|---|---|---|
| Twitch | IRC anônimo | Chat, inscrições, resubs, raids e Bits | Follows, Channel Points e eventos avançados precisam de EventSub com autenticação. |
| YouTube Live | `pytchat` com polling | Chat, Super Chat e membros | Eventos de inscritos e recursos oficiais da API exigem API key/OAuth. |
| TikTok Live | TikTokLive WebSocket | Chat, gifts, follows, likes e shares | A disponibilidade depende da live e da compatibilidade do transporte TikTokLive. |
| Kick | Pusher | Chat, subscriptions, gifts, follows, raids e eventos de doação quando publicados pela sala | Os nomes e payloads de eventos podem variar; o adaptador conserva o payload original para diagnóstico. |

## Contrato dos eventos

Todos os adaptadores tentam preencher os mesmos campos em `event.data`:

- `eventId` para deduplicação;
- `user`, `displayName` e `userId`;
- `message` e `title`;
- `count`, `amount`, `giftName` e `months` quando existirem;
- `duration` quando o alerta precisar de uma duração específica.

## Reconexão e saúde

Twitch, TikTok, YouTube e Kick mantêm o cancelamento pelo dashboard. Twitch e TikTok usam o heartbeat de seus transportes; YouTube mantém polling; Kick usa o keepalive do Pusher. YouTube e Kick reconectam com backoff progressivo, enquanto todos os eventos de status, chat e alertas atualizam `lastActivity` no estado do dashboard.

O estado de cada plataforma está disponível em `GET /api/state` e o registro de capacidades em `GET /api/platforms`.

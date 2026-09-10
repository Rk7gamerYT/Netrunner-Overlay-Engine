# Overlays de chat e eventos

O Netrunner Overlay Engine 1.2.9 separa a conversa das notificações da live em dois overlays locais. Cada editor possui seu próprio HTML, CSS, JavaScript, biblioteca de arquivos salvos, importação/exportação e prévia.

## URLs para o OBS

Com o aplicativo aberto, copie os links no Dashboard:

- `http://127.0.0.1:5000/overlay` — overlay de chat.
- `http://127.0.0.1:5000/events` — overlay de eventos e notificações.

Adicione cada URL como uma fonte **Navegador** no OBS. O servidor aceita apenas conexões locais; mantenha o Netrunner aberto durante a transmissão.

## Editor de chat

O editor de chat recebe mensagens normalizadas de Twitch, YouTube, TikTok e Kick. O objeto entregue ao template contém:

```json
{
  "id": 42,
  "platform": "twitch",
  "user": "kaua",
  "displayName": "Kaua Alves",
  "userId": "123",
  "message": "Olá!",
  "color": "#9147ff",
  "timestamp": "2026-09-10T12:00:00Z",
  "messageType": "chat",
  "badges": ["moderator"],
  "emotes": [],
  "metadata": {}
}
```

O endpoint de polling é `/api/v1/chat?after=<id>`. O parâmetro `after` faz o overlay buscar apenas mensagens posteriores ao último `id` renderizado. A rota legada `/chat?after=<id>` permanece disponível para templates existentes.

Exemplo mínimo de JavaScript para um overlay de chat:

```js
let lastId = 0;
async function updateChat() {
  const response = await fetch(`/api/v1/chat?after=${lastId}`);
  const messages = await response.json();
  for (const message of messages) {
    lastId = Math.max(lastId, Number(message.id) || 0);
    const row = document.createElement('div');
    row.className = `message ${message.platform}`;
    row.innerHTML = `<b>${message.displayName || message.user}</b> ${message.message}`;
    document.querySelector('#log').append(row);
  }
}
setInterval(updateChat, 1000);
updateChat();
```

## Editor de eventos

Eventos ficam fora do chat para que alertas possam ter duração, animação e hierarquia próprias. Os eventos disponíveis dependem da plataforma conectada e incluem presentes, novos seguidores, inscrições, raids, Super Chats, membresias, likes e compartilhamentos quando o conector fornece esses dados.

Formato normalizado:

```json
{
  "id": 8,
  "platform": "tiktok",
  "type": "gift",
  "timestamp": "2026-09-10T12:00:00Z",
  "data": {
    "user": "viewer",
    "displayName": "Viewer",
    "giftName": "Rose",
    "count": 1,
    "message": ""
  }
}
```

Use `/api/v1/events?after=<id>` para buscar novos eventos. A rota `/events` sem `after` entrega a página HTML do overlay; com `after` ela retorna JSON para o polling.

Exemplo de template de eventos:

```js
let lastEventId = 0;
async function updateEvents() {
  const response = await fetch(`/api/v1/events?after=${lastEventId}`);
  const events = await response.json();
  for (const event of events) {
    lastEventId = Math.max(lastEventId, Number(event.id) || 0);
    const data = event.data || {};
    const alert = document.createElement('div');
    alert.className = `event event-${event.type}`;
    alert.textContent = `${data.displayName || data.user || 'Alguém'} · ${event.type}`;
    document.querySelector('#events').append(alert);
    setTimeout(() => alert.remove(), 8000);
  }
}
setInterval(updateEvents, 1000);
updateEvents();
```

## Transparência, arquivos e modelos

Os modelos base já usam `body { background: transparent; }`, deixando o vídeo do OBS visível. O tabuleiro quadriculado aparece apenas na prévia do editor e não é enviado para o overlay.

Use **Overlays salvos** para selecionar arquivos separados por tipo. O aplicativo mantém os arquivos em:

```text
%LOCALAPPDATA%\NetrunnerOverlay\overlays\chat
%LOCALAPPDATA%\NetrunnerOverlay\overlays\events
```

**Importar** lê um arquivo JSON com `html`, `css` e `js`; **Exportar** grava a configuração do editor selecionado. No Windows, o app abre o seletor de pasta/arquivo nativo. Em uma janela de navegador, o download e upload padrão do navegador são usados.

## API auxiliar

- `GET /api/v1` — versão da API e links dos recursos.
- `GET /api/v1/templates` — modelos base de chat e eventos.
- `GET /api/overlays` — lista as configurações salvas.
- `POST /api/overlays` — salva `{ "kind": "chat|events", "name": "...", "html": "...", "css": "...", "js": "..." }`.
- `POST /api/v1/moderation` — aplica ações de moderação na sessão (`ignore`, `allow` ou `delete`).

Para garantir compatibilidade, templates devem escapar texto inserido no DOM e tratar respostas vazias. O polling é intencionalmente simples para funcionar no Browser Source do OBS sem dependências externas.

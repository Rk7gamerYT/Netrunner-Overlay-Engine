# Overlays de chat e eventos

O Netrunner Overlay Engine 1.3.0 separa a conversa das notificações da live em dois overlays locais. Cada editor possui seu próprio HTML, CSS, JavaScript, biblioteca de arquivos salvos, importação/exportação e prévia.

## URLs para o OBS

Com o aplicativo aberto, copie os links seguros no Dashboard. Cada URL já contém um token opaco próprio e deve ser colada inteira no Browser Source:

- `http://127.0.0.1:5000/overlay?token=...` — overlay de chat.
- `http://127.0.0.1:5000/events?token=...` — overlay de eventos e notificações.

Adicione cada URL como uma fonte **Navegador** no OBS. O servidor aceita apenas conexões locais; mantenha o Netrunner aberto durante a transmissão.

Não remova o parâmetro `token`: ele autoriza a página, o polling e o WebSocket do overlay. Se um link vazar ou precisar ser trocado, use **Configurações → Segurança dos overlays → Rotacionar**. **Revogar** bloqueia o token até que um novo seja gerado. O estado local fica em `security.json` junto da configuração do overlay; ele não contém credenciais das plataformas.

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

O endpoint de polling é `/api/v1/chat?after=<id>&token=...`. O parâmetro `after` faz o overlay buscar apenas mensagens posteriores ao último `id` renderizado. A rota legada `/chat?after=<id>&token=...` permanece disponível para templates existentes.

Quando o servidor local está ativo, o template padrão tenta primeiro `ws://127.0.0.1:5001/ws/chat?after=<id>&token=...` para receber as mensagens em tempo real e recuperar as que chegaram durante uma queda curta. Se a conexão cair ou o gateway não estiver disponível, ele retorna ao polling HTTP automaticamente.

Exemplo mínimo de JavaScript para um overlay de chat:

```js
const overlayToken = new URLSearchParams(location.search).get('token');
const overlayRequest = path => {
  const url = new URL(path, location.href);
  url.searchParams.set('token', overlayToken || '');
  return url;
};
let lastId = 0;
async function updateChat() {
  const response = await fetch(overlayRequest(`/api/v1/chat?after=${lastId}`));
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

Use `/api/v1/events?after=<id>&token=...` para buscar novos eventos. A rota `/events?token=...` entrega a página HTML do overlay; com `after` e o mesmo token ela retorna JSON para o polling.

O transporte em tempo real equivalente é `ws://127.0.0.1:5001/ws/events?after=<id>&token=...`. O WebSocket envia um pacote inicial `hello`; depois, cada mensagem tem o mesmo formato JSON retornado por `/api/v1/events`. O gateway mantém um replay limitado dos últimos 200 itens em memória, permitindo recuperar eventos recebidos durante uma queda curta. O polling continua sendo o fallback compatível com fontes do OBS já configuradas.

Exemplo de template de eventos:

```js
const overlayToken = new URLSearchParams(location.search).get('token');
const overlayRequest = path => {
  const url = new URL(path, location.href);
  url.searchParams.set('token', overlayToken || '');
  return url;
};
let lastEventId = 0;
async function updateEvents() {
  const response = await fetch(overlayRequest(`/api/v1/events?after=${lastEventId}`));
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

**Importar** aceita JSON com `html`, `css`, `js` ou os aliases `markup`, `style`, `script`, além de documentos HTML completos e arquivos CSS/JS separados; **Exportar** grava a configuração do editor selecionado. No Windows, o app abre o seletor de pasta/arquivo nativo. Em uma janela de navegador, o download e upload padrão do navegador são usados. Consulte o [guia de migração](PORTING.md) para adaptar widgets de outras ferramentas.

## API auxiliar

- `GET /api/v1` — versão da API e links dos recursos.
- `GET /api/v1/templates` — modelos base de chat e eventos.
- `POST /api/v1/events/test` — injeta um evento sintético no overlay para validar o tema sem uma live ativa. O campo `type` aceita `follow`, `sub`, `gift`, `donation`, `raid`, `like`, `share`, `bits`, `superchat` e `membership`.
- `GET /api/overlays` — lista as configurações salvas.
- `POST /api/overlays` — salva `{ "kind": "chat|events", "name": "...", "html": "...", "css": "...", "js": "..." }`.
- `POST /api/overlays/validate` — valida tamanho, delimitadores de CSS/JS e caracteres inválidos antes de aplicar.
- `GET /api/overlays/history?target=chat|events` — lista as últimas 20 versões locais.
- `POST /api/overlays/history/load` — restaura uma versão no editor sem publicá-la automaticamente.
- `GET /api/assets` — lista os assets locais disponíveis para uso no código do overlay.
- `POST /api/assets` — salva `{ "name": "alert.mp3", "content": "<base64>" }` na biblioteca local.
- `GET /overlay-assets/<nome>` — serve um asset local para o Browser Source.
- `GET /api/security/tokens` — mostra o estado dos tokens ao dashboard autenticado.
- `POST /api/security/tokens` — recebe `{ "kind": "chat|events", "action": "rotate|revoke" }` no dashboard autenticado.
- `POST /api/v1/webhooks/pix` — recebe uma confirmação Pix assinada e converte para `donation`.
- `POST /api/v1/webhooks/stripe` — recebe uma confirmação Stripe assinada e converte para `donation`.
- `POST /api/v1/moderation` — aplica ações de moderação na sessão (`ignore`, `allow` ou `delete`).
- `GET /api/diagnostics` — retorna saúde do HTTP, WebSocket, fila, plataformas e o último teste de resiliência.
- `POST /api/diagnostics` — inicia `{ "durationSeconds": 60 }`, limitado entre 5 segundos e 1 hora, sem injetar dados artificiais.

O editor não impõe duração, posição, animação ou limite de itens: HTML, CSS e JS continuam sendo a fonte de verdade para a personalização. Os modelos base são apenas pontos de partida. O objetivo é permitir importar e adaptar overlays existentes do Streamlabs, OBS e outras ferramentas sem reescrever tudo; quando a origem depender de APIs próprias, a adaptação deve trocar apenas a camada de dados pelo contrato comum do Netrunner. Para garantir compatibilidade, templates devem escapar texto inserido no DOM e tratar respostas vazias. O polling é intencionalmente simples para funcionar no Browser Source do OBS sem dependências externas.

No overlay de eventos, `window.NetrunnerAssets.preload(url, 'image'|'video'|'audio')` pode ser usado pelo JS personalizado. Eventos que possuam `data.assetUrl` ou `data.soundUrl` também são pré-carregados pela fila padrão.

### Contrato livre de alertas

O tema padrão entende estes campos opcionais em `event.data`, mas o usuário continua livre para ignorá-los ou implementar outra lógica no próprio JS:

- `assetUrl` e `assetType` (`image` ou `video`) — mídia visual do alerta.
- `soundUrl` e `volume` (`0` a `1`) — som do alerta; se o navegador bloquear autoplay, o overlay exibe `Ativar sons` e repete os sons pendentes após a interação.
- `duration` ou `durationMs` — duração visual em milissegundos.
- `priority` — prioridade numérica da fila; valores maiores entram primeiro.
- `cooldownMs` e `cooldownKey` — descarte opcional de repetições durante uma janela.
- `tts`, `ttsText`, `ttsRate` e `ttsVolume` — fala opcional por alerta.

Para habilitar TTS globalmente no JS customizado, use `window.NetrunnerTTS.enabled = true` e configure `window.NetrunnerTTS.blockedWords = ['palavra']`. O contrato não cria controles visuais obrigatórios: HTML, CSS e JS continuam sendo a fonte de verdade para posição, animação, layout, limite de itens e qualquer comportamento adicional.

### Limites e confiança

Os endpoints administrativos exigem a sessão local do dashboard; páginas e APIs de overlay exigem o token do respectivo overlay. O servidor limita requisições HTTP a 40 MB, cada seção HTML/CSS/JS a 1 MB, cada asset a 25 MB e a fila de entrada das plataformas a 2.000 registros. Usuários, mensagens, títulos, metadados e estruturas aninhadas recebidos dos conectores são limitados e sanitizados antes de entrar no estado comum. O HTML/CSS/JS salvo no editor é deliberadamente tratado como código confiável do próprio usuário, para preservar a liberdade de criação; os templates padrão escapam os dados antes de inseri-los no DOM.

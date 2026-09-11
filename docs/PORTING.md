# Guia de migração de overlays

O Netrunner não exige que o usuário abandone o próprio design. O caminho recomendado é importar o HTML, CSS e JS existentes, validar, trocar apenas a camada que lê eventos e aplicar.

## Formatos aceitos pelo editor

- JSON do Netrunner: `{ "html": "...", "css": "...", "js": "..." }`.
- JSON de outras ferramentas com os aliases `markup`, `style` e `script`.
- Documento `.html` ou `.htm`: estilos dentro de `<style>` vão para CSS, scripts JavaScript comuns vão para JS e o conteúdo do `body` vai para HTML.
- Arquivo `.css`: substitui apenas a aba CSS.
- Arquivo `.js`: substitui apenas a aba JS.

Scripts com `type="text/template"` continuam no HTML para não destruir templates usados pelo overlay.

## Contrato comum de eventos

O overlay de eventos recebe um objeto com esta forma:

```js
{
  id: 42,
  platform: 'twitch',
  type: 'gift',
  timestamp: 1789041600000,
  data: {
    eventId: 'origem-123',
    user: 'viewer',
    displayName: 'Viewer',
    userId: 'user-123',
    message: 'enviou uma Rose',
    amount: '10',
    count: 1,
    giftName: 'Rose',
    duration: 5000
  }
}
```

Os tipos mais comuns são `follow`, `subscription`, `gift`, `donation`, `raid`, `like`, `share`, `bits`, `superchat` e `member`. O código do overlay pode ignorar campos que não usar e continuar criando qualquer markup, animação ou fluxo próprio.

## Adaptação de widgets externos

Overlays que dependem de APIs privadas, URLs de widget, variáveis proprietárias ou assets remotos podem exigir uma adaptação manual pequena. A regra é preservar o visual e substituir o leitor de dados pela camada normalizada do Netrunner; não há tentativa de reescrever o HTML/CSS/JS automaticamente.

Exemplo de renderizador independente da plataforma:

```js
function renderEvent(event) {
  const data = event.data || {};
  const name = data.displayName || data.user || 'Alguém';
  const text = data.message || `${name} acionou ${event.type}`;
  // O restante continua sendo o design original do usuário.
}
```

Depois de importar, use o simulador do editor para testar tipos diferentes antes de conectar uma live real.

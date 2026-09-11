# Roadmap do Netrunner Overlay Engine

## Objetivo

O Netrunner deve agregar Twitch, YouTube Live, TikTok Live e Kick em uma única experiência de overlay. O streamer configura os canais uma vez, escolhe um tema e usa um overlay de chat e um overlay de alertas no OBS, sem criar uma configuração diferente para cada plataforma.

As plataformas ficam isoladas nos adaptadores de entrada. O restante do sistema trabalha somente com mensagens e eventos normalizados.

## Estado atual

- [x] Dashboard local em Flask com editor HTML, CSS e JavaScript.
- [x] Overlay de chat em `/overlay` e overlay de eventos em `/events`.
- [x] Adaptadores independentes para Twitch, YouTube, TikTok e Kick.
- [x] Mensagens e eventos passam por uma camada comum no dashboard.
- [x] Polling HTTP funcionando como transporte do Browser Source.
- [x] TikTok com chat, gifts, follows, likes e shares.
- [x] Twitch com chat, inscrições e raids.
- [x] YouTube com chat, Super Chat e membros.
- [x] Kick com chat e listeners para eventos conhecidos.

## Fases

### Fase 1 - Contrato unificado e motor de alertas

Objetivo: fazer qualquer plataforma produzir o mesmo evento e garantir que os alertas sejam exibidos um por vez.

- [x] Normalizar `platform`, `type`, `timestamp` e `data`.
- [x] Preservar campos comuns como usuário, mensagem, quantidade, valor e duração.
- [x] Criar fila FIFO no modelo padrão de eventos.
- [x] Definir catálogo oficial de tipos: `follow`, `subscription`, `gift`, `like`, `share`, `raid`, `superchat`, `donation`, `member`.
- [x] Adicionar deduplicação por identificador de origem.
- [x] Criar testes de contrato para o catálogo e os aliases principais.

### Fase 2 - Adaptadores completos das plataformas

Objetivo: capturar os eventos previstos para cada plataforma, respeitando o que cada API realmente oferece.

- [x] Twitch: documentar o limite do IRC anônimo e o caminho EventSub para follows e Point Redemptions; manter IRC como fallback de chat e Bits.
- [x] YouTube: manter polling do chat, ampliar Super Chat/membros e documentar os eventos que exigem API key ou OAuth.
- [x] Kick: mapear os nomes de eventos Pusher conhecidos, preservar o payload original e tratar subscriptions, follows, raids e doações quando disponíveis.
- [x] TikTok: chat, gifts, follows, likes e shares.
- [x] Unificar reconexão, backoff, heartbeat disponível no transporte, cancelamento, mensagens de erro e `lastActivity`.

Fase concluída: os adaptadores agora carregam `eventId` quando a origem fornece um identificador, entregam campos comuns, expõem capacidades e limitações, atualizam `lastActivity`, e YouTube/Kick possuem reconexão com backoff. Integrações que exigem credenciais próprias ficam explicitamente documentadas.

### Fase 3 - Transporte do overlay

Objetivo: reduzir latência e manter o Browser Source estável em transmissões longas.

- [x] Criar gateway WebSocket local para chat e eventos.
- [x] Manter polling HTTP como fallback.
- [x] Adicionar heartbeat do servidor, reconexão exponencial no cliente e retomada limitada por `lastEventId`.
- [x] Evitar perda de eventos durante queda ou atualização da fonte do OBS com replay do histórico do servidor.

Fase concluída: o overlay tenta `ws://127.0.0.1:5001/ws/chat` ou `/ws/events`, reconecta com backoff exponencial, solicita eventos posteriores ao último ID recebido e volta automaticamente ao polling HTTP quando o gateway fica indisponível. O gateway mantém um buffer rápido e consulta o histórico do servidor para recuperar eventos durante a atualização ou queda curta da fonte do OBS.

### Fase 4 - Editor de overlays

Objetivo: permitir personalização sem exigir conhecimento de código para tarefas comuns.

- [x] Editor separado para chat e eventos.
- [x] Preview, modelos base, importar, exportar e overlays salvos.
- [x] Preview com evento de teste pelo pipeline real.
- [x] Manter HTML, CSS e JS como fonte de verdade, sem impor controles visuais que limitem a personalização.
- [x] Temas reutilizáveis com cores, fontes e componentes como modelos opcionais e totalmente editáveis.
- [x] Validação básica de HTML/CSS/JS e mensagens de erro antes de aplicar.
- [x] Histórico local de alterações e restauração por versão.
- [x] Preview com eventos simulados de follow, inscrição, gift, doação, raid, like, share, Bits, Super Chat e membro.
- [x] Aviso de alterações não salvas e restauração explícita do modelo padrão.
- [x] Importação e adaptação de overlays existentes do Streamlabs, OBS e outras ferramentas, preservando o código original sempre que possível.
- [x] Guia de migração com mapeamento entre eventos/variáveis externas e o contrato comum do Netrunner.

Fase concluída: o editor continua livre em HTML/CSS/JS, oferece validação, histórico, simulador de eventos, modelos opcionais e importação de formatos comuns para facilitar a migração de overlays existentes.

### Fase 5 - Assets e execução de alertas

Objetivo: transformar eventos em alertas visuais e sonoros completos.

- [x] Upload e biblioteca local de PNG, GIF, WebM e áudio.
- [x] Pré-carregamento dos assets usados pelo tema.
- [x] Reprodução de áudio com tratamento de bloqueio do navegador.
- [x] Prioridade e duração por evento, mantendo volume e cooldown livres no JS.
- [x] TTS opcional com filtro de palavras proibidas.
- [x] Fila de prioridade para doações e eventos importantes.

Fase concluída: assets ficam em uma biblioteca local, podem ser enviados pelo editor e usados pelos templates via URL. A fila respeita prioridade e cooldown, pré-carrega `assetUrl`/`soundUrl`, mantém duração e volume definidos pelo evento e trata o desbloqueio de áudio do navegador. TTS é opcional e filtra palavras configuradas pelo JS do overlay.

### Fase 6 - Segurança e operação

Objetivo: preparar o produto para uso seguro e distribuição.

- [x] Tokens opacos para URLs do overlay.
- [x] Geração, rotação e revogação de tokens no dashboard.
- [x] Limites e autenticação para endpoints administrativos.
- [x] Sanitização consistente de conteúdo externo.
- [x] Separar HTML/JS confiável do conteúdo recebido das plataformas.
- [x] Logs de conexão, reconexão, eventos descartados e falhas de parsing.

Fase concluída: o dashboard usa uma sessão administrativa local, cada overlay tem um token independente persistido em `security.json`, e a rotação/revogação invalida URLs antigas. Payloads externos passam por limites de tamanho/profundidade, a fila de captura é limitada e os logs registram conexões realtime, descartes e falhas de parsing. HTML/CSS/JS editados pelo usuário continuam sendo a camada confiável e livre; conteúdo recebido das plataformas permanece dado, escapado nos templates padrão e sanitizado na entrada.

### Fase 7 - Pagamentos e integrações adicionais

Objetivo: receber doações externas dentro do mesmo motor de alertas.

- [x] Modelo comum para doações.
- [x] Webhook de confirmação de Pix.
- [x] Integração opcional com Stripe.
- [x] Validação de assinatura e idempotência dos webhooks.
- [x] Associação segura da doação ao overlay do streamer.

Fase concluída: Pix e Stripe convergem para o evento comum `donation`, com valor em centavos, moeda, provedor, doador, mensagem e streamer de destino. Webhooks exigem assinatura válida, status confirmado e identificador externo; confirmações repetidas são reconhecidas sem gerar outro alerta. O ledger local persiste as confirmações e o evento segue para o mesmo overlay de eventos das plataformas.

### Fase 8 - Qualidade e lançamento

- [x] Testes unitários dos contratos e adaptadores.
- [x] Testes de integração com payloads gravados.
- [x] Teste de longa duração do OBS pelo usuário, com acompanhamento no dashboard.
- [x] Teste de reconexão e recuperação de fila.
- [x] Verificação de transparência, áudio e assets no Browser Source.
- [x] Build, instalador, atualização e documentação de troubleshooting.

Fase implementada na v1.3.0: o dashboard agora expõe **Configurações → Saúde
do sistema**, valida os dois Browser Sources pelos links seguros, informa o
estado do HTTP/WebSocket, acompanha a fila de captura e executa um teste de
resiliência de 5 segundos a 1 hora sem injetar mensagens ou eventos falsos.
Os testes automatizados cobrem 50 casos; a validação final de longa duração
no OBS continua sendo uma ação do usuário durante a transmissão de teste.

## Ordem de implementação

1. Contrato unificado e fila de alertas.
2. Testes com payloads simulados de todas as plataformas.
3. Correção e validação dos adaptadores reais.
4. Preview de eventos e controles do editor.
5. WebSocket local com fallback HTTP.
6. Assets, áudio, TTS e temas.
7. Tokens, pagamentos e preparação para distribuição.

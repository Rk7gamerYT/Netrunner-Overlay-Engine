# Netrunner Overlay Engine

<p align="center">
  <img src="assets/netrunner.png" alt="Netrunner Overlay Engine" width="150">
</p>

O Netrunner reúne mensagens públicas de lives da Twitch, YouTube, TikTok e Kick em um único chat para exibição no OBS Studio. Não é necessário informar senhas, cookies ou credenciais das suas contas.

![Dashboard do Netrunner](docs/images/dashboard.png)

## Instalação

1. Abra a página **Releases** deste repositório.
2. Baixe `NetrunnerOverlay-Setup-v1.2.0-windows-x64.exe`.
3. Execute o instalador e escolha o idioma.
4. Ao concluir, abra **Netrunner Overlay Engine** pelo Menu Iniciar ou pelo atalho opcional da área de trabalho.

Requisitos: Windows 10 ou 11 de 64 bits, conexão com a internet e Microsoft Edge WebView2 Runtime. O OBS Studio é necessário apenas para usar o overlay em uma transmissão.

O Windows SmartScreen pode mostrar um aviso enquanto o instalador não possui assinatura digital. Confirme que o arquivo veio da Release oficial e compare seu SHA-256 com `SHA256SUMS.txt` antes de executá-lo.

## Como usar

Abra **Plataformas** e preencha somente os canais que deseja acompanhar:

- **Twitch:** nome ou URL do canal.
- **YouTube:** URL da live ou ID do vídeo.
- **TikTok:** nome ou `@` do canal.
- **Kick:** nome ou URL do canal.

Clique em **Iniciar / Reconectar captura**. Para trocar algum canal, encerre a captura, altere os campos e conecte novamente.

![Configuração das plataformas](docs/images/plataformas.png)

## Usar no OBS

1. No Dashboard, clique em **Copiar link**.
2. No OBS, adicione uma fonte **Navegador**.
3. Cole `http://127.0.0.1:5000/overlay` no campo URL.
4. Comece com 600 × 800 e ajuste ao layout da sua transmissão.
5. Mantenha o Netrunner aberto enquanto o overlay estiver em uso.

Consulte o [guia do OBS](docs/OBS.md) se precisar atualizar a fonte ou resolver um overlay vazio.

## Personalizar o overlay

O **Overlay Editor** permite ajustar a aparência e acompanhar a mesma prévia que será exibida no OBS. Depois de editar, clique em **Salvar e aplicar**.

![Editor e prévia real do overlay](docs/images/overlay-editor.png)

As personalizações ficam salvas em:

```text
%LOCALAPPDATA%\NetrunnerOverlay\overlay.json
```

Esse arquivo contém somente o HTML, CSS e JavaScript personalizados do overlay. Ele pode ser copiado como backup e restaurado no mesmo local.

## Idiomas e configurações

A interface está disponível em Português, Inglês, Espanhol e Francês. O idioma pode ser alterado em **Configurações**.

![Configurações do Netrunner](docs/images/configuracoes.png)

## Desinstalação

1. Abra **Configurações do Windows → Aplicativos → Aplicativos instalados**.
2. Localize **Netrunner Overlay Engine**.
3. Abra o menu do aplicativo e clique em **Desinstalar**.

O desinstalador pergunta se você também deseja apagar as personalizações salvas. Escolha **Não** para preservá-las para uma instalação futura.

## Solução rápida de problemas

- **Overlay vazio:** confirme que o Netrunner está aberto e atualize o cache da fonte Navegador no OBS.
- **Uma plataforma não conecta:** confira o canal informado e se a live está ativa.
- **Mensagens pararam:** encerre e reconecte a captura; depois atualize a fonte no OBS.
- **Porta 5000 ocupada:** feche outra instância do Netrunner ou o programa que estiver usando essa porta.
- **Arquivo bloqueado pelo antivírus:** baixe novamente somente pela Release oficial e confira o SHA-256.

## Privacidade

- As mensagens permanecem temporariamente na memória e não são gravadas em histórico pelo Netrunner.
- O aplicativo não possui telemetria própria nem solicita credenciais das plataformas.
- O servidor do overlay aceita somente conexões locais em `127.0.0.1`.
- O projeto é independente e não possui vínculo oficial com Twitch, YouTube, TikTok, Kick ou OBS.

O código-fonte proprietário permanece fechado. O download oficial é distribuído somente como instalador e segue a [licença de distribuição binária](LICENSE.md). Componentes de terceiros mantêm suas próprias licenças, descritas em [Avisos de terceiros](THIRD_PARTY_NOTICES.md).

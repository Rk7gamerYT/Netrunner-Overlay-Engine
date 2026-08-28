# Configuração do overlay no OBS

## Adicionar a fonte

1. Abra o Netrunner Overlay Engine.
2. Clique em **COPIAR LINK DO OBS**.
3. No OBS Studio, localize a cena desejada.
4. Em **Fontes**, clique em **+** e selecione **Navegador**.
5. Crie uma nova fonte e cole `http://127.0.0.1:5000` no campo URL.
6. Comece com 600 × 800 e redimensione conforme o seu layout.

O fundo do overlay é transparente. Não é necessário aplicar chroma key.

## Atualizar a fonte

Se o OBS mantiver uma versão antiga:

1. Abra as propriedades da fonte Navegador.
2. Clique em **Atualizar cache da página atual**.
3. Caso necessário, desative e ative a fonte uma vez.

## Mensagens pararam de chegar

1. Confirme que a janela do Netrunner continua aberta.
2. Veja se novas mensagens aparecem na pré-visualização interna.
3. Atualize o cache da fonte no OBS.
4. Encerre e reconecte a captura no aplicativo.
5. Confirme que não existem duas instâncias do Netrunner disputando a porta 5000.

## Uso em outro computador

O endereço `http://127.0.0.1:5000` funciona somente quando OBS e Netrunner estão no mesmo computador. Por segurança, esta é a configuração recomendada. Não encaminhe a porta 5000 no roteador nem exponha o overlay à internet.

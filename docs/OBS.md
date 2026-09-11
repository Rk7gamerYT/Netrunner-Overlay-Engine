# Configuração do overlay no OBS

## Adicionar a fonte

1. Abra o Netrunner Overlay Engine.
2. Clique em **COPIAR LINK DO OBS**.
3. No OBS Studio, localize a cena desejada.
4. Em **Fontes**, clique em **+** e selecione **Navegador**.
5. Crie uma nova fonte e cole no campo URL o link seguro de chat copiado no Dashboard (ele contém `?token=...`).
6. Comece com 600 × 800 e redimensione conforme o seu layout.

O fundo do overlay é transparente. Não é necessário aplicar chroma key.

## Diagnóstico antes da live

Em **Configurações → Saúde do sistema**, clique em **Validar Browser Sources**.
O teste confere os dois links seguros, o HTML entregue pelo servidor, a
transparência declarada pelo tema, o runtime do overlay e a biblioteca de
assets local. O WebSocket é um transporte opcional; se estiver indisponível,
o template padrão continua no polling HTTP.

Use **Teste de resiliência** para observar a fila de captura e as amostras do
transporte realtime durante alguns minutos. Esse teste não cria mensagens,
eventos, sons ou doações artificiais. Para uma verificação completa, deixe a
fonte Navegador aberta no OBS pelo período escolhido e confirme que o resultado
fica como **concluído**.

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

Por segurança, o overlay funciona somente no mesmo computador em que o Netrunner está aberto.


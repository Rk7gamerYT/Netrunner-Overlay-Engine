# Avisos de componentes de terceiros

O Netrunner Overlay Engine inclui componentes de terceiros. Esses componentes permanecem sob suas próprias licenças e não são abrangidos pelas restrições aplicadas ao código proprietário do Netrunner.

## Qt for Python / PySide6 6.8.3

A interface utiliza PySide6 e bibliotecas Qt distribuídas, para esta versão, sob a GNU Lesser General Public License versão 3 (LGPL-3.0). As bibliotecas compartilhadas permanecem separadas no diretório `_internal` do pacote para que possam ser substituídas por versões compatíveis.

O usuário pode estudar, modificar, substituir e realizar a engenharia reversa necessária para depurar modificações nesses componentes, conforme permitido pela LGPL. O texto integral acompanha o pacote em `licenses/LGPL-3.0.txt`.

### Oferta do código-fonte correspondente

Mediante solicitação por uma issue no repositório oficial, o mantenedor fornecerá gratuitamente uma cópia digital do código-fonte correspondente das bibliotecas Qt/PySide6 distribuídas nesta versão, incluindo as informações necessárias para substituir as bibliotecas. Esta oferta permanece válida até 28 de agosto de 2029.

Projeto e documentação: https://doc.qt.io/qtforpython-6/

## TikTokLive 7.0.0

A integração de leitura utiliza TikTokLive 7.0.0 sob a licença Modified AGPL-3.0 e sua exceção específica para integrações downstream. O texto integral fornecido pelo pacote acompanha esta distribuição em `licenses/TikTokLive-LICENSE.txt`.

## Python e demais bibliotecas

O executável contém o runtime do Python e bibliotecas sob licenças permissivas ou compatíveis, incluindo Flask, Werkzeug, Jinja2, Requests, HTTPX, websockets, pytchat, pysher e suas dependências. Os textos e avisos disponíveis nos pacotes utilizados acompanham a distribuição no diretório `licenses`.

As marcas e nomes de projetos pertencem aos respectivos titulares. A inclusão de uma biblioteca não implica endosso ao Netrunner.
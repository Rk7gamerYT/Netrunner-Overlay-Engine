# Política de Segurança

## 📋 Visão Geral

Este documento descreve as práticas de segurança do Netrunner Overlay Engine, incluindo como reportar vulnerabilidades e usar o aplicativo de forma segura.

---

##  Avisos Importantes

### Falsos Positivos em Antivírus

O instalador `NetrunnerOverlay-Setup-*.exe` pode ser detectado por alguns antivírus como malicioso. **Isto é um falso positivo.**

**Por que isso acontece?**
- O aplicativo é empacotado com **PyInstaller** (ferramenta para distribuir programas Python)
- O instalador ainda não possui assinatura digital
- O programa cria um servidor web local (`127.0.0.1:5000`) para o overlay no OBS
- Bibliotecas de terceiros podem acionar heurísticas de segurança

**Como verificar a segurança:**
1. ✅ Baixe **SOMENTE** da [página oficial de Releases](https://github.com/Rk7gamerYT/Netrunner-Overlay-Engine/releases)
2. ✅ Compare o hash SHA-256 com o arquivo `SHA256SUMS.txt`
3. ✅ O código-fonte está disponível para auditoria
4. ✅ Verifique em [VirusTotal](https://www.virustotal.com) - tipicamente 1/70 detecções

**O que estamos fazendo:**
- 🔄 Reportamos o falso positivo para os fabricantes de antivírus
- 🔄 Buscamos assinatura de código gratuita (projetos open source)
- 🔄 Mantemos o código transparente e auditável

Se seu antivírus bloquear o instalador:
- Adicione uma exceção temporária
- Ou compile você mesmo a partir do código-fonte

---

## 🛡️ Uso Seguro

### Download e Verificação

- ✅ **Baixe SOMENTE** da página oficial de [Releases](https://github.com/Rk7gamerYT/Netrunner-Overlay-Engine/releases)
- ✅ **Compare o SHA-256** do instalador com `SHA256SUMS.txt`
- ✅ **Verifique a assinatura** do commit no GitHub
-  **NÃO execute** cópias modificadas ou obtidas de terceiros
- ❌ **NÃO forneça** credenciais das plataformas ao aplicativo

### Configuração de Rede

- Use `http://127.0.0.1:5000/overlay` no OBS
- **NÃO exponha** a porta 5000 à internet
- **NÃO encaminhe** a porta no roteador
- Verifique suas regras de firewall regularmente

### Credenciais e Dados

- 🔒 O Netrunner **NÃO solicita** senha, cookie ou token de Twitch, YouTube, TikTok ou Kick
- 🔒 As mensagens permanecem temporariamente na memória
-  Não há histórico permanente nem telemetria
- 🔒 O servidor aceita **somente** conexões locais

---

## 📌 Versões Suportadas

| Versão | Status de Segurança |
|--------|---------------------|
| **Última Release** | ✅ Suportada com correções |
| Versões anteriores | ❌ Sem suporte |

> **Importante:** Apenas a versão mais recente publicada na página de [Releases](https://github.com/Rk7gamerYT/Netrunner-Overlay-Engine/releases) recebe correções de segurança. Mantenha sempre atualizado.

---

## 🚨 Reportando uma Vulnerabilidade

### O que Reportar

- Vulnerabilidades de segurança
- Problemas de privacidade
- Vazamentos de dados
- Configurações inseguras
- Dependências vulneráveis

### Como Reportar

**⚠️ IMPORTANTE:** Não publique detalhes exploráveis, credenciais, cookies ou dados pessoais em uma issue pública.

**Passos:**

1. **Contato Privado:** Entre em contato com o mantenedor pelo perfil do GitHub [@Rk7gamerYT](https://github.com/Rk7gamerYT) antes de divulgar detalhes técnicos

2. **Informações Necessárias:**
   - Versão do aplicativo
   - Versão do Windows
   - Comportamento observado
   - Passos mínimos para reprodução
   - Impacto potencial da vulnerabilidade

3. **Aguarde Resposta:** Aguarde nosso retorno antes de divulgar publicamente

### O que Esperar

- ✅ **Resposta inicial:** Em até 7 dias úteis
- ✅ **Análise técnica:** Avaliação do impacto e severidade
- ✅ **Correção:** Desenvolvimento e teste de patch
- ✅ **Publicação:** Release com correção e agradecimento (se desejar)

---

## 📜 Políticas de Uso

O projeto agrega mensagens públicas para exibição em overlay. 

**NÃO É AUTORIZADO:**
-  Abuso ou automação de spam
- ❌ Assédio ou harassment
- ❌ Evasão de controles das plataformas
- ❌ Violação de leis e termos aplicáveis
- ❌ Coleta de dados pessoais sem consentimento

O uso do software implica na aceitação destas condições.

---

## 🔗 Recursos Adicionais

- [Documentação Principal](README.md)
- [Política de Privacidade](PRIVACY.md)
- [Termos de Licença](LICENSE.md)
- [Avisos de Terceiros](THIRD_PARTY_NOTICES.md)
- [Releases Oficiais](https://github.com/Rk7gamerYT/Netrunner-Overlay-Engine/releases)

---

## 📞 Contato

**Dúvidas sobre segurança?**
- GitHub: [@Rk7gamerYT](https://github.com/Rk7gamerYT)
- Issues: [Página de Issues](https://github.com/Rk7gamerYT/Netrunner-Overlay-Engine/issues) (apenas para questões não-sensíveis)

---

*Última atualização: Setembro de 2026*
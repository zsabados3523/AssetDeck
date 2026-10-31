# Política de Segurança — AssetDeck

O AssetDeck leva a segurança e a privacidade dos seus usuários muito a sério. Por ser uma ferramenta para criadores e artistas 3D que lidam com acervos locais de arquivos, nosso modelo de segurança foi projetado para ser simples, transparente e estritamente local.

## Versões Suportadas

Correções de segurança são aplicadas na branch principal (`main`) e na versão estável mais recente.

| Versão | Suportada |
| --- | --- |
| 0.1.x | :white_check_mark: |
| < 0.1.0 | :x: |

## Modelo de Segurança e Arquitetura

Para entender o escopo de segurança do projeto, observe as seguintes características arquiteturais:

- **100% Offline:** O AssetDeck não realiza requisições para a internet, não possui telemetria, não se comunica com servidores externos e não exige criação de conta.
- **Biblioteca somente-leitura por padrão:** O aplicativo não apaga, renomeia ou altera arquivos da sua biblioteca sem o seu comando explícito. As únicas exceções são a renomeação em lote e a movimentação de assets entre pastas — ambas exibem previamente um diálogo de confirmação detalhado antes de tocar no disco.
- **Ponte local com o Blender (`assetdeck/bridge`):**
  - O servidor interno utiliza `QTcpServer` e escuta **exclusivamente no endereço de loopback `127.0.0.1`** (porta padrão `45017`). Nenhuma conexão externa ou vinda de outras máquinas da rede é aceita.
  - A comunicação exige um **token secreto** gerado aleatoriamente na primeira execução (`secrets.token_urlsafe(24)`) e salvo no arquivo de configuração local (`config.json`).
  - Cada comando enviado pelo add-on do Blender deve conter o token correspondente; conexões sem token ou com token inválido são imediatamente rejeitadas (`bad_token`).
  - O protocolo opera via mensagens JSON em linha única com tamanho máximo estrito de 256 KB (`MAX_MESSAGE_BYTES`), evitando sobrecarga ou estouro de buffer por requisições malformadas.

## Como reportar uma vulnerabilidade

Se você identificou uma vulnerabilidade de segurança no AssetDeck, agradecemos a sua ajuda em nos notificar de forma responsável.

> **Importante:** Por favor, **NÃO crie issues públicas** no repositório para relatar vulnerabilidades ou falhas que possam colocar usuários em risco.

Para reportar uma vulnerabilidade de forma privada:

1. Acesse a aba **Security** do repositório no GitHub.
2. Clique em **Advisories** ou use o link direto: [Report a vulnerability](https://github.com/zsabados3523/AssetDeck/security/advisories/new).
3. Preencha os detalhes da falha:
   - Descrição clara da vulnerabilidade.
   - Passos detalhados para reproduzir o problema (com prova de conceito, se aplicável).
   - Sistemas operacionais e versões afetadas.
   - Impacto estimado.

Seu relatório será analisado pelos mantenedores do projeto em canal confidencial. Coordenaremos a correção, os testes e o lançamento de uma nova versão antes de publicar qualquer detalhe técnico sobre a vulnerabilidade.

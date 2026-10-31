# Contribuindo com o AssetDeck

Obrigado pelo interesse em contribuir com o AssetDeck! Este documento resume como configurar o ambiente, executar o projeto, rodar os testes e as diretrizes a seguir ao enviar um Pull Request.

## Código de Conduta e Segurança

- Ao participar deste projeto, você concorda em seguir o nosso [Código de Conduta](CODE_OF_CONDUCT.md).
- Para relatar vulnerabilidades ou falhas de segurança de forma privada e responsável, consulte a nossa [Política de Segurança](SECURITY.md).

## Como reportar bugs

Se você encontrou um erro no AssetDeck:

1. Verifique se o problema já não foi relatado nas [Issues do repositório](https://github.com/zsabados3523/AssetDeck/issues).
2. Abra um novo relato usando o formulário de [Bug Report](.github/ISSUE_TEMPLATE/bug.yml).
3. Informe seu sistema operacional, forma de execução (executável pré-compilado ou código-fonte) e passos para reprodução.
4. Anexe trechos relevantes dos logs (`assetdeck.log` ou `quedas.txt`). No aplicativo, você pode abrir a pasta de logs diretamente pelo menu **Configurações → Manutenção → Abrir pasta de logs** ou **Ajuda → Abrir pasta de logs** (localizada em `~/.local/share/assetdeck/logs` no Linux, `%LOCALAPPDATA%\assetdeck\logs` no Windows e `~/Library/Application Support/assetdeck/logs` no macOS).

## Como propor funcionalidades

Novas ideias e melhorias são muito bem-vindas:

1. Para discussões conceituais ou dúvidas de design, considere abrir um tópico nas [Discussões da Comunidade](https://github.com/zsabados3523/AssetDeck/discussions).
2. Para propostas formais, abra uma issue utilizando o formulário de [Feature Request](.github/ISSUE_TEMPLATE/feature.yml).
3. Descreva a motivação prática no seu fluxo de trabalho 3D/artístico e detalhe como imagina o comportamento esperado no app.

## Áreas onde ajuda é bem-vinda

Se você deseja colaborar com código ou testes, destacamos algumas áreas prioritárias:

- **Testes em Windows e macOS reais:** verificação de atalhos, renderização de fontes, caminhos de arquivo e estabilidade da interface gráfica em diferentes versões dos sistemas operacionais.
- **Traduções e localização (i18n):** expansão e refinamento do suporte a outros idiomas na interface.
- **Empacotamento e distribuição:** geração de instaladores, suporte a assinaturas digitais de binários para Windows (SmartScreen) e macOS (Gatekeeper / notarização com Apple ID).
- **Documentação:** guias de uso, tutoriais de integração com o Blender e documentação de arquitetura.

## Como rodar o projeto

1. **Clone o repositório e crie um ambiente virtual com Python 3.12:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # No Windows: .venv\Scripts\activate
   ```

2. **Instale as dependências:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Execute o aplicativo:**
   ```bash
   python -m assetdeck
   ```

## Como testar

Antes de abrir um Pull Request, execute a suíte de testes em modo headless (sem abrir janelas gráficas):

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

Todos os testes devem passar.

## Diretrizes e regras de desenvolvimento

- **Uma mudança por PR:** mantenha Pull Requests pequenos, atômicos e focados em um único objetivo.
- **Biblioteca somente-leitura:** a biblioteca de arquivos do usuário é estritamente somente-leitura. O app nunca move, renomeia ou apaga arquivos do usuário por conta própria. As únicas duas exceções permitidas no app são o renomeador em lote (`batch_rename`) e a ação explícita de mover assets (`mover`), que sempre exigem confirmação do usuário e operam com segurança.
- **Nenhum `except` silencioso:** trate exceções com contexto e registre-as no log (`log.warning`, `log.error` ou `log.exception`). Nunca use `except: pass` sem tratamento ou logging adequado.
- **Nenhum `setStyleSheet` fora de `assetdeck/ui/theme.py`:** cores, raios, espaçamentos e fontes devem ser declarados como tokens em `theme.py` e usados via `$nome` em `theme.qss`.
- **Não enfraqueça testes:** se um teste falhar, conserte o código e a implementação, nunca relaxe ou desative as asserções de um teste para que ele passe.

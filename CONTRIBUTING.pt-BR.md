# Contribuindo com o AssetDeck

[English](CONTRIBUTING.md) | Português (Brasil)

Obrigado pelo interesse em contribuir com o AssetDeck! Este documento resume como configurar o ambiente, executar o projeto, rodar os testes e as diretrizes a seguir ao enviar um Pull Request.

## Código de Conduta e Segurança

- Ao participar deste projeto, você concorda em seguir o nosso [Código de Conduta](CODE_OF_CONDUCT.pt-BR.md).
- Para relatar vulnerabilidades ou falhas de segurança de forma privada e responsável, consulte a nossa [Política de Segurança](SECURITY.pt-BR.md).

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
- **Traduções e localização da interface (i18n):** traduzir a interface para outros idiomas (espanhol, francês, alemão, japonês, etc.) e manter as traduções existentes atualizadas. Consulte a seção [Traduções (i18n)](#traduções-i18n) abaixo.
- **Empacotamento e distribuição:** geração de instaladores, suporte a assinaturas digitais de binários para Windows (SmartScreen) e macOS (Gatekeeper / notarização com Apple ID).
- **Documentação e tutoriais:** guias de uso, tutoriais de integração com o Blender e documentação de arquitetura.
- **Novos formatos de asset:** novos loaders e importadores para formatos 3D, materiais ou texturas.
- **Correção de bugs e melhorias:** confira as issues marcadas com as etiquetas [`good first issue`](https://github.com/zsabados3523/AssetDeck/labels/good%20first%20issue) e [`help wanted`](https://github.com/zsabados3523/AssetDeck/labels/help%20wanted).

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

### Cobertura

O CI imprime um resumo de cobertura do pacote `assetdeck` (ainda sem limite mínimo). Para ver localmente:

```bash
pip install pytest-cov
QT_QPA_PLATFORM=offscreen pytest -q --cov=assetdeck --cov-report=term
```

Linha de base (2026-11): **81%** no total (9753 instruções, 1063 testes).

## Diretrizes e regras de desenvolvimento

- **Uma mudança por PR:** mantenha Pull Requests pequenos, atômicos e focados em um único objetivo.
- **Biblioteca somente-leitura:** a biblioteca de arquivos do usuário é estritamente somente-leitura. O app nunca move, renomeia ou apaga arquivos do usuário por conta própria. As únicas duas exceções permitidas no app são o renomeador em lote (`batch_rename`) e a ação explícita de mover assets (`mover`), que sempre exigem confirmação do usuário e operam com segurança.
- **Nenhum `except` silencioso:** trate exceções com contexto e registre-as no log (`log.warning`, `log.error` ou `log.exception`). Nunca use `except: pass` sem tratamento ou logging adequado.
- **Nenhum `setStyleSheet` fora de `assetdeck/ui/theme.py`:** cores, raios, espaçamentos e fontes devem ser declarados como tokens em `theme.py` e usados via `$nome` em `theme.qss`.
- **Não enfraqueça testes:** se um teste falhar, conserte o código e a implementação, nunca relaxe ou desative as asserções de um teste para que ele passe.

## Traduções (i18n)

O AssetDeck utiliza o sistema de internacionalização do Qt (Qt Linguist) via PySide6. O idioma-fonte no código é o Português do Brasil (`pt-BR`), e as traduções são carregadas 100% offline a partir de arquivos compilados `.qm` em `translations/`.

### Diretrizes para desenvolvedores

1. **Strings visíveis para o usuário:** Sempre envolva textos de interface com `self.tr("...")` em subclasses de `QObject` ou `QCoreApplication.translate("Contexto", "...")` fora delas.
2. **Parâmetros dinâmicos:** Use marcadores `%1`, `%2` do Qt com `.arg(...)`:
   ```python
   self.tr("Processando %1 arquivos...").arg(total)
   ```
3. **Não traduza:** Mensagens de log, identificadores ou colunas do banco de dados, chaves internas de configuração ou nomes de formatos de arquivo.
4. **Texto-fonte:** Sempre mantenha o texto original no código em Português do Brasil (`pt-BR`).

### Atualizando traduções existentes

Quando novas strings forem adicionadas ou alteradas no código:

1. Extraia as strings atualizadas para os arquivos `.ts`:
   ```bash
   python tools/build_translations.py --update
   ```
2. Edite `translations/assetdeck_<idioma>.ts` (usando o Qt Linguist ou editor de texto) para preencher as traduções e remover `type="unfinished"`.
3. Compile os arquivos `.ts` para binários `.qm`:
   ```bash
   python tools/build_translations.py --release
   ```
4. Execute os testes para garantir integridade e que não há entradas pendentes:
   ```bash
   QT_QPA_PLATFORM=offscreen pytest tests/test_i18n.py
   ```
5. Envie tanto o arquivo `.ts` quanto o `.qm` no Pull Request.

### Adicionando um novo idioma

1. Execute `python tools/build_translations.py --update --lang <codigo_iso>` (ex.: `es` ou `fr`).
2. Traduza todas as entradas em `translations/assetdeck_<codigo_iso>.ts`.
3. Compile com `python tools/build_translations.py --release --lang <codigo_iso>`.
4. Registre o novo idioma em `SUPPORTED_LANGUAGES` em `assetdeck/i18n.py` e adicione a opção no seletor de idiomas em `assetdeck/ui/preferences_dialog.py`.


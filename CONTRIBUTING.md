# Contribuindo com o AssetDeck

Obrigado pelo interesse em contribuir com o AssetDeck! Este documento resume como configurar o ambiente, executar o projeto, rodar os testes e as diretrizes a seguir ao enviar um Pull Request.

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

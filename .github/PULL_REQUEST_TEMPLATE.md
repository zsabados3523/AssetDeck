## Description / Descrição da Alteração

Please describe clearly and objectively what this Pull Request changes, adds, or fixes, and the motivation behind the change.
*Descreva de forma clara e objetiva o que este Pull Request altera, adiciona ou corrige, e a motivação por trás da mudança.*

Fixes #(issue) <!-- If applicable, link the corresponding issue / Se aplicável, vincule a issue correspondente -->

## Type of Change / Tipo de Mudança

- [ ] Bug fix / Correção de bug
- [ ] New feature / Nova funcionalidade
- [ ] Performance improvement or refactoring / Melhoria de desempenho ou refatoração
- [ ] Documentation update / Ajuste de documentação
- [ ] Other / Outro: 

## Compliance Checklist / Checklist de Conformidade

Please verify that your contribution complies with all project guidelines before requesting review:
*Por favor, verifique se sua contribuição atende a todas as diretrizes do projeto antes de solicitar revisão:*

- [ ] **Local tests / Testes locais:** I ran tests with `QT_QPA_PLATFORM=offscreen pytest -q` and all tests passed. / *Executei os testes com `QT_QPA_PLATFORM=offscreen pytest -q` e todos os testes passaram com sucesso.*
- [ ] **No silent exceptions / Nenhum except silencioso:** All handled exceptions include context and proper logging (`log.warning`, `log.error`, or `log.exception`). There are no bare `except: pass` blocks. / *Todas as exceções tratadas possuem contexto e logging apropriado (`log.warning`, `log.error` ou `log.exception`). Não há blocos `except: pass` vazios.*
- [ ] **Centralized styles / Estilos centralizados:** No calls to `setStyleSheet` outside `assetdeck/ui/theme.py`. Colors, radii, spacing, and fonts use tokens defined there and `$token` references in `assetdeck/ui/theme.qss`. / *Não há chamadas a `setStyleSheet` fora de `assetdeck/ui/theme.py`. Cores, raios, espaçamentos e fontes usam tokens definidos lá e referências `$token` em `assetdeck/ui/theme.qss`.*
- [ ] **New tests included / Novos testes inclusos:** Added tests covering modified or fixed scenarios. / *Adicionei testes cobrindo os cenários alterados ou corrigidos.*
- [ ] **Existing tests preserved / Testes existentes preservados:** Did not weaken, comment out, or relax existing assertions to mask failures. / *Não enfraqueci, comentei ou relaxei asserções de testes existentes para mascarar falhas.*
- [ ] **Database Schema / Schema do Banco de Dados:** If this PR modifies SQLite tables or columns, updated the schema documentation and the corresponding migration. / *Se este PR introduz modificações em tabelas ou colunas do SQLite, li e atualizei `SCHEMA.md` e a migração correspondente.*
- [ ] **Read-only library / Biblioteca somente-leitura:** Library files remain intact, honoring the read-only principle (only permitted write operations are `mover` and `batch_rename`, always under user confirmation). / *A biblioteca de arquivos permanece intacta, respeitando o princípio de somente-leitura (as únicas operações de escrita permitidas são `mover` e `batch_rename`, sempre sob confirmação do usuário).*
- [ ] **No production mocks / Sem mocks em produção:** No mocked data or behaviors in production code (mocks only in `tests/`). / *Não há dados ou comportamentos mockados no código de produção (mocks apenas em `tests/`).*

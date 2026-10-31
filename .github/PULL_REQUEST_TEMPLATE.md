## Descrição da Alteração

Descreva de forma clara e objetiva o que este Pull Request altera, adiciona ou corrige, e a motivação por trás da mudança.

Fixes #(issue) <!-- Se aplicável, vincule a issue correspondente -->

## Tipo de Mudança

- [ ] Correção de bug (bug fix)
- [ ] Nova funcionalidade (feature)
- [ ] Melhoria de desempenho ou refatoração
- [ ] Ajuste de documentação
- [ ] Outro: 

## Checklist de Conformidade

Por favor, verifique se sua contribuição atende a todas as diretrizes do projeto antes de solicitar revisão:

- [ ] **Testes locais:** Executei os testes com `QT_QPA_PLATFORM=offscreen pytest -q` e todos os testes passaram com sucesso.
- [ ] **Nenhum except silencioso:** Todas as exceções tratadas possuem contexto e logging apropriado (`log.warning`, `log.error` ou `log.exception`). Não há blocos `except: pass` vazios.
- [ ] **Estilos centralizados:** Não há chamadas a `setStyleSheet` fora de `assetdeck/ui/theme.py`. Cores, raios e fontes usam tokens definidos lá e referências `$token` em `assetdeck/ui/theme.qss`.
- [ ] **Novos testes inclusos:** Adicionei testes cobrindo os cenários alterados ou corrigidos.
- [ ] **Testes existentes preservados:** Não enfraqueci, comentei ou relaxei asserções de testes existentes para mascarar falhas.
- [ ] **Schema do Banco de Dados:** Se este PR introduz modificações em tabelas ou colunas do SQLite, li e atualizei `SCHEMA.md` e a migração correspondente.
- [ ] **Biblioteca somente-leitura:** A biblioteca de arquivos permanece intacta, respeitando o princípio de somente-leitura (as únicas operações de escrita permitidas são `mover` e `batch_rename`, sempre sob confirmação do usuário).
- [ ] **Sem mocks em produção:** Não há dados ou comportamentos mockados no código de produção (mocks apenas em `tests/`).

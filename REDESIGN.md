# AssetDeck — redesenho visual

Estado em 2026-09-24. Os mockups foram revisados e aprovados pelo Rafael. A implementação está na branch `codex/redesign-final-review`, empilhada sobre uma branch por fatia.

## Direção aprovada

- Tema claro com fundo branco puro; superfícies brancas separadas por contornos discretos.
- Identidade monocromática P&B nos dois temas. Avisos e erros conservam cores semânticas; os realces de seleção e foco usam neutros.
- Filtros de categoria compactos: ícone e contagem, com o rótulo visível quando selecionados.
- Cards mostram nome e tipo específico do asset; tags continuam nos detalhes e não viram subtítulo do card.
- Grade com densidade equilibrada, controle de tamanho mais largo e leitura em pixels.
- Janelas secundárias conservam a moldura nativa do Linux; cabeçalho, conteúdo e ações internas seguem o mesmo padrão.
- Movimento curto para hover, com opção “Reduzir movimento”. Sem sombras caras por card.

## Fatias implementadas

| Fatia | Branch | Commit | Conteúdo |
|---|---|---|---|
| Fundação visual | `codex/visual-foundation` | `5157dc2` | Paleta neutra e contraste claro/escuro |
| Janela principal e grade | `codex/main-grid-redesign` | `3c26f69` | Slider ampliado, leitura do valor e subtítulo de tipo |
| Lateral e detalhes | `codex/sidebar-details-redesign` | `2a32496` | Rótulos compartilhados e seções acessíveis por teclado |
| Previews e visualizadores | `codex/previews-viewers-redesign` | `9bc78b4` | Nomes de mapas legíveis e controles acessíveis |
| Aparência e movimento | `codex/settings-dialogs-redesign` | `dcbc4e3` | Preferência de movimento, estados de foco e tema |
| Revisão de diálogos | `codex/redesign-final-review` | este commit | Cabeçalho e faixa de ações compartilhados nos diálogos |

Sem alteração no schema do banco. A biblioteca segue somente para leitura.

## Verificação

- Testes focados de tema: 56 passaram.
- Janela/grade em 1280×800 e 1600×900 e testes do delegate: 24 passaram.
- Lateral, detalhes, filtros e tema: 136 passaram.
- Preview e visualizadores: 39 passaram.
- Preferência de movimento e tema: 58 passaram.
- Diálogos padronizados: 37 passaram.
- Revisão final: 116 testes focados passaram; `git diff --check` passou; capturas claro/escuro conferidas em 1280×800; testes de layout cobrem 1280×800 e 1600×900.
- A captura visual usa o backend Qt offscreen: este ambiente não tem uma sessão X disponível e falta a dependência `xcb-cursor0` para abrir a janela nativa.
- Na tentativa da suíte inteira, 956 testes passaram antes de um erro ambiental em `test_modo_screenshot_nao_trava_num_dialogo`: o sandbox redirecionou um caminho temporário para `/media/root/...`, onde `stat` falhou com `PermissionError`. O teste isolado reproduziu a limitação. A suíte ainda precisa de uma execução integral fora desse sandbox.

## Status final

- O redesign aprovado está implementado nas seis fatias listadas acima, sem alteração de schema e sem escrita na biblioteca.
- A conferência visual dos diálogos e visualizadores nativos ainda depende de uma sessão gráfica Linux; os testes automatizados de diálogos passaram.
- A execução integral de `pytest -q` segue pendente em ambiente fora das restrições de caminho temporário deste sandbox.

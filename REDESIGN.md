# REDESIGN.md — plano do redesign visual (F4)

Estado em 2026-08-01. A **Fatia 24 está pronta e commitada** (tema, vitrine,
27 testes). Este arquivo é o plano das fatias 25 a 30, escrito para ser
executado numa sessão futura sem precisar redescobrir nada.

## Direção definida pelo Rafael (final)

Depois de três rodadas de correção vendo na tela:

- **Fundo branco puro.** Painel e fundo são o mesmo branco; o que separa é uma
  linha de contorno quase invisível mais uma sombra de opacidade baixa.
- **Monocromático de verdade.** Botões, seleção, foco, estados **e o card sem
  miniatura**: tudo em cinza (`theme.ACCENT`, `#4A4A52` — mais claro que a
  primeira tentativa, `#2E2E33`, achada escura demais). Cor não sobrou em
  lugar nenhum da UI de sistema; a cor da tag (dado do usuário) segue como
  está hoje, sem mudança.
- **Uma fonte só** (Inter), com variação apenas de peso (400/600) e de
  tamanho. Títulos mais escuros que o corpo — a hierarquia vem daí, não de cor.
- **Cantos menos arredondados**: 8px no card/controle (`RADII["discreto"]` foi
  de `(14, 12, 9)` para `(10, 8, 6)`; `"marcante"` de `(20, 18, 13)` para
  `(16, 12, 9)`).
- **Reconhecimento do tipo de asset por TEXTO, não por cor** — um chip
  pequeno no canto do card com a extensão (`.fbx`, `.exr`, `.blend`, `.png`),
  estilo Connecter. Ver Fatia 27.
- **Organização inspirada no Connecter Suite** (só o arranjo, não o estilo).

O que morreu no caminho, e por quê: fundo lavanda (pesado), "vidro fosco"
(não há o que filtrar entre dois brancos — e o blur do Qt borra o conteúdo do
próprio widget, não o fundo), seleção em barra sólida colorida (dominava a
tela), tints pastel de baixo contraste (o tipo sumia), tints saturados por
tipo (o Rafael pediu para tirar a cor também daqui — ver abaixo), e **ícone
por tag** (Fatia 29 antiga — descartado, a tag continua só por cor).

## Estado da base (Fatia 24, já no repositório)

- `assetdeck/ui/theme.py` — tokens, paleta, `build_qss()`, `apply_theme()`,
  `contrast_ratio()`, `make_card()`, `apply_card_shadow()`.
- `assetdeck/ui/theme.qss` — folha em arquivo, `$token` via `string.Template`.
- `assetdeck/ui/theme_gallery.py` — `python -m assetdeck --theme-preview`.
- Regra no `CLAUDE.md`: nenhum `setStyleSheet` fora do `theme.py`.

Fatos do Qt já medidos (não re-testar): subclasse de `QWidget` filha ignora
`background` do QSS sem `WA_StyledBackground`; view arredondada vaza no canto,
precisa do `QFrame#card` em volta; `QListView::item` no QSS mata a rolagem;
`url()` precisa de caminho absoluto; `QIcon("x.svg")` funciona sem `.qrc`;
estilizar `QTreeView::branch` faz o Qt voltar ao azul padrão dele.

---

## Fatia 25 — Aplicar o tema à janela principal

**Não mexe no layout** — só veste o que já existe. Reorganização é a 28.

**Tocados:** `app.py` (uma linha: `theme.apply_theme(app)`),
`ui/main_window.py` (`objectName`s, `theme.make_card()` em volta de cada
painel, margens, `#appSurface` no widget central), `ui/details_panel.py`
(`WA_StyledBackground` + remover o `setStyleSheet` inline da L118 → usar
`objectName("multiWarn")`), os 4 painéis laterais e `ui/asset_grid.py`
(`setFrameShape(NoFrame)` + viewport transparente, dentro do card).

Atenção: `setMinimumWidth(300)/setMaximumWidth(380)` do details
(`main_window.py:200-201`) migra para o card, somando o padding.

**Deu certo quando:** o app abre branco, com painéis delimitados por linha
fantasma e sombra, e os cantos arredondados mostram o fundo de verdade.
Grade, arrasto, filtros e ponte com o Blender funcionam igual.
**pytest:** suíte inteira. Novo: `grab()` da janela e conferir que a quina de
um card é branco puro e o meio da aresta tem a linha (mesma técnica de
`test_theme.py::test_o_canto_do_card_e_arredondado`).

---

## Fatia 26 — Ícones SVG

**Novos:** `ui/icons/` (SVGs), `ui/icons.py`, `tests/test_icons.py`.

`icon(nome, cor=None, tam=20) -> QIcon`, carregando por
`Path(__file__).parent / "icons"`, com `lru_cache` e erro logado se faltar.
Recolorização em runtime (`CompositionMode_SourceIn`) para um arquivo servir a
várias cores. Sem `.qrc`, sem passo de build.

**Origem dos SVGs — decisão a tomar:**
- **Recomendado: desenhar à mão.** São ~12 ícones geométricos simples
  (estrela, olho cortado, lupa, seta circular, chevron, check, pasta,
  etiqueta, camadas). Zero dependência, zero licença, zero download — o que
  casa com o "100% offline" do projeto.
- Alternativa: vendorizar um subconjunto de Lucide (ISC) ou Tabler (MIT)
  dentro do repo com o arquivo de licença. São arquivos estáticos, então o
  offline em runtime segue intacto — mas exige baixar uma vez no dev.

**Onde entram:** as 5 estrelas e o `fav_btn` do `details_panel.py`
(hoje `QPushButton("☆")` — **nenhuma fonte da máquina tem o glifo ★**,
conferido com `QRawFont`, e o Qt cai numa substituta que sai torta), a lupa da
busca, o `rescan_btn`, o `✓` branco dentro do checkbox marcado (hoje a caixa é
só preenchida), o chevron do `QComboBox::drop-down`, e um glifo por tipo de
asset para o card sem miniatura.

**Deu certo quando:** as estrelas são nítidas em qualquer escala e nenhum
ícone some no hover ou desabilitado.

---

## Fatia 27 — Delegate dos cards da grade

**Novos:** `ui/asset_card_delegate.py`, `tests/test_asset_card_delegate.py`.
**Tocado:** `ui/asset_grid.py`.

Contrato que **não** muda: `sizeHint()` devolve exatamente `CELL` (176×200);
`uniformItemSizes`, `SinglePass`, `Movement.Static`, `dragEnabled`,
`ScrollPerPixel` e `_stacked_preview()` intactos.

Muda: `DisplayRole` passa a devolver só o nome — o `"★ "` e o `"[oculto] "`
(`asset_grid.py:147-149`) viram papéis novos desenhados como badge (bônus: a
busca-por-digitação do `QListView` volta a funcionar). O delegate pinta card
arredondado (8px, `theme.RADII["discreto"][1]`), miniatura, nome elidido em 2
linhas e badges; seleção em cinza, sem retângulo pontilhado de foco. Card sem
miniatura usa a pastilha única `theme.TYPE_TINT` (não há mais cor por tipo).

**Chip de extensão (pedido do Rafael, estilo Connecter):** todo card — com ou
sem miniatura — ganha um selo pequeno num canto (`theme.TYPE_TINT` a 55% de
opacidade, texto branco, ~9px) com a extensão real do arquivo em maiúsculas:
`.FBX`, `.EXR`, `.BLEND`, `.PNG`. É o reconhecimento do tipo por TEXTO,
substituindo o que a cor fazia antes. Fonte do texto: `Path(row["path"]).suffix`
— já existe no repo, não precisa de coluna nova. Protótipo do chip está em
`theme_gallery.py::_build_palette_sample` (amostra "CARD SEM MINIATURA + CHIP
DE EXTENSÃO"), copiar o padrão de posicionamento de lá para o delegate. Tudo
pré-computado no `__init__` do delegate.

Bug a corrigir junto: a chave do `QPixmapCache` em `_pixmap_for` é
`f"thumb:{key_hash}"` **sem o tamanho** — mudar o tamanho do ícone serve
pixmaps velhos na mesma sessão.

**pytest:** `tests/test_grid_state.py` inteiro e sem alteração é o teste de
regressão (verificado: `movement()==Static` e os 3 testes de rolagem passam,
`scrollbar.maximum()` = 5702).

---

## Fatia 28 — Reorganização estilo Connecter

A maior e a mais arriscada. Hoje a janela é: uma fila de 11 widgets crus de
filtro no topo, e um `QSplitter` horizontal com [4 painéis empilhados] |
grade | detalhes à direita.

**Arranjo alvo, lido das referências do Connecter:**

| Faixa | Hoje | Alvo |
|---|---|---|
| Topo | busca + 10 controles na mesma linha | barra de ferramentas de botões-ícone **com contador embaixo** (tipos, nota, favoritos, resolução, ocultos, dependências) |
| Acima da grade | nada | **caminho navegável** (breadcrumb) da pasta atual + "Ordenar" + filtro por nome |
| Esquerda | 4 painéis de peso igual empilhados | **Pastas** como painel principal; Tags / Coleções / Smart como seções secundárias embaixo, com contador |
| Detalhes | coluna à direita | **faixa inferior em COLUNAS**: Arquivo · Imagem/3D · Tags · Propriedades · Notas |
| Rodapé | barra de status com versão | `391 assets · 3 selecionados` |

**Risco principal:** `tests/test_main_window.py` trava a existência dos
atributos `grid, details, folders, tags, collections, smart_collections,
type_filter, search_box, deps_check, hidden_check, group_check` e os textos
`"Só texturas"` / `"(nenhuma aplicada)"`. Manter os nomes dos atributos mesmo
com os widgets reparentados; se algum controle virar botão-ícone, o teste
correspondente muda junto, com a razão escrita no commit.

**Sugestão de execução:** fatiar em 28a (barra de ferramentas + breadcrumb +
status) e 28b (detalhes para a faixa inferior). O 28b é o que mais mexe em
`details_panel.py` e merece branch própria.

---

## ~~Fatia 29 — Tags com ícone~~ — descartada

Decisão do Rafael: a tag continua identificada só por cor, como hoje
(`ui/tag_tree.py:61-62`). Sem ícone, sem seletor novo, sem migration — a única
fatia deste plano que não vai acontecer.

---

## Fatia 30 — Acabamento

`preview_popup.py` (**se mexer no padding, ajustar `_win_w-40` /
`_win_h-110` junto**, senão `tests/test_preview_popup.py` quebra), os 6
diálogos, `QMenu`/`QToolTip`/`QScrollBar`/`QSplitter::handle` no `theme.qss`.

**Deu certo quando:** abrir todos os diálogos e o menu de contexto da grade
não revela nenhuma "ilha cinza padrão do Qt".

---

## Como retomar

```bash
cd "/home/rafael/00 - PROJETOS/assetdeck" && source .venv/bin/activate
git checkout fatia-24-tema-fundacao   # ou a main, se a 24 já tiver sido mergeada
python -m assetdeck --theme-preview   # confere o ponto de partida
pytest -q                             # 254 verdes
```

Uma fatia por vez, branch própria, pytest verde, e merge na `main` só depois
de o Rafael confirmar na tela.

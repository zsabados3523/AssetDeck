# REDESIGN.md — plano do redesign visual (F4)

Estado em 2026-08-01. A **Fatia 24 está pronta e commitada** (tema, vitrine,
38 testes). Este arquivo é o plano das fatias 25 a 30, escrito para ser
executado numa sessão futura sem precisar redescobrir nada.

## Direção definida pelo Rafael (final)

Depois de duas rodadas de correção vendo na tela:

- **Fundo branco puro.** Painel e fundo são o mesmo branco; o que separa é uma
  linha de contorno quase invisível mais uma sombra de opacidade baixa.
- **Monocromático.** Botões, seleção, foco e estados: só cinza. Cor sobrou em
  dois lugares onde ela CARREGA informação — a cor da tag e o tipo do asset.
- **Uma fonte só** (Inter), com variação apenas de peso (400/600) e de
  tamanho. Títulos mais escuros que o corpo — a hierarquia vem daí, não de cor.
- **Tints por tipo com contraste alto** (fundo médio-escuro, texto branco).
- **Organização inspirada no Connecter Suite** (só o arranjo, não o estilo).

O que morreu no caminho, e por quê: fundo lavanda (pesado), "vidro fosco"
(não há o que filtrar entre dois brancos — e o blur do Qt borra o conteúdo do
próprio widget, não o fundo), seleção em barra sólida colorida (dominava a
tela), tints pastel de baixo contraste (o tipo sumia).

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
arredondado, miniatura, nome elidido em 2 linhas e badges; seleção em cinza,
sem retângulo pontilhado de foco. Card sem miniatura usa `theme.TYPE_TINTS` +
o glifo do tipo (Fatia 26). Tudo pré-computado no `__init__`.

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

## Fatia 29 — Tags com ícone ⚠️ MEXE NO BANCO

**Precisa da autorização do Rafael antes de começar** (regra do `CLAUDE.md`).

**Migration 006:** `ALTER TABLE tags ADD COLUMN icon TEXT` (nulo = usa a cor,
como hoje — nada quebra e nada precisa ser migrado). Atualizar `SCHEMA.md`.

`ui/tag_dialogs.py` ganha um seletor de ícone ao lado do seletor de cor;
`ui/tag_tree.py` desenha o ícone quando existir, senão o quadradinho de cor de
hoje (`tag_tree.py:61-62`). O sidecar já espelha tags — conferir se o campo
novo acompanha, senão o ícone se perde ao apagar o banco.

Para o seletor valer a pena são precisos ~24 ícones genéricos (madeira, tijolo,
metal, tecido, planta, pedra, vidro, água, luz…). É aqui que vendorizar um
conjunto pronto compensa mais do que desenhar à mão.

**Se ficar caro, não faça:** o Rafael disse explicitamente "somente se possível
e se não for muito trabalho à toa, senão deixa cor mesmo".

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

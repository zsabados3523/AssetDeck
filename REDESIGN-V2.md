# REDESIGN-V2.md — overhaul visual completo (CONCLUÍDO)

**Status: fechado em 2026-08-04.** As sete fatias (43 a 50) estão todas na
`main`, confirmadas na tela pelo Rafael. Este documento fica como registro —
não é mais handoff de trabalho em aberto. Se uma sessão nova for mexer no
visual do AssetDeck de novo, é um pedido NOVO, não uma continuação deste.

A versão anterior deste arquivo era o handoff da Fatia 43, escrito quando
ainda não havia direção escolhida. **As decisões abaixo estão fechadas — não
pergunte de novo**, a menos que o Rafael peça uma mudança de direção.

## Decisões fechadas (o Rafael escolheu olhando mockups)

O que funcionou: montar a JANELA INTEIRA em HTML, em direções diferentes, e
deixar ele escolher olhando. Perguntar em abstrato ("você quer cor de
destaque?") foi o erro da Fatia 43 — ele vetou cor no abstrato e escolheu
azul em dez segundos vendo quatro botões lado a lado.

| Decisão | Escolha |
|---|---|
| Direção geral | Híbrida: lateral da ref. 1, topo/biblioteca da ref. 3, rodapé da ref. 2 |
| Cor de destaque | **Azul.** `#2A63CF` no claro, `#4D8DFF` no escuro |
| Base padrão | **Escura** |
| Barra de categorias | **Os 6 ícones ficam** — ele os considera mais intuitivos que dropdown |
| Variante da barra | **V3**: ícone + contador sempre; rótulo só na categoria ativa |
| Régua do topo | **Duas linhas**: navegação/caminho numa fina, categorias na outra |
| Filtros finos | Nota/Resolução/Cor/Nome saem da régua e vão pro cabeçalho da lista, à direita |

Mockups em HTML (fora do repo, some com a sessão): a página final tinha as
duas bases lado a lado. Se precisar de novo, remonte — o custo é baixo e o
retorno foi alto.

## Fatias

1. **Fatia 44 — fundação do tema.** FEITA, mergeada na `main` (`68023ef`).
   Azul, superfícies em camadas, `TYPE_TINT` desacoplado do accent, três
   `#FFFFFF` cravados no QSS viraram token.
2. **Fatia 45 — lateral.** FEITA, commit `3da06f9` na branch
   `fatia-45-lateral`. Confirmada na tela pelo Rafael, **falta mergear**.
   Rail de ícones, contador por seção, seções recolhíveis.
3. **Fatia 46 — topo + filtros.** PRÓXIMA. Régua em duas linhas, categorias
   em V3, filtros finos migrando pro cabeçalho da lista.
4. **Fatia 47 — card da grade e estados.**
5. **Fatia 48 — painel de detalhes.**
6. **Fatia 49 — rodapé informativo.** FEITA. LED do Blender, tamanho da
   biblioteca. Nela apareceu o bug do `QFrame#card` (ver abaixo).
7. **Fatia 50 — barra superior e card sem moldura.** FEITA. Nasceu porque o
   Rafael reparou que o topo e a grade não tinham mudado: meu recorte das
   fatias 46 e 47 cobriu só a régua de filtros e os estados do card, e eu não
   avisei que estava deixando o resto do mockup de fora. **Lição: ao fatiar,
   diga explicitamente o que a fatia NÃO cobre.**

Todas as sete mergeadas na `main` em 2026-08-04 (commits até `6cc8ec8`).
709 testes verdes na última rodada da suíte inteira.

## Decisões tomadas DEPOIS dos mockups

- **As abas do mockup foram descartadas** (Biblioteca / Coleções /
  Duplicados). Elas não correspondem a telas do AssetDeck: Coleções é seção
  da lateral e Duplicados é diálogo de Ferramentas. Abas que só abrissem
  diálogos prometeriam uma navegação que não existe. Ficou a marca à esquerda
  e o contexto à direita, na mesma faixa dos menus, via `setCornerWidget`.
- **Não foram feitos, por escolha do Rafael:** a linha de metadados sob o
  nome do card (`HDRI · 4096×2048`) e o card hero da pasta. Ambos continuam
  possíveis; a resolução existe em `files.width/height`. Não são pendência —
  são escopo que ficou fora de propósito. Se o Rafael quiser depois, é pedido
  novo, não fatia esquecida.

## O que NÃO foi tocado neste overhaul

Fora do escopo das 7 fatias, de propósito: os diálogos (batch rename,
duplicados, propriedades, templates de tag) continuam com a aparência de
antes da Fatia 43 — só herdam a paleta nova via QSS global, não receberam
nenhum ajuste de layout. Se algum ficar estranho com o tema novo (contraste,
espaçamento), é fatia própria, não bug desta.

## Coisas que custaram tempo — não redescubra

- **Modo escuro já existia** desde a Fatia 43 e funciona. A Fatia 44 só
  rebaseou as cores.
- **Widgets que pintam cor em Python não passam pelo QSS.** Todo widget novo
  que tinge ícone precisa de `refresh_theme()` e de entrar em
  `MainWindow._refresh_theme_dependent_widgets()`. Hoje estão na lista:
  `AssetCardDelegate`, `AssetGridModel`, `FilterButton`, `CategoryBar`,
  `DetailsPanel`, `Sidebar`.
- **Luminância relativa satura perto do preto.** Para medir se dois tons
  escuros formam um degrau visível, use `contrast_ratio()`, não a diferença
  de luminância — ver `DEGRAU_MINIMO` em `tests/test_theme.py`.
- **`grab()` de um widget isolado não mostra o fundo do app**, mostra o
  preenchimento do pixmap. Um teste de canto arredondado precisa grabar a
  JANELA. O teste antigo comparava branco com branco e teria passado com o
  card quadrado.
- **Contador de lista não deve depender de quem chama `reload()`.** Ligue no
  modelo da view (`rowsInserted`/`rowsRemoved`/`modelReset`/`layoutChanged`).
- **Largura mínima de painel deve ser derivada do conteúdo**, não cravada:
  "SMART COLLECTIONS" pede ~219px e o `200` mágico cortava no meio da palavra.
- **`--screenshot` NÃO serve para conferir sombra nem efeito gráfico.** Ele
  usa `win.grab()`, que repinta o widget e não passa pelo compositor. O
  painel de detalhes ficou sem fundo por várias fatias sem aparecer em
  nenhuma captura. Para ver o que o Rafael vê, abra o app e capture a TELA:
  `QApplication.primaryScreen().grabWindow(0)`.
- **`QFrame#card` não casa com o DetailsPanel**, que é um QWidget. Seletor de
  tema deve ser `#card`, sem o tipo. Ficou escondido enquanto `bg` e
  `surface` eram a mesma cor.
- **`setCornerWidget` não transfere a posse no PySide.** O widget é coletado
  quando a função retorna e o canto volta a ficar vazio — guarde a
  referência em `self`. Vale para qualquer widget entregue ao Qt por um
  setter que a documentação diz "takes ownership".
- **Screenshot headless é a ferramenta que destrava tudo:**
  `QT_QPA_PLATFORM=offscreen python -m assetdeck --screenshot /tmp/x.png
  --screenshot-delay 3000`, depois recortar/ampliar com PIL. Use SEMPRE antes
  de dizer que ficou bom.
- **Para ver o modo escuro sem mexer no config do Rafael**, copie a config
  real para uma pasta temporária, troque só `theme_mode`, e rode com
  `ASSETDECK_CONFIG_DIR` apontando pra lá. O `config.json` dele tem
  `theme_mode: "claro"` gravado desde a Fatia 43, e valor gravado ganha do
  padrão novo.

## Regras do projeto que continuam valendo

- **Nenhum `setStyleSheet` fora de `ui/theme.py`.** Cor/raio/fonte novos
  entram como token lá e viram `$nome` no `ui/theme.qss`. Há um teste
  proibindo cor literal no QSS.
- Biblioteca de teste é `/home/rafael/00 - PROJETOS/assetdeck-testlib`.
- `pytest -q` verde antes de dizer que terminou (~3,5 min hoje, 684 testes).
- Uma fatia por vez, branch própria; **merge na `main` só depois do Rafael
  confirmar na tela**.
- Rafael não programa: explique cada comando antes, e execute você mesmo.
- Testes que travam o visual e não podem ser enfraquecidos: contraste WCAG
  em `tests/test_theme.py` (claro E escuro), teste de PIXEL do canto
  arredondado do card, `tests/test_grid_state.py` (rolagem).

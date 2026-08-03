# REDESIGN-V2.md — overhaul visual completo (Fatia 43b)

Documento de handoff, escrito em 2026-08-03 no fim de uma sessão longa.
A Fatia 43 entregou MENOS do que o Rafael esperava; esta é a continuação,
pra ser executada numa sessão nova com contexto limpo.

## O que aconteceu (leia antes de tudo)

O Rafael pediu "overhaul visual" e mandou **3 referências** (imagens). Eu
perguntei em abstrato se ele queria cor de destaque e modo escuro; ele
respondeu "mantém monocromático" + "quero modo escuro". Entreguei a
Fatia 43 nesse escopo: modo escuro real, barra do breadcrumb
reorganizada, bug de layout corrigido, cantos/sombra mais generosos.

**Ele viu e disse que esperava um overhaul COMPLETO da UI** — janelas,
botões, o visual inteiro, seguindo as referências. Palavras dele numa
mensagem anterior: o programa ainda tem "visual de IA", não passa "cara
de profissional".

**Erro a não repetir:** perguntar "você quer X?" em abstrato. O jeito que
funcionou nesta sessão (barra do breadcrumb) foi **desenhar 2-3 mockups e
pedir pra ele escolher olhando**. Faça isso pro visual inteiro ANTES de
escrever código — inclusive pra cor de destaque, que ele já vetou uma vez
no abstrato mas cujas 3 referências TÊM.

## As 3 referências (peça pro Rafael reanexar as imagens)

As imagens não sobrevivem à troca de sessão. **Peça pra ele mandar de
novo no começo.** Descrição do que eu vi, pra você saber o que procurar:

1. **DAM claro (parece Strapi Media Library)** — fundo branco/quase
   branco, **destaque roxo/violeta** (botão "Upload asset" roxo sólido,
   checkbox de seleção roxo). Barra lateral esquerda com uma coluna
   ESTREITA de ícones + uma coluna de navegação ("Custom views" /
   "Default views" → All, Images, Videos, Documents, Others). Topo com
   filtros em pílula ("title is [valor] ×", botão "+", "Clear all"),
   "Select all", "Sort by:". Cards de asset com miniatura grande, nome
   embaixo, checkbox no canto ao passar o mouse. Rodapé com paginação
   ("50 entries", "Page 1 of 2", "Show 50").

2. **MuseDAM** — **modo escuro**, destaque azul. Barra lateral com
   contadores por seção ("All materials 5581", "uncategorized 1851",
   "recycle bin 18"), seções "Smart Labels (4)" e "Labels (10)" com
   itens `# nome  contagem`. Topo com filtros como DROPDOWNS ROTULADOS
   com ícone + texto ("color ▾", "type ▾", "Label ▾", "creation time ▾",
   "sort ▾", "adaptive"), slider de tamanho e um toggle "dark mode"
   visível. Grid de cards mostrando MOSAICO de várias miniaturas por
   card + nome + "N items". Rodapé com uso de armazenamento
   ("19.83GB / 1TB") e status de plugin.

3. **TextureLibrary** — **quase preto**, destaque azul. Barra de
   navegação superior com abas (Discover / **Library** / Pricing /
   Community) e logo. Lateral com árvore expansível (Everything, Realism
   → Asphalt/Bricks/Concrete/Marble..., Atlases, Collections,
   Downloads, Favorites, Free, Stylized) — item ativo com barra vertical
   à esquerda. Linha de filtros com ícone+texto ("Material type ▾",
   "Composition ▾", "Characteristics ▾", "Solid / Pattern ▾")
   separados por divisores verticais. Card "hero" grande no topo com
   imagem de fundo, título e descrição. Seção "Featured" com subtítulo.
   Card selecionado com borda azul.

**O que as 3 têm e o AssetDeck não tem** (é isto que "overhaul" quer
dizer, na prática):
- Cor de destaque de verdade (roxo numa, azul em duas).
- Filtros como **dropdown rotulado com ícone + texto**, não botão só de
  ícone. Hoje o AssetDeck tem 6 ícones sem rótulo + 3 ícones de filtro,
  e você não sabe o que cada um faz sem passar o mouse.
- Hierarquia clara na lateral: seções com **contador**, item ativo
  marcado, agrupamento visual — hoje são 4 cards empilhados iguais.
- Cards com mais respiro, raio maior, estado de hover/seleção evidente.
- Rodapé informativo (armazenamento, contagem, status) em vez de só
  "391 assets".
- Um "primeiro plano" claro: as 3 têm um elemento âncora no topo (botão
  primário forte, abas, ou hero card).

## Estado do código (2026-08-03)

- Branch `fatia-43-overhaul-visual`, commit `870fa22`, **não mergeada**
  (espera o OK do Rafael). `main` está em `49428bb`.
- 650 testes verdes.
- **Modo escuro JÁ EXISTE e funciona** — não refaça. `theme.py` tem
  `_PALETA_CLARA`/`_PALETA_ESCURA`, `Variant.mode`, `current_colors()`,
  toggle no menu Configurações persistido em `config.json: theme_mode`.
  A paleta escura foi calibrada por fórmula WCAG, **nunca vista na tela
  pelo Rafael** — provavelmente precisa de ajuste fino de gosto.
- Armadilha já descoberta e resolvida (não redescubra): vários widgets
  pintam cor direto em Python (delegate da grade, ícones pré-tingidos) e
  NÃO passam pelo QSS. Existe `theme.current_colors()` + `refresh_theme()`
  em `AssetCardDelegate`, `AssetGridModel`, `FilterButton`, `CategoryBar`,
  `DetailsPanel`, orquestrados por
  `MainWindow._refresh_theme_dependent_widgets()`. Qualquer widget novo
  que pinte cor à mão precisa entrar nessa lista.
- `theme_gallery.py` (`python -m assetdeck --theme-preview`) é a vitrine
  ao vivo: 5 combos (fundo/separação/cantos/fonte/modo). É o lugar certo
  pra calibrar cor COM o Rafael olhando. Trocar tema ao vivo é só chamar
  `theme.apply_theme(app, variant)` de novo.

## Como conduzir (o processo importa mais que o plano)

1. **Peça as 3 imagens de novo.** Sem elas você está adivinhando.
2. **Mockups primeiro, código depois.** Monte 2-3 telas inteiras de
   AssetDeck em HTML (não widget solto: a janela toda — lateral, topo,
   grid, detalhes, rodapé) em direções diferentes, e deixe ele escolher.
   Foi assim que a barra do breadcrumb saiu boa nesta sessão.
3. **Pergunte de novo sobre cor de destaque, mas MOSTRANDO.** Ele vetou
   no abstrato; as referências dele têm cor. Uma opção monocromática e
   uma com destaque, lado a lado, resolve isso em 10 segundos.
4. **Fatie.** Isto é grande demais pra um commit só. Sugestão de corte:
   (a) fundação do tema (paleta/tokens/raios/espaçamento);
   (b) barra lateral (hierarquia, contadores, item ativo);
   (c) topo + filtros (dropdown rotulado em vez de ícone mudo);
   (d) card da grade + estados;
   (e) painel de detalhes;
   (f) diálogos e acabamento.
   Uma por vez, com screenshot pra ele a cada uma.
5. **Screenshot headless funciona bem** e foi o que destravou esta
   sessão: `QT_QPA_PLATFORM=offscreen python -m assetdeck --screenshot
   /tmp/x.png --screenshot-delay 3000`, depois recortar/ampliar com PIL
   pra olhar detalhe. Use SEMPRE antes de dizer que ficou bom.

## Regras do projeto que continuam valendo

- **Nenhum `setStyleSheet` fora de `ui/theme.py`.** Cor/raio/fonte novos
  entram como token lá e viram `$nome` no `ui/theme.qss`.
- Biblioteca de teste é `/home/rafael/00 - PROJETOS/assetdeck-testlib`.
  Nunca aponte pra outro caminho.
- `pytest -q` verde antes de dizer que terminou (~3 min hoje).
- Uma fatia por vez, branch própria, commit só no fim; **merge na `main`
  só depois do Rafael confirmar na tela**.
- Rafael não programa: explique cada comando antes, e execute você mesmo.
- Testes que travam o visual e não podem ser enfraquecidos: contraste
  WCAG em `tests/test_theme.py` (claro E escuro), teste de PIXEL do
  canto arredondado do card, `tests/test_grid_state.py` (rolagem).

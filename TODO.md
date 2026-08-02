# TODO.md — Roadmap e estado atual

## Marco: Alpha 1.0 (2026-08-02)

Estado atual marcado como **Alpha 1.0** — tag Git anotada `alpha-1.0` sobre
o commit `d6f7135` da `main`. F0-F4 completos, tema Craft aplicado,
executável no menu do Zorin, bugs de tags recriadas e ícone do app
corrigidos nesta sessão. Testado uma vez contra a biblioteca real do
Rafael (650GB, ~72 mil arquivos, sem erros graves — ver sessão de
2026-08-02) e depois desanexada de novo a pedido dele; app voltou a
apontar para a testlib para a próxima fase de desenvolvimento.

Próxima fase: **F5 — v2.0**, roadmap fechado com o Rafael em 2026-08-02
(14 fatias, 31 a 44 — ver seção própria abaixo). Começando pela Fatia 31.

## Estado atual (2026-08-02)

**F0, F1, F2 e F3 completos.** **F4 (redesign visual) completo e mergeado
na `main`**, confirmado pelo Rafael na tela.

| | |
|---|---|
| Testes | 308 verdes (`pytest -q`) |
| Schema | migrations 001–005 aplicadas (ver SCHEMA.md) |
| Biblioteca de trabalho | testlib: 750 arquivos → 391 assets → **127 visíveis** (dependências ocultas) |
| Add-on do Blender | v0.4.0, Blender 5.2 Flatpak |
| Tema visual | claro estilo Craft, monocromático — ver F4 abaixo |

Próximo item já com direção definida: **executável / entrada no menu de
aplicativos do Zorin** (F4, mais abaixo, ✅ concluído). O resto da F4 ainda
não tem direção (auto-tagging, checagem seamless, etc.) — decisão do
Rafael, agora em levantamento para o roadmap pós-Alpha 1.0.

## Como ler este arquivo
Uma fatia por vez, em branch própria. Cada fatia termina com: pytest verde,
critério de "deu certo" verificado pelo Rafael na tela, e commit. O merge na
`main` só acontece depois que ele confirma que rodou.

---

## F0 — MVP ✅

- **☑ Fatia 1 — Esqueleto vivo.** Pacote, config XDG, logging, schema v1
  completo como migration 001, backup rotativo do .db, janela, `--screenshot`.
- **☑ Fatia 2 — Indexação em background.** Scanner em thread, idempotente;
  arquivo sumido ganha `missing_since` (nunca é apagado).
- **☑ Fatia 3 — Grid de thumbnails.** Cache em disco por content_hash,
  painel de detalhes, abrir pasta / app padrão. Resgate de PNGs com chunk
  iCCP corrompido e suporte a mapas 16-bit.
- **☑ Fatia 4 — Busca e filtros.** FTS5 (prefixo, sem acentos), árvore de
  pastas, toggle de subpastas, filtro por tipo, **rolagem suave**.

## F1 — Vira útil ✅

- **☑ Fatia 5 — Sidecars JSON + notas.** Espelho `.assetdeck.json` ao lado do
  asset; apagar o banco e reindexar recupera os metadados. Filtro de tipos em
  checklist multi-seleção.
- **☑ Fatia 6 — Agrupamento PBR.** 127 sets criados na testlib; correção
  manual (agrupar/desagrupar) travada contra o agrupador — **migration 002**
  (`group_locked`). Preview ampliado por duplo clique.
- **☑ Fatia 7 — Thumbs especiais.** HDR/EXR tonemapados (Reinhard + gamma),
  fit correto da grid, toggle "Agrupar sets PBR", PBR Material Viewer.
- **☑ Fatia 8 — Tags.** Hierarquia N níveis, cor, aliases PT/EN ("madeira"
  acha "wood"), 3 formas de taggear, copiar/colar/substituir. Cutouts com
  transparência real.
- **☑ Fatia 9 — Ratings, favoritos, filtros combinados.** Edição em massa:
  tag/nota/favorito valem para todos os assets selecionados.
- **☑ Fatia 10 — Previews customizados.** Arrastar imagem externa define a
  capa; galeria 1:N com capa e soft delete.
- **☑ Fatia 10b — Preview interno.** Arrastar um asset de imagem sobre um
  modelo vira a capa dele, com diálogo "ocultar a origem?" e memória da
  escolha — **migration 003** (`hidden`), reversível via "Mostrar ocultos".

## F2 — Blender ✅

- **☑ Fatia 11 — Ponte + add-on.** Socket só em 127.0.0.1 com token,
  QTcpServer assíncrono, add-on instalado pelo próprio AssetDeck.
- **☑ Fatia 12 — Material PBR + previews no add-on.** Node group fechado com
  colorspaces corretos, AO no mix, displacement; miniaturas dentro do Blender.
- **☑ Fatia 13 — AssetDeck vira a origem do arrasto.** Arrastar da grid para
  o Blender aciona o menu nativo dele. Detecção de **dependências**
  (texturas que acompanham um .blend irmão) — **migration 004**
  (`is_dependency`) — e capas automáticas de `*_Preview1.png` dos packs.
- **☑ Fatia 14 — Import estilo Connecter.** Append/Link por tipo com
  "& Place". Correções: rolagem da grade e capa no modo expandido.
- **☑ Fatia 15 — Submenus + rolagem (de vez).** Causa real: layout em lotes
  descobria o tamanho da lista tarde demais → trocado para SinglePass.
- **☑ Fatia 16 — Capas por render + salvar na biblioteca.** Render headless
  com enquadramento automático e **relocalização de texturas** (packs
  Maxtree vêm com caminhos quebrados); salvar seleção da cena de volta, com
  rescan automático.

---

## F3 — Power user (a fazer)

### ☑ Fatia 17 — Collections manuais
As tabelas `collections` e `collection_items` existem desde o schema v1 e
ganharam UI: painel lateral (junto de pastas e tags), criar / renomear /
excluir, arrastar assets para dentro, subpastas de coleção, ordem manual.
**Reusa:** `ui/tag_tree.py` (o drag-and-drop com `MIME_ASSETS`) e
`db/repos/tags.py` (hierarquia, soft delete, `descendants`).
**Nota de processo (2026-08-02):** checkbox ficou desatualizado — o Rafael
confirmou que esta fatia já estava implementada quando as Fatias 17b/18/19
(que dependem dela) foram feitas; só o `☐` não tinha sido corrigido.

### ☑ Fatia 17b — Preview agrupado ao arrastar múltiplos assets
Feedback do Rafael depois de usar a Fatia 17: arrastando vários assets
espalhados pela grade para uma coleção, o Qt desenhava cada miniatura na
posição relativa original, ficando com espaçamento esquisito. Trocado por
um preview compacto tipo "baralho de cartas" (miniaturas empilhadas + selo
com o total) que acompanha o cursor pelo centro. Só entra em 2+ itens
selecionados; 1 item continua com o comportamento padrão do Qt.
**Deu certo quando:** selecionar 3+ assets distantes na grade e arrastar
até uma coleção mostra um bloco compacto seguindo o mouse, e soltar ainda
adiciona todos à coleção.

### ☑ Fatia 18 — Smart Collections
Tabela `smart_collections` (`query_json`), sem migration nova. Painel
"Smart Collections" (lista achatada, sem hierarquia): "Salvar filtros
atuais…" serializa o mesmo dicionário que `_apply_filters()` já monta para
`assets_repo.list_for_grid`; aplicar uma delas reescreve os widgets da
barra (busca, tipos, pastas, tag, coleção, nota, favoritos, resolução,
ocultos, dependências) e reaplica — a reatividade que já existia (nota,
reindexação) mantém a visão sempre recalculada, sem código extra.
**Deu certo quando:** salvar "HDRIs com nota ≥ 4" e ela se atualizar sozinha
ao dar 5 estrelas a um HDRI novo.

### ☑ Fatia 19 — Relocalizar assets perdidos
`indexer/relocator.py` escrito: casa arquivos `missing_since` com arquivos
ativos de mesmo `content_hash` em outro caminho (assets de 1 arquivo só,
dos dois lados). Menu "Biblioteca → Relocalizar assets perdidos…" mostra os
pares para o Rafael revisar antes de aplicar — nunca fusão automática
silenciosa. Aplicar funde o duplicado que a varredura criou de volta no
asset original (mesmo padrão de `indexer/grouper.py`): uuid, tags, nota e
favorito sobrevivem; o duplicado leva soft delete.
**Deu certo quando:** mover um arquivo indexado para outra subpasta,
reindexar, religar pelo menu e ver o asset original (com a mesma
tag/nota de antes) apontando pro caminho novo, sem sobrar um asset
fantasma duplicado na grid.

### ☑ Fatia 19b — Bug: card fica preso onde o mouse soltou
**Primeiro diagnóstico meu estava ERRADO** (achei que era um "fantasma" de
repaint). O Rafael corrigiu a descrição: o preview do próprio asset É
MOVIDO e fica preso, estático, onde soltou. Isso é o Qt movendo o item de
verdade.

**Causa raiz:** `setViewMode(IconMode)` liga `Movement.Free` por padrão, e
em `Free` o `QIconModeViewBase` deixa o usuário reposicionar os ícones e
guarda a posição de cada um. Verificado rodando o Qt do projeto:
`QListView()` novo = `Static`; após `setViewMode(IconMode)` = **`Free`**.
Fix: `self.setMovement(QListView.Movement.Static)` — a grade é sempre
ordenada pela consulta, nunca houve reordenar à mão. Confirmado que o
layout em grade fica idêntico e `dragEnabled` continua `True` (arrastar
para tag/coleção/Blender não regride).

Mantido também o fix anterior como defesa em profundidade: `dropEvent` faz
`event.ignore()` + `viewport().update()` em vez de cair no
`super().dropEvent()` (caminho morto, sem `InternalMove`), e o `startDrag`
customizado força repaint após o `drag.exec(...)`.

Teste de regressão em `tests/test_grid_state.py` trava a CONFIGURAÇÃO
(`movement() == Static`) — provei que ele falha sem o fix. Um teste do
comportamento (simular drop e comparar `visualRect`) não é possível: o
`filterDropEvent` do Qt exige um `QDrag` real como `event.source()` e
derruba o processo se for forjado.
**Deu certo quando:** arrastar um asset e soltar em espaço vazio da própria
grade faz o card voltar pro lugar dele, sem ficar preso onde soltou.

### ☑ Fix — Smart Collection "(nenhuma aplicada)" não resetava os filtros
Relatado pelo Rafael: voltar pro item raiz do painel de Smart Collections
deixava os filtros da coleção anterior (tipo, nota, etc.) parados, em vez
de mostrar tudo de novo. `_on_smart_collection_selected` só dava `return`
quando `smart_id` era `None`; agora chama `_restore_filters({})` — reusa a
mesma função da Fatia 18, que já cai no "mostrar tudo" quando a chave não
existe no dicionário.
**Deu certo quando:** aplicar uma Smart Collection e depois clicar em
"(nenhuma aplicada)" mostra a biblioteca inteira de novo, sem filtro
nenhum sobrando.
**Nota de processo:** o Rafael reportou que este fix "não funcionou", mas a
causa foi minha — deixei o repo na branch `fatia-23-batch-rename`, que saiu
da `main` ANTES deste commit, então ele testou um código sem o fix. Lição:
consolidar tudo numa branch só antes de pedir teste.

### ✕ Decidido — mover asset para outra categoria arrastando
Avaliado e descartado (2026-08-01): o Rafael confirmou que a Tag/Collection
já resolve reclassificar dentro do app, e que mover ARQUIVO físico de
verdade fica por conta do gerenciador de arquivos do sistema — mantém o
"somente-leitura" como está, sem exceção nova além da Fatia 23 (Batch
rename, já prevista). Não vira fatia.

### ☑ Fatia 20 — Duplicados por perceptual hash
**Migration 005** (`files.phash`) — dHash de 64 bits, só para arquivos
raster, calculado na mesma abertura de imagem que já lê width/height
(`scanner.image_meta`, sem ler o arquivo duas vezes; sem dependência nova,
só Pillow). `indexer/duplicates.py` agrupa assets ativos e visíveis com o
mesmo phash. Menu "Biblioteca → Duplicados por conteúdo visual…" lista os
grupos e deixa o Rafael escolher o que ocultar — **nunca apaga nada**, usa
`assets.hidden` (Fatia 10b), reversível em "Mostrar ocultos".
**Deu certo quando:** duas cópias da mesma textura em resoluções diferentes
aparecem no mesmo grupo; ocultar uma some da grade padrão sem apagar nada
do disco nem do banco.

### ☑ Fatia 21 — Busca booleana + substring
Sem migration — `AND`/`OR`/`NOT` já são nativos do FTS5 e funcionam com o
tokenizer de hoje (confirmado testando direto no SQLite do projeto);
`_fts_query` só traduz E/OU/NÃO pra eles. Pra "quartzite" achar
"StoneQuartziteTile" (limitação da Fatia 12), acrescentado um `LIKE
'%termo%'` em `assets.name` como reforço (OR) do FTS — só ativa quando a
busca não tem conector, pra não confundir com a lógica booleana. Testado
com dado real: "quartzite" agora acha `Poliigon_StoneQuartziteTile_8607`
na testlib. Cogitei trocar o tokenizer pra `trigram` (resolveria sozinho)
mas descartei: quebra a insensibilidade a acento e termos curtos como
"4k"/"2k" (comuns em nome de textura) nunca batem com só 2 caracteres.
**Deu certo quando:** buscar "quartzite" acha o pack Poliigon mesmo sem
espaço no nome; "concreto E rustico" / "OU" / "NÃO" filtram como esperado;
buscas antigas (prefixo, "4k", sem acento) continuam iguais.

### ☑ Fatia 22 — Custom properties na UI
Sem migration — `property_defs`/`property_values` já existem desde o v1.
Painel de detalhes ganhou a seção "Propriedades:" (`db/repos/properties.py`
+ `ui/property_defs_dialog.py` pra criar/renomear/excluir a definição, tipo
text/number/bool/date). Fechei também um buraco que já estava documentado:
`assets_repo.get_bundle` tinha `"custom": {}` sempre vazio com o comentário
"EAV na UI chega no F3" — agora popula de verdade, e
`sidecar/reader.py`/`indexer/scanner.py` restauram `custom` do sidecar
(mesmo padrão que já existia pra tags), então propriedades sobrevivem a
apagar o banco. Cuidado com o schema: `property_defs.name` tem `UNIQUE`
incondicional (não só entre ativas) — `create_def` revive uma definição
soft-deleted em vez de tentar inserir de novo.
**Deu certo quando:** criar "Fornecedor" (texto), preencher num asset,
trocar de asset e voltar (valor ficou só naquele), apagar o banco e
reindexar (propriedade e valor voltam via sidecar).

### ☑ Fatia 23 — Batch rename
**A única exceção ao somente-leitura.** Perguntei o formato ao Rafael antes
de programar (não tinha spec). Escolhido: busca-e-substituição no NOME do
arquivo (não mexe no campo "Nome" do banco — fica pra outra hora),
aplicada a TODOS os arquivos do asset selecionado (um set PBR de 6 mapas
troca os 6 juntos, preservando o que não bate, tipo "_basecolor").
`assetdeck/batch_rename.py` — na raiz do pacote de propósito, é a única
operação que escreve fora de sidecars: `build_plan`/`find_conflicts` (só
leitura, prévia ao vivo no diálogo) e `apply_plan` (só depois de confirmar
explicitamente); sidecar do arquivo renomeado acompanha; item problemático
falha sozinho sem derrubar o lote. Menu de contexto da grid → "Renomear em
lote…".
**Deu certo quando:** selecionar 2-3 assets, trocar um pedaço do nome, ver
a prévia, confirmar, e os arquivos mudarem de nome no disco de verdade,
sem sobrar nada quebrado na grade.

## F4 — Em andamento

Dois itens abaixo já têm direção definida (pedido do Rafael em
2026-08-01); o resto da lista ainda não foi fatiado.

**Escolhas do Rafael para o redesign (2026-08-01):** destaque
**azul-petróleo**, fundo **cor lisa**, e a ordem "tema global primeiro, cards
da grade depois". Fatiado em 24 → 28.

**Correção de rumo (mesmo dia):** a primeira tentativa usou fundo lavanda e o
Rafael reprovou vendo na tela — ficou pesado. Direção nova, olhando a
referência do Craft de novo: **fundo SEM cor** (cinza claríssimo), cartões
**brancos** flutuando com sombra discreta, contorno quase invisível, e cor só
em detalhe pequeno. Consequências: o "vidro fosco" saiu de cena (não há nada
atrás para filtrar num esquema branco-sobre-cinza), a seleção virou pastilha
clara com texto na cor (a barra sólida de petróleo dominava a tela), e as
cores por tipo de asset viraram pastilhas claras com texto escuro em vez de
blocos chapados com texto branco.

### ☑ Fatia 24 — Fundação do tema + vitrine
`ui/theme.py` (tokens de cor/raio/fonte, paleta, contraste WCAG),
`ui/theme.qss` (template com `$token`, lido do disco) e `ui/theme_gallery.py`,
aberta por `python -m assetdeck --theme-preview`. **Não toca no app** — existe
para o Rafael escolher na tela (fundo liso × com grão, 3 níveis de
translucidez, 2 raios, Inter × fonte do sistema) antes de aplicar.

Regra nova do projeto: **nenhum `setStyleSheet` fora do `theme.py`.**

Decisões forçadas pelo que o Qt realmente faz (medido, não presumido):
- **Blur de verdade não existe aqui de qualquer jeito.**
  `QGraphicsBlurEffect` borra o conteúdo do PRÓPRIO widget (borraria as
  miniaturas), e o Mutter não implementa blur atrás da janela. O visual não
  depende disso: cartão branco separado do fundo por sombra.
- **Subclasse de `QWidget` filha ignora `background` do QSS** sem
  `WA_StyledBackground` (pega o `DetailsPanel` na Fatia 25).
- **Seleção da árvore é barra de linha inteira, não pílula arredondada:** a
  coluna do indicador de expandir é pintada quadrada pelo estilo e fica um
  degrau ao lado do item arredondado. Estilizar `QTreeView::branch` para
  corrigir é pior — o Qt volta a pintar a seleção com o azul padrão dele.
- **Caixa de checkbox ganhou borda explícita** (exceção consciente à regra de
  não estilizar subcontrole): com a paleta clara, o indicador do Fusion usa a
  cor de botão e a caixa DESMARCADA ficava invisível. O "✓" branco entra na 26.
- **Nenhuma fonte da máquina tem o glifo ★** (conferido com `QRawFont`) — o Qt
  cai numa substituta e o desenho sai torto. É a justificativa da Fatia 26.
- Barra de progresso ficou fina e sem texto: a porcentagem escrita por cima do
  trecho preenchido dá 2,4:1 de contraste contra o petróleo.

**Deu certo quando:** `python -m assetdeck --theme-preview` abre e o Rafael
aponta na tela qual fundo, translucidez, raio e fonte valem. 23 testes novos
(239 na suíte), incluindo teste de PIXEL — o Qt descarta regra de QSS com erro
de sintaxe em silêncio, então só ler a cor do pixel prova que a folha pegou.

### Fatias 25 a 30 — ver **REDESIGN.md**
O plano detalhado do resto do redesign saiu deste arquivo e virou um documento
próprio (`REDESIGN.md`), escrito para ser executado numa sessão futura sem
redescobrir nada: 25 aplicar o tema · 26 ícones SVG · 27 delegate dos cards ·
28 reorganização estilo Connecter · 29 tags com ícone (**mexe no banco, precisa
de autorização**) · 30 acabamento.

### ☑ Redesign visual (F4) — Fatias 24 a 28 + 3 rodadas de correção, mergeado na main
Tema claro estilo Craft: fundo branco liso, cartões brancos separados por
contorno quase invisível + sombra discreta, monocromático (cor só em tag e
chip de extensão), cantos arredondados nos cards e em menus (não em
diálogos — eles têm barra de título do gerenciador de janelas, arredondar
por baixo dela deixa costura feia, testado e revertido).

- **24** — `ui/theme.py`/`theme.qss`/`theme_gallery.py`, vitrine em
  `--theme-preview`. Regra nova: nenhum `setStyleSheet` fora de `theme.py`.
- **25** — tema aplicado na janela real (cartões, sombra, WA_StyledBackground).
- **26** — 8 ícones SVG desenhados à mão (estrelas, lupa, refresh, check,
  filtro, resolução — nenhuma fonte da máquina tem o glifo ★, medido com
  QRawFont).
- **27** — primeiro `QStyledItemDelegate` do projeto: cards quadrados,
  chip de extensão (`.FBX`/`.EXR`) no lugar de cor por tipo, slider de
  tamanho da miniatura (`cell_for_icon()` como fonte única de geometria).
- **28** — barra de busca em 1 linha, "Incluir subpastas" removido,
  Tipos/Nota/Resolução viraram ícone (`FilterButton`, popup de escolha
  única) na linha do breadcrumb.
- **Correções pós-tela** (3 rodadas): janela não redimensionava (painel de
  detalhes sem QScrollArea forçava altura mínima de 1214px — resolvido);
  preview de capa customizada sumia (`_thumb_from_disk` não olhava
  `cover_path`); checkbox de árvore/tabela virava quadrado preto
  (`QTreeView::indicator`/`QListView::indicator`/`QTableView::indicator`
  não estilizados); miniatura vazava por cima do nome; diálogos sem
  moldura; painel de detalhes com cantos quadrados (viewport da
  QScrollArea preenchia o fundo por cima do #card); preview de `.svg`
  novo via QtSvg; preview manual liberado pra qualquer asset sem
  miniatura nativa (`.ies`/`.psd`/`.cube`, não só modelo).

**Não verificável por screenshot automatizado** (offscreen não renderiza
sombra/máscara/decoração de janela): cantos arredondados de card/menu,
ausência de costura no diálogo — confirmados por Rafael na tela real.
303 testes verdes.

### ☑ Executável / entrada no menu de aplicativos (Zorin OS)
`~/.local/share/applications/assetdeck.desktop` (fora do repositório —
caminhos absolutos desta máquina): `Exec` chama o Python da venv direto
(`.venv/bin/python -m assetdeck`, sem precisar "ativar" nada) e `Path`
fixa o diretório de trabalho no repo, porque o pacote não é instalado via
pip — `python -m` só acha `assetdeck` se o cwd for a raiz do projeto
(testado: sem `Path=`, o import falha). Validado com
`desktop-file-validate` (limpo depois de trocar `Categories` — `Graphics`
+ `Utility` juntas contavam como duas categorias "principais" e duplicavam
o app no menu) e testado rodando o `Exec` literal do arquivo.

Ícone novo: `assetdeck/ui/icons/app-icon.svg` (dois cartões sobrepostos,
cor de destaque — referência ao nome "AssetDeck") + `app-icon.png` 256px
gerado com o mesmo `QSvgRenderer` do resto dos ícones. `Icon=` do
`.desktop` usa caminho absoluto (não é o pacote Python, é lido por fora
do processo). De brinde, o app ganhou `setWindowIcon()` de verdade
(carregado por caminho relativo ao pacote) — antes não tinha nenhum,
aparecia um ícone genérico na barra de tarefas/alt-tab.

**Deu certo quando:** o AssetDeck aparece no menu de aplicativos do Zorin
com ícone próprio e abre com duplo clique, sem terminal.

### Resto da F4
Levantado como candidato solto, sem direção — o Rafael revisou em
2026-08-02 e organizou junto com a lista dele; foi pra **F5 — v2.0**
abaixo (auto-tagging e checagem seamless/tileable saíram da lista, os
outros seguiram).

### Fatia 30 — Acabamento (ainda pendente)
Plano detalhado em `REDESIGN.md`: diálogos, `QMenu`, `QToolTip`,
`QScrollBar`, `QSplitter::handle` ainda não confirmados 100% dentro do
tema Craft. Vai ser feita junto com a Fatia 43 (overhaul visual do v2.0,
abaixo) pra não retocar tema duas vezes.

---

## F5 — v2.0 (a fazer)

Lista fechada com o Rafael em 2026-08-02, a partir do que sobrou da F4
("Resto da F4" acima, menos auto-tagging e checagem seamless/tileable,
tirados por decisão dele) + pedidos novos dele. Ordem abaixo é sugestão de
sequência, a confirmar antes de começar cada fatia (uma por vez, como
sempre). Nenhuma tem direção técnica definida ainda — isso é decidido na
hora de fatiar cada uma.

### ☑ Fatia 31 — Filtro por extensão dentro do tipo de asset
`assets_repo.list_for_grid` ganhou o parâmetro `extensions` (filtra pelo
sufixo de `files.rel_path`, case-insensitive) e a função nova
`distinct_extensions(conn, asset_type=None)`. `TypeFilter`
(`ui/type_filter.py`) ganhou um checklist secundário indentado de
extensões por tipo — só aparece pra tipo marcado com mais de uma
extensão presente na biblioteca (ex.: `texture` com `.jpg`/`.png`/`.tiff`
na testlib; `ies` com uma extensão só não ganha checklist). Desmarcar o
tipo pai esconde e ANULA a extensão marcada (não vaza pra outros tipos
selecionados junto). `main_window.py`: `_current_filters_dict`/
`_restore_filters` levam `extensions` — Smart Collections salvam/restauram
de graça, sem migração (query é JSON livre).
**Limitação conhecida:** com 2+ TIPOS marcados ao mesmo tempo, o filtro de
extensão é global (não por tipo) — marcar `.fbx` sob "model" enquanto
"texture" também está marcado restringiria "texture" a `.fbx` também
(caso raro; documentar se o Rafael esbarrar nisso, resolvido fatiando de
novo com um filtro por tipo+extensão combinado se necessário).
**Deu certo quando:** marcar "texture" mostra 11 de 391 assets da testlib;
marcar também `.jpg` mostra 4; desmarcar "texture" volta a mostrar os 391
(a extensão não vaza). Verificado rodando a `MainWindow` de verdade contra
a testlib (script manual, não só teste offscreen). 322 testes verdes (14
novos: `tests/test_search.py` + `tests/test_type_filter.py` novo).

### ☐ Fatia 32 — Navegação de pastas com histórico
Controles tipo navegador (voltar / avançar) na área de visualização de
assets, além da árvore de pastas atual.

### ☐ Fatia 33 — Ícones pré-definidos para tags
Conjunto de ícones prontos (preset) que o Rafael pode escolher ao criar ou
editar uma tag, além da cor que já existe hoje.

### ☐ Fatia 34 — Visualizador avançado de HDRI/EXR
Preview com rotação (esfera), visualização de reflexos — como o
Connecter tem. Maior escopo técnico da lista (provavelmente precisa de
render 3D real, não só um QLabel com imagem); avaliar viabilidade com
Qt/OpenGL na hora de fatiar.

### ☐ Fatia 35 — Templates de tags prontos
Presets de estrutura de tags por área de atuação (arquitetura, filmagem,
gamedev...), com níveis de complexidade (básico / resumido / complexo),
inspirado no Connecter.

### ☐ Fatia 36 — Barra de menus
Arquivo, Editar, Ferramentas, Configurações, Janela — o app hoje não tem
menu de topo nenhum. Definir o conteúdo de cada menu na hora de fatiar.

### ☐ Fatia 37 — Compatibilidade com outros formatos
Revit, Maya, SketchUp, USD, Alembic etc. Maior escopo da lista depois da
34 — cada formato pode precisar de abordagem própria (metadados, preview,
dependências). Avaliar prioridade por formato com o Rafael antes de
começar.

### ☐ Fatia 38 — Render de previews em lote
Cena de estúdio configurável pra gerar capas de vários assets de uma vez
(hoje é um por um, via Blender).

### ☐ Fatia 39 — Busca por cor dominante
Filtrar/buscar assets pela cor predominante da textura/preview.

### ☐ Fatia 40 — Listar texturas faltando de um `.blend`
Detectar e listar mapas que um `.blend` espera mas não encontra na
biblioteca (caminho quebrado, textura removida etc).

### ☐ Fatia 41 — Múltiplas bibliotecas na UI
Suportar mais de uma `library_root` ativa ao mesmo tempo, com seleção na
UI — a `libraries` table já suporta isso desde o schema v1, só a UI
(grid, árvore de pastas) nunca filtrou por biblioteca ativa. É a causa
raiz do bug de pastas duplicadas que resolvemos em 2026-08-02 quando a
testlib e a biblioteca real ficaram indexadas ao mesmo tempo.

### ☐ Fatia 42 — Miniaturas faltando em alguns formatos de imagem
Achado testando a biblioteca real (2026-08-02): 163 arquivos `.tif`
("Silhuetas") e pelo menos 1 arquivo com modo de cor não suportado pelo
Pillow ficam sem preview (asset é indexado normal, só sem miniatura).
Investigar se dá pra ampliar o resgate que já existe pra PNG corrompido
(`thumbs/raster.py`) pra esses casos.

### ☐ Fatia 43 — Overhaul visual (fecha o v2.0)
Por último, de propósito (pedido do Rafael): depois que as fatias 31-42
adicionarem telas/controles novos (menu, navegação de pastas, visualizador
de HDRI...), passar o tema Craft por cima de tudo de uma vez — evita
retocar duas vezes. Absorve também a Fatia 30 (Acabamento) que ficou
pendente da F4.

### ☐ Fatia 44 — Bug: preview customizado não aceita imagem externa via drag-and-drop
Relatado pelo Rafael (2026-08-02): arrastar um `.png`/`.jpeg` do
gerenciador de arquivos do sistema para cima de um asset na grade não
faz nada — devia definir a imagem como capa customizada (Fatia 10).

**Investigado sem reproduzir ainda** (ver `assetdeck/ui/asset_grid.py`):
`_dropped_image` (456-469), `dropEvent` (471-497), `dragEnterEvent`/
`dragMoveEvent` (499-511) diferenciam corretamente drop externo
(`hasUrls()`) de drop interno (`MIME_ASSETS`, Fatia 10b) e emitem
`image_dropped` certinho num teste direto com `QDropEvent` sintético
(offscreen). Os handlers em `main_window.py` (`_on_image_dropped`,
981-994) também estão corretos. **Hipótese principal: integração XDND do
SO** (X11/Wayland ↔ gerenciador de arquivos), fora do que dá pra testar
headless — não é claramente um bug de lógica Python.
**Próximo passo ao fatiar:** reproduzir na tela do Rafael com log
temporário em `dragEnterEvent`/`dropEvent` pra confirmar se o evento
chega no app; testar também com `QT_QPA_PLATFORM=xcb` (descarta
Wayland-specific). Cobertura de teste também falta: nenhum teste hoje
simula um `QDropEvent` com `hasUrls()` real contra `AssetGridView`.

---

## Pendências fora do código
- ☐ Rafael rodar: `sudo apt remove -y blender` (remove o 4.0.2 redundante;
  o projeto usa o 5.2 do Flatpak).
- ☐ Quando o app estiver maduro: cadastrar a biblioteca real do SSD como
  segunda library (o caminho é configuração, nunca hardcoded).

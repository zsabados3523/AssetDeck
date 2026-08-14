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

### ☑ Fatia 31 — Barra de categorias com filtro por extensão

**Primeira tentativa reprovada pelo Rafael na tela** (commit `5e51022`): um
`TypeFilter` só, botão de ícone sem rótulo, com todos os tipos crus do banco
(`pbr_set`, `ies`, `lut`, `other`) e extensões indentadas espremidos num
popup — "não consigo ver exatamente qual opção filtrar". Além disso o filtro
de extensão só existia pra tipo com 2+ extensões, e `extensions` era global
(marcar `.fbx` em Modelos restringia Imagens a `.fbx` também). Refeita
inteira; `ui/type_filter.py` e seu teste foram deletados.

**Versão final, estilo Connecter:** fileira de 6 botões
(`ui/category_bar.py`) na linha do breadcrumb, um por categoria, com ícone
próprio, rótulo legível e contador — `MenuButtonPopup`: o corpo liga/desliga
a categoria, a setinha abre o checklist de extensões *daquela* categoria com
a contagem de cada uma.

- `ui/categories.py` — mapa fixo de UI (não toca no banco) agrupando os 12
  `asset_type` do schema em Modelos · Materiais · Imagens · HDRIs · Vetores ·
  Documentos. Teste trava que todo tipo do schema cai em exatamente uma
  categoria (tipo novo no schema não fica órfão da barra).
- 6 ícones SVG novos (`cat-*.svg`), mesmo estilo dos 8 existentes;
  monocromáticos — cor só no estado ativo, via `QToolButton:checked` que o
  tema já tem, sem QSS novo (decisão do Rafael, mantém a regra da F4).
- `assets_repo`: `_build_where` extraído de `list_for_grid` para a grade e o
  contador responderem aos mesmos filtros (duplicar isso é como o número sai
  de sincronia com a tela). Parâmetro `extensions` (global, da 1ª tentativa)
  substituído por `category_filters` — OR entre categorias, AND entre tipo e
  extensão dentro de cada uma, que é o que corrige o vazamento.
  `count_by_category` respeita os filtros ativos MENOS o de categoria (senão
  clicar numa zeraria o contador das outras e o número perderia a função de
  prever o resultado do clique); `extension_counts` substitui
  `distinct_extensions` e já devolve a contagem por extensão.
- `asset_types` cru continua aceito em `list_for_grid`: Smart Collection
  salva antes desta fatia usa esse formato, e `_restore_filters` remapeia
  pros botões via `set_selection_from_types`.

**Deu certo quando** (verificado com a `MainWindow` real contra a testlib,
não só teste offscreen): barra mostra `Modelos 85 · Materiais 3 · Imagens 11
· HDRIs 7 · Vetores 14 · Documentos 7`; ligar Modelos → 85; marcar `.blend`
→ segue 85; ligar Imagens junto → 96 (a extensão de Modelos NÃO restringe
Imagens); buscar "wood" com tudo desligado → contadores caem pra refletir a
busca. Barra tem 681px e cabe sem espremer o breadcrumb até 1100px de
janela. 329 testes verdes (`tests/test_category_bar.py` novo no lugar do
`test_type_filter.py`).

### ☑ Fatia 32 — Navegação de pastas com histórico
Voltar · Avançar · Subir um nível na linha do breadcrumb (3 ícones novos),
com `Alt+←`/`Alt+→`/`Alt+↑` e os botões laterais do mouse.

- `ui/nav_history.py` — pilha de navegação **sem Qt** (não havia nada de
  histórico/undo no projeto): `push` descarta o "futuro" ao navegar do
  meio, como um navegador; `back`/`forward` levantam `IndexError` fora dos
  limites em vez de falhar quieto.
- **Correção estrutural:** a pasta atual era derivada de
  `folders.currentItem()` e mudava por DOIS caminhos independentes
  (`_on_dir_selected` e `_restore_filters`). Centralizados num
  `_go_to_dir(prefix, record=True)` — histórico furado era questão de
  tempo. Smart Collection entra no histórico (decisão do Rafael).
- `folder_tree.select()` agora devolve `bool` e expande os ancestrais.
  Antes falhava em silêncio com pasta inexistente (deixando o breadcrumb
  mentindo) e podia selecionar dentro de um nó fechado.
- **Bug antigo corrigido de quebra:** `_reload_all` jogava pra raiz no fim
  de cada varredura e não atualizava o breadcrumb — agora a pasta é
  preservada, ou cai na raiz se sumiu do disco.
- Breadcrumb passou a encurtar pela ESQUERDA (`ElideLeft` + tooltip com o
  caminho inteiro): os 3 botões novos comeram ~90px da linha e o título
  ficava cortado no fim, escondendo justamente a pasta atual. Só encurta
  abaixo de ~1366px de janela.
- `tests/test_icons.py` agora varre a pasta de ícones em vez da lista fixa
  (que já tinha ficado desatualizada duas vezes): 21 → 58 casos.

**Deu certo quando** (verificado com a `MainWindow` real contra a testlib):
entrar em `01 - MODELOS` (127→77), depois em `Vegetação` (→75), Voltar
duas vezes, Avançar, Subir; botões habilitam/desabilitam certo a cada
passo; reindexar dentro de `03 - TEXTURAS` continua em `03 - TEXTURAS`;
pasta inexistente cai na raiz. 388 testes verdes (`test_nav_history.py`,
`test_folder_tree.py` — a `FolderTree` não tinha cobertura nenhuma — e
`test_navegacao_pastas.py`, todos novos).

### ☑ Fatia 33 — Ícones pré-definidos para tags
26 ícones `tag-*.svg` desenhados à mão (12 materiais · 6 natureza ·
5 objetos · 3 marcadores), escolhidos num diálogo próprio pelo menu de
contexto da árvore ("Ícone…", ao lado de "Cor…").

**Zero DDL:** a coluna `tags.icon` existe desde o schema v1
(`001_initial.sql:68`, documentada em `SCHEMA.md:113` como "nome de
ícone") e nunca tinha sido lida nem escrita. Só faltava o SELECT
(`list_tree`, `tags_of`), o `set_icon` e a UI.

- `ui/tag_icons.py` — lista dos presets + `pixmap_for(icon, color, tam)`,
  a **única** função que decide como uma tag é desenhada. Os 3 pontos de
  exibição chamam ela; é isso que impede eles de divergirem.
- **Ícone tingido com a cor da tag** (decisão do Rafael): ocupa o mesmo
  espaço de antes e mostra as duas informações de uma vez. Tag sem ícone
  mantém o quadradinho colorido de sempre.
- **Guarda contra SVG que sumiu:** `icons.pixmap` levanta
  `FileNotFoundError`, e sem tratamento uma única tag derrubaria o reload
  da árvore INTEIRA. Cai no quadradinho e loga em WARNING — nunca
  `except` mudo. Testado com `caplog`.
- Aparece na árvore lateral, no painel de detalhes e no Ctrl+T (os dois
  últimos não mostravam nem a cor antes).
- `tests/test_tag_tree.py` novo — a `TagTree` não tinha cobertura
  nenhuma, mesma lacuna que a `FolderTree` tinha antes da Fatia 32.

**Deu certo quando** (verificado com a `MainWindow` real contra a
testlib): pôr madeira/marrom em "Materiais" e metal/azul em "Metal" mostra
os dois tingidos na árvore e no painel de detalhes; tag sem ícone segue
com o quadradinho; tag com ícone inexistente no banco não derruba nada.
507 testes verdes (os 26 SVGs somam 78 casos sozinhos em `test_icons.py`,
que varre a pasta desde a Fatia 32).

### ☑ Fatia 34 — Visualizador avançado de HDRI/EXR
Duplo clique num `.hdr`/`.exr` abre um visualizador OpenGL com dois
modos — **Ambiente** (estar dentro do HDRI, arrastar gira) e **Esfera de
reflexo** (bola espelhada flutuando na cena). Todo o resto continua no
`PreviewPopup`; o desvio reusa `thumbs/hdr.can_hdr()`.

**Viabilidade medida antes de planejar**, não presumida: OpenGL 4.6
(RTX 3070), pipeline completo (shader → VAO → textura → draw) validado
num experimento isolado, e **nenhuma dependência nova** — PySide6 6.11.1
já traz `QOpenGLShaderProgram`/`QOpenGLTexture`/`QOpenGLFunctions_3_3_Core`
(PyOpenGL não é preciso). O Rafael escolheu OpenGL sabendo do custo.

- **Os dois modos são só fragment shader sobre um triângulo de tela
  cheia** — sem malha de esfera, sem índices, sem biblioteca de
  geometria. Ambiente: direção do raio por pixel → equirretangular.
  Esfera: interseção raio×esfera → `reflect()` → mesma textura.
- `ui/hdri_camera.py` — yaw/pitch, clamp nos polos, base ortonormal.
  **Sem Qt de propósito:** o `QOpenGLWidget` não roda offscreen, então a
  matemática mora fora dele e fica coberta pelo pytest normal.
- `app.py` chama `ensure_gl_format()` ANTES do `QApplication`: o formato
  padrão é imutável depois, e sem 3.3 Core o `#version 330` não compila.
- Visualizador criado sob demanda — quem nunca abre HDRI não paga o
  contexto GL.
- Textura liberada no `closeEvent` com o contexto corrente (senão o Qt
  reclama e vaza 32MB de GPU por HDRI 4K).

**Dois bugs achados vendo na tela** (o que os testes não pegariam):
cena de cabeça pra baixo por um `mirrored()` indevido (o Qt já envia a
scanline 0 como primeira linha da textura), e a esfera de reflexo presa a
um ponto do mundo, escapando da tela ao girar — agora acompanha a câmera,
para o ambiente girar EM VOLTA dela. Ambos travados em teste.

**Limite honesto de cobertura:** o desenho GL em si não roda no pytest
("QOpenGLWidget is not supported on this platform"). O que dá é testado
(câmera, preparo de textura, roteamento, e o shader não sair de sincronia
com a matemática Python); o render é verificado com `DISPLAY=:0` +
`.grab()`, que captura o framebuffer de verdade.

**Deu certo quando:** duplo clique em `belvedere_4k.hdr` e
`belfast_farmhouse_4k.exr` (leitores diferentes) abre a cena navegável
com horizonte reto e sem costura na emenda 360°; alternar pra Esfera
mostra a bola refletindo o ambiente; girar mantém a bola centrada.
542 testes verdes.

**Ajuste pós-tela (2026-08-02):** o Rafael usou e apontou que o eixo
VERTICAL estava invertido — arrastar para cima empurrava a vista para o
alto em vez de puxar a imagem para cima. Corrigido; os dois eixos têm
sinais diferentes de propósito agora (o horizontal ele aprovou como
estava). Teste atualizado para travar o sentido novo.

**Candidato barato se o Rafael sentir falta ao usar:** controle de
exposição (oferecido e não escolhido) — com esta arquitetura é um
`uniform` de uma linha, mas exige trocar a textura de 8-bit para float32.
Zoom/campo de visão idem (`tan_half_fov` já é uniform).

### ☑ Fatia 35 — Templates de tags prontos
Template de **Arquitetura/Visualização** em três níveis, aplicado pelo
menu de contexto da árvore de tags ("Aplicar template…"). O Rafael pediu
só a área dele — filmagem e gamedev saíram do escopo por não serem o
trabalho dele.

| Nível | Tags | Forma |
|---|---|---|
| Resumido | 8 | só as categorias-raiz |
| Balanceado | 49 | categoria > tipo |
| Completo | 102 | 3 níveis onde faz sentido (Materiais > Madeira > Carvalho) |

Raízes: Materiais · Vegetação · Mobiliário · Iluminação · Escala ·
Ambiente · Acabamento · Referência — desenhadas em cima das pastas reais
da biblioteca dele. Já vêm **com cor e ícone** (reaproveitando os 26 da
Fatia 33).

- **Os três níveis são o mesmo tronco podado em profundidades
  diferentes**, não três listas soltas — é o que garante que aplicar o
  balanceado depois do resumido só acrescenta folhas. Travado em teste
  (`resumido < balanceado < completo` como conjuntos de caminhos).
- **Aplicar SOMA, nunca substitui.** Saiu de graça: `tags_repo.create()`
  já devolvia a tag existente sem tocar em cor/ícone. Teste prova que uma
  tag pré-existente mantém cor, ícone E os assets marcados.
- `previa()` não escreve nada; alimenta o diálogo mostrando o que é novo
  vs. o que já existe antes de aplicar.
- Zero DDL.

**Bug achado vendo na tela:** marcar "já existe" com `setDisabled` apagava
os FILHOS junto (comportamento do Qt) — "Materiais (já existe)" fazia
Madeira/Pedra/Vidro parecerem que também não viriam. Trocado por cor
esmaecida só no item; travado em teste.

**Deu certo quando** (verificado numa CÓPIA do banco real, sem tocar no
dele): aplicar o balanceado sobre as 2 tags que ele tinha reporta
"47 criadas, 2 já existiam", e "Materiais"/"Metal" saem com cor e ícone
idênticos aos de antes. 565 testes verdes.

**Ajuste pós-tela (2026-08-02):** o Rafael reportou que criar/apagar
qualquer tag reabria a árvore INTEIRA — `reload()` chamava `expandAll()`
sem olhar o que já estava aberto/fechado. Corrigido: `_tags_expandidas()`
captura o estado antes do `clear()` e restaura depois. Só a primeira
carga (árvore vazia/recém-aberta) expande tudo; dali em diante o Rafael
manda. Detalhe achado no caminho: `expandAll()` marca até FOLHA como
"expandida" — sem filtrar por `childCount()`, uma tag sem filho hoje
apareceria aberta sozinha no dia em que ganhasse o primeiro filho.
9 testes novos em `test_tag_tree.py`; 569 no total.

### ☑ Fatia 36 — Barra de menus
Arquivo, Editar, Ferramentas, Configurações, Janela. Reorganiza o que já
existia solto (menu ad hoc "Biblioteca" da Fatia 19, "Blender" da F2, Ctrl+T
como `QShortcut` avulso) num menu de topo de verdade — nenhuma lógica nova,
só descoberta (o Rafael não tinha como saber que "Relocalizar assets
perdidos" existia sem clicar às cegas em "Biblioteca").

- **Arquivo:** Reindexar biblioteca (Ctrl+R) · Sair (Ctrl+Q/atalho padrão).
- **Editar:** Editar tags dos selecionados… (Ctrl+T) · Copiar/Colar/
  Substituir tags · Renomear em lote… · Propriedades customizadas…. As
  ações que dependem de seleção avisam no rodapé em vez de falhar em
  silêncio quando nada está selecionado (`_copy_tags_selected`,
  `_paste_tags_selected`, `_batch_rename_dos_selecionados`).
- **Ferramentas:** Relocalizar assets perdidos… · Duplicados por conteúdo
  visual… (ex-menu "Biblioteca") · Aplicar template de tags… (novo ponto de
  entrada público `TagTree.apply_template_dialog`, além do menu de contexto
  da árvore que já existia) · submenu **Blender** (ex-menu de topo próprio:
  instalar add-on, gerar/parar capas, como usar).
- **Configurações:** Preferências… (diálogo novo, `ui/preferences_dialog.py`
  — só regrava `config.json`: ativar/desativar a ponte, porta, política de
  ocultar preview de origem, backups a manter) · Abrir pasta de
  configuração/logs.
- **Janela:** toggle de visibilidade para cada painel esquerdo (Pastas,
  Tags, Coleções, Smart Collections) + painel de detalhes · Restaurar
  layout padrão (tamanhos originais dos dois `QSplitter`).

**Achado escrevendo os testes:** `QAction.menu()` chamado duas vezes na
mesma comprehension (uma pro filtro `if a.menu()`, outra pro valor) aciona
um bug do shiboken nesta versão do PySide6 — o wrapper Python descartável
da 1ª chamada derruba o `QMenu` de verdade, e a 2ª releitura explode com
"Internal C++ object already deleted". Solução adotada: `MainWindow` guarda
referência própria a cada menu de topo (`self._top_menus`,
`self._menu_arquivo` etc.) em vez de reconstruir a árvore via
`menuBar().actions()` depois — mais robusto e é o que os testes usam.

**Deu certo quando** (verificado com `--screenshot` contra a testlib
ausente neste ambiente — Rafael, confirme na tela real com a testlib
montada): os 5 menus aparecem na barra, "Ferramentas → Blender" mostra as
mesmas 4 ações de antes, "Janela" desliga/religa cada painel, "Restaurar
layout padrão" devolve os painéis escondidos. 577 testes verdes (era 569).

### ☑ Fatia 37 — Compatibilidade com outros formatos
Decisão do Rafael (2026-08-03), depois de eu mapear custo por formato:
**Revit (.rvt), SketchUp (.skp), USD (.usd/.usda/.usdc/.usdz) e Alembic
(.abc)** — Maya ficou de fora. **Só reconhecer e catalogar**, sem tentar
extrair preview embutido (só o `.skp` teria essa convenção, sem lib
pronta no projeto). Entram junto de "Modelos", sem categoria própria.

**7 linhas no `EXT_MAP`** (`indexer/scanner.py`), mapeando pra
`asset_type='model'` — já existente no enum, **zero migration**. Todo o
resto do pipeline decide comportamento pelo `asset_type`, não pela
extensão, então isso resolve de graça: categoria "Modelos"
(`categories.py:21`), detecção de dependência de texturas vizinhas
(`dependencies.py:28`, mesma convenção do `.blend`) e chip de extensão
no card — nenhum dos três precisou de código novo.

**Deu certo quando** (verificado com a `MainWindow` real, biblioteca
sintética): `.rvt`/`.skp`/`.usdz`/`.abc` aparecem na grade com chip
certo e pastilha genérica (igual ao `.blend` hoje); uma textura vizinha
de um deles some da visão padrão (virou dependência, mesmo mecanismo do
`.blend`, sem mudar `dependencies.py`); os 4 formatos caem em "Modelos"
na barra de categoria. 596 testes verdes.

**Dúvida do Rafael esclarecida (2026-08-03), não é bug:** o dropdown de
extensão do botão "Modelos" não mostrava `.rvt`/`.skp`/`.usd*`/`.abc` —
comportamento correto, não defeito. `CategoryButton` (`category_bar.py`)
só lista extensões que existem de verdade entre os assets indexados
(mesma regra da Fatia 31, evita opção vazia no popup); nem a testlib nem
o banco tinham nenhum arquivo desses 4 formatos ainda. Confirmado
rodando: assim que um `.rvt` existe no banco, ele aparece no dropdown na
hora, sem precisar de nada novo.

**Nota**: não dá pra testar com arquivo real de Revit/SketchUp/USD/
Alembic (binários proprietários complexos, nenhum na testlib) — os
testes usam extensão certa em conteúdo dummy, suficiente porque o
scanner só olha o sufixo pra classificar. Vale o Rafael confirmar com um
arquivo de verdade se tiver algum à mão.

### ☑ Fatia 38 — Render de previews em lote (cena configurável)
Bloqueada pela sessão automatizada anterior por falta de Blender no
ambiente dela — **Blender + Flatpak estão instalados aqui**
(`org.blender.Blender` 5.2, confirmado com `flatpak list`), o que
desbloqueou a fatia de verdade.

**Descoberta ao mapear:** a fila em lote **já existia** —
`RenderWorker` (`ui/render_worker.py`) já pegava TODOS os modelos sem
capa e renderizava um por vez (um processo Blender headless por asset,
isolamento de crash proposital), sem travar a UI, com progresso e
cancelamento. Só faltava a **cena configurável**, 100% hardcoded até
aqui.

Decisões do Rafael (2026-08-03): mantém fundo cinza + sol (sem HDRI) —
só **cor do fundo**, **força do fundo** e **intensidade do sol** viram
configuráveis; continua 1 ângulo por asset; continua "todos sem capa"
(sem seletor de assets nesta fatia); campos ficam em Configurações →
Preferências, preset global.

- `hex_to_linear_rgb()` nova (`blender/render.py`) — o `QColorDialog`
  devolve sRGB, o shader do Blender espera linear; sem a conversão a cor
  sai mais clara do que a escolhida na amostra.
- `render_thumbnail()` ganha `bg_color`/`bg_strength`/`sun_energy` com
  defaults **idênticos aos valores hardcoded de sempre** — todo chamador
  existente (inclusive os testes já escritos) continua funcionando sem
  mudar uma linha.
- `render_thumb.py` (roda dentro do Blender) lê os 3 valores extra do
  `sys.argv`, com fallback pros mesmos hardcoded se não vierem — chamar
  o script à mão continua funcionando.
- `RenderWorker.run()` lê `config.load_config()` **a cada rodada**, não
  uma vez só — mudar a preferência e clicar em "Gerar capas" de novo já
  usa o valor novo, sem reiniciar o app (diferente de
  `bridge_port`/`bridge_enabled`, que precisam de reabertura porque o
  servidor já está de pé).
- Amostra de cor no diálogo é **ícone** (`QPixmap` preenchido), nunca
  `setStyleSheet` — regra do projeto, mesmo padrão do quadradinho de cor
  de tag (`tag_icons.py`).

**Verificado com Blender de verdade, não só teoria:**
`test_render_de_verdade_gera_png` (já existia, pulado até aqui por
`skipif`) passou de verdade (3,6s). Escrevi um teste diferencial novo —
renderiza duas cores bem diferentes e compara o pixel de fundo do PNG
final — em vez de comparar contra um valor absoluto exato, porque o
Blender aplica view transform (AgX, padrão desde a 4.x) por cima da cor
linear; reproduzir essa curva aqui seria escopo maior que a fatia pedia.
Script manual comparando 3 cenas lado a lado (padrão / fundo azul forte
/ sol fraco) confirma visualmente a diferença.

**Deu certo quando:** 608 testes verdes (12 novos, incluindo o real de
Blender); mudar a cor em Preferências e clicar em "Gerar capas" usa a
cor nova sem reiniciar o app; as 3 cenas de teste saem visualmente
diferentes no render real.

### ☑ Fatia 39 — Busca por cor dominante
Desbloqueada nesta sessão: perguntei ao Rafael as duas coisas que faltavam
e ele decidiu (2026-08-03): **cor média simples** (não quantização/k-means)
e **paleta fixa de botões de cor** (não seletor livre). Confirmou também
que podia mexer no schema.

- `assetdeck/db/migrations/006_dominant_color.sql` — `files.dominant_color
  TEXT`, NULL pra não-raster (mesmo padrão do phash). `SCHEMA.md`
  atualizado.
- `assetdeck/thumbs/dominant_color.py` (novo, espelha `thumbs/phash.py`):
  cor média reamostrando a imagem inteira pra 1x1 pixel. Ligado no MESMO
  lugar que já abre a imagem pro phash em `scanner.image_meta()` — não
  abre o arquivo de novo.
- `color_distance(hex_a, hex_b)` — função SQL customizada registrada em
  `db/connection.py::connect()` (nenhuma função customizada existia antes
  no projeto); comparar hex ficaria ilegível como expressão SQL inline.
  `assets_repo._build_where` ganha `dominant_color` + `COLOR_TOLERANCE`
  (constante, calibrada olhando a testlib real — ver nota abaixo).
- UI: `FilterButton` ganhou um parâmetro `swatch=True` (ícone quadradinho
  de cor por opção, via `QPixmap.fill` — mesmo precedente da cor de tag,
  não é `setStyleSheet`) em vez de widget novo. Paleta de 11 cores fixas
  na barra do breadcrumb, ícone novo `palette.svg`.

**Nota sobre a testlib real:** rodando contra a biblioteca de teste, os
baldes "Marrom" e "Preto" trazem MUITO mais assets (212 e 175 de 634 com
cor) do que "Azul"/"Verde"/"Laranja" (0 cada). Não é bug — a testlib é
pesada em madeira/pedra/vegetação, cores reais de material tendem pro
terroso/escuro, e cor pura de vermelho/azul quase não aparece numa
textura de verdade. É a ressalva que já estava registrada aqui antes
("pode ficar 'lavada'") se confirmando na prática.

**Deu certo quando:** 637 testes verdes (`pytest -q`, 12 novos:
`test_dominant_color.py`, mais casos em `test_migrations.py`,
`test_filter_button.py`, `test_search.py`); rodei a varredura completa
contra a testlib real e
conferi que o filtro por cor realmente muda a contagem de resultados por
balde. Falta o Rafael confirmar na tela (abrir o app, clicar num botão de
cor da paleta, ver a grade estreitar) — ambiente desta sessão não tem
display interativo pra clicar de verdade, só screenshot + consulta direta
no banco.

### ☑ Fatia 40 — Listar texturas faltando de um `.blend`
Bloqueada pela sessão automatizada anterior por falta de Blender no
ambiente dela — desbloqueada aqui, mesmo caso da Fatia 38.

Decisões do Rafael (2026-08-03): reaproveita a mesma regra de
`texturas_perdidas()` (toda imagem com caminho quebrado, sem filtrar por
uso em material); sob demanda, um asset por vez (botão "Checar
texturas…" no painel de detalhes, só pra `.blend`); sem persistência —
calcula na hora, mostra num diálogo, nada grava no banco.

- `blender/scripts/list_missing_textures.py` (novo) roda dentro do
  Blender, **nunca escreve nada**. Roda a mesma relocalização automática
  que o render já faz (`bpy.ops.file.find_missing_files`, só na cópia em
  memória) e reporta **só o que continua quebrado depois** — é a
  informação de fato acionável, já que o render (Fatia 16/38) resolve o
  resto sozinho. Duplica ~15 linhas de `render_thumb.py` de propósito:
  aquele script chama `main()` incondicionalmente no nível do módulo
  (sem guarda de `__main__`), então importar de lá dispararia um render
  por engano.
- `blender/missing_textures.py` (novo): mesmo padrão de
  `render.py::render_thumbnail` (subprocess + timeout, nunca levanta),
  lendo uma linha `ASSETDECK_TEXTURAS_JSON {...}` isolada do stdout (uma
  linha JSON só, não texto solto — o Blender imprime bastante ruído de
  inicialização no mesmo stdout).
- `DetailsPanel`: botão novo **visível só quando o arquivo é `.blend`**
  e não está sumido — os formatos novos da Fatia 37 (`.rvt`/`.usd*`/
  `.abc`) não são arquivos Blender, então o conceito nem se aplica.
- `MissingTexturesDialog` (novo): tabela somente-leitura (textura +
  caminho esperado) + resumo + "Abrir pasta do asset". Sem checkbox, sem
  ação de aplicar — não há nada pra escrever: o que está quebrado é
  referência interna do `.blend`, fora do alcance de escrita do app
  (`relocator.py` só ajusta o banco do AssetDeck, nunca o conteúdo de um
  `.blend`).

**Descoberta rodando de verdade** (não achei escrevendo o teste, achei
rodando contra o Blender real): criar uma imagem sintética via
`bpy.data.images.new()` sem religar a nenhum material faz ela **sumir
silenciosamente** do `.blend` ao salvar — precisa de
`img.use_fake_user = True` pra sobreviver ao save. Sem isso os testes de
integração real dariam "lista vazia" mesmo com a textura de propósito
quebrada, um falso-negativo que passaria despercebido.

**Deu certo quando:** 625 testes verdes (17 novos, incluindo 2 rodando o
Blender de verdade). Verificado no app real: `.blend` sintético com uma
imagem de caminho quebrado — botão aparece, checagem acha a textura
certa (nome + caminho), diálogo mostra a tabela e o resumo.

### ☐ Fatia 41 — Múltiplas bibliotecas na UI (avaliada, não implementada — risco/escopo)
Suportar mais de uma `library_root` ativa ao mesmo tempo, com seleção na
UI — a `libraries` table já suporta isso desde o schema v1, só a UI
(grid, árvore de pastas) nunca filtrou por biblioteca ativa. É a causa
raiz do bug de pastas duplicadas que resolvemos em 2026-08-02 quando a
testlib e a biblioteca real ficaram indexadas ao mesmo tempo.

**Avaliada e adiada de propósito nesta sessão automatizada** — não é
"não coube o tempo", é risco real demais pra fazer sozinho, sem o Rafael
podendo confirmar na tela e sem a biblioteca real (SSD NTFS) disponível
pra testar de verdade:
- `library_root: Path` é um parâmetro passado por CONSTRUÇÃO (não lido do
  banco por asset) em praticamente todo módulo que toca em caminho de
  arquivo — `MainWindow`, `AssetGridModel`, `FolderTree`,
  `DetailsPanel`, `batch_rename.py` (a ÚNICA exceção ao somente-leitura
  — um bug de resolução de caminho ali escreve no lugar errado de
  verdade), `sidecar/writer.py`, `indexer/scanner.py`, a ponte com o
  Blender e o render de capas. Suportar VÁRIAS ao mesmo tempo exige virar
  cada `library_root / rel_path` em "olhar o `library_id` do asset e
  resolver a raiz DELE" — mudança sistêmica, não uma tela nova.
- **Decisão de UX que só o Rafael pode dar:** grade combinada mostrando
  as duas bibliotecas juntas, ou trocar de biblioteca como quem troca de
  aba? Onde entra o seletor? Isso é do mesmo tipo de decisão que o
  redesign visual (F4) — iterada com ele olhando a tela, não fatiada
  sozinho.
- Testável só com sintético neste ambiente (sem a biblioteca real de
  650GB); um bug de resolução de caminho tocando `batch_rename` (escreve
  no disco de verdade) tem custo alto demais pra arriscar sem validação
  real.

**Plano técnico pra quando ele confirmar a UX** (pra não redescobrir
nada): `config.json` ganha `library_roots: list[str]` (migração suave a
partir do `library_root` singular hoje, mesmo padrão de "chaves novas
completadas" que `config.load_config` já usa); cada módulo que hoje
recebe `library_root: Path` passa a receber uma função
`resolve_root(library_id) -> Path` ou um dict `{library_id: Path}`;
seletor na UI (provável: perto da árvore de pastas, como mais um filtro,
reaproveitando o padrão do `CategoryBar`/`FilterButton` da Fatia 31/28c).

### ☐ Fatia 42 — Miniaturas faltando em alguns formatos de imagem (parcial)
Achado testando a biblioteca real (2026-08-02): 163 arquivos `.tif`
("Silhuetas") e pelo menos 1 arquivo com modo de cor não suportado pelo
Pillow ficam sem preview (asset é indexado normal, só sem miniatura).

**Investigado sem acesso aos arquivos reais** (esta sessão rodou sem a
testlib nem a biblioteca do Rafael montadas — CLAUDE.md proíbe apontar
para outro caminho, e não existia um pra apontar aqui). Sem os arquivos
que falham (ou o trecho do log deles), não dava pra confirmar a causa raiz
— então não fiz uma correção "no escuro" e chamá-la de pronta.

**O que foi feito, como melhoria estrutural defensável por si só** (não
como correção confirmada): `thumbs/raster.py::make_thumbnail` convertia o
modo da imagem (paleta, CMYK, 1-bit → RGB/L/RGBA) **depois** de chamar
`img.thumbnail()`. Isso é estruturalmente arriscado — o resample
BICUBIC/LANCZOS padrão do Pillow historicamente não aceita todo modo — e
`.tif` de máscara ("Silhueta") é candidato natural a vir em modo "1" ou
"P". Virou `_to_safe_mode()`, chamado ANTES do resize. Testado com `.tif`
sintético nos modos 1/P/CMYK/L/RGB (`test_tif_em_varios_modos_de_cor_gera_thumbnail`),
mas **nenhum desses modos falhava também na ordem antiga** nesta versão do
Pillow (12.3.1) — não consegui um teste vermelho→verde, só cobertura de
regressão. Pode não ser a causa real do bug do Rafael.

**Pendente para fechar de vez:** o Rafael rodar contra a biblioteca real
de novo e, se algum `.tif` continuar sem preview, colar aqui o trecho do
log (`~/.local/share/assetdeck/logs/assetdeck.log`, procurar "Thumbnail
falhou") — o traceback tem o tipo exato de exceção do Pillow, que é o que
falta pra mirar a correção certa em vez de generalizar no escuro.

### ☑ Fatia 43 — Overhaul visual (fecha o v2.0)
Desbloqueada em 2026-08-03: o Rafael trouxe 3 referências visuais (uma DAM
clara com roxo, MuseDAM e TextureLibrary, escuras) e, depois de eu apontar
que isso contradiz a decisão monocromática da F4, decidiu: **continua
monocromático** (sem cor de destaque nova), mas quer **modo escuro de
verdade** (toggle manual persistido) e cantos/sombra mais generosos.
Escopo cresceu no caminho com um bug real e um combinado anterior que não
tinha sido registrado — ver abaixo.

**Parte 1 — bug + reorganização, sem tocar em paleta:**
- **Bug corrigido:** desligar todos os painéis pelo menu Janela fazia a
  barra de busca inchar até quase tomar a tela (medido: 356px de altura,
  deveria ser ~46px). Causa: `top_card`/`splitter` disputavam o espaço
  extra do `QVBoxLayout` central sem prioridade nenhuma entre eles —
  `layout.setStretchFactor(splitter, 1)` resolve, splitter sempre ganha.
- `fav_check`/`group_check`/`deps_check`/`hidden_check` saíram da barra de
  busca e viraram `QAction` marcável no menu **Janela** (combinado
  anterior que não estava escrito aqui) — mesmos nomes de atributo,
  `QAction` tem a mesma API de `QCheckBox` que o resto do código já usava.
- Barra do breadcrumb, **opção C** (dos 3 esboços mostrados na tela,
  antes de tocar em código): botões de navegação viram "ghost" (sem
  moldura), divisor fino entre grupos (navegação+caminho / categorias /
  filtros), slider de tamanho saiu da barra e foi pro rodapé.
- Fatia 30 (Acabamento): a maior parte já estava pronta (`QMenu`/
  `QToolTip`/`QScrollBar`/`QSplitter::handle` já tinham regra no
  `theme.qss` — nota antiga do REDESIGN.md estava desatualizada).
  `PreferencesDialog`/`PreviewPopup` conferidos por screenshot, nenhum
  precisou de mudança.

**Parte 2 — modo escuro (infraestrutura nova do zero):**
- `theme.py` ganhou uma paleta `_DARK` completa (mesma lógica
  monocromática, luminância invertida; `WARNING`/`DANGER` mais claros pra
  manter contraste). `Variant` ganhou o campo `mode` (claro/escuro).
  `build_tokens`/`build_palette`/`surface_solid` escolhem a paleta certa
  por um dict interno (`_paleta()`), sem duplicar as funções.
- **Achado tarde, mas corrigido:** vários widgets pintam cor "à mão" em
  Python (delegate da grade, ícones pré-tingidos de nav/busca/categoria/
  filtro/estrela/tag) — isso NÃO passa pelo QSS, então continuavam
  sempre na cor clara mesmo em modo escuro (o card "sem miniatura" saía
  branco num fundo escuro). `theme.current_colors()` novo (lê o último
  `Variant` aplicado) + `refresh_theme()` em `AssetCardDelegate`,
  `AssetGridModel`, `FilterButton`, `CategoryBar`/`CategoryButton`,
  `DetailsPanel`, chamados de `MainWindow._refresh_theme_dependent_widgets`
  depois de cada troca — sem isso, o toggle ao vivo ficaria pela metade.
- Vitrine (`--theme-preview`) ganhou um 5º combo "Modo" — reaproveita o
  mecanismo de troca ao vivo que já existia (`apply_theme(app, variant)`
  de novo já re-renderiza tudo, sem `unpolish`/`polish` manual).
- Toggle real: `QAction` marcável "Modo escuro" no menu Configurações,
  aplica na hora (sem precisar reabrir o app) e persiste em
  `config.json: theme_mode`.
- Cantos: `DEFAULT.radius` virou `"marcante"` (16/12/9px, já existia como
  opção). Sombra: mais presença (blur 18→24, alfa 28→42) — sobretudo
  efeito de modo claro; no escuro a elevação vem mais do contorno/
  `$popover` do que da sombra, que quase não aparece em fundo escuro
  (esperado).

**Deu certo quando:** 650 testes verdes (`pytest -q`, ~20 novos: bug do
resize, checks no menu, contraste WCAG do modo escuro nos mesmos pares já
testados no claro). Rodei o app real contra a testlib nos dois modos —
screenshot confirma barra de busca normal mesmo com painéis desligados,
cards com fundo correto nos dois modos, diálogos OK sem código extra.

**Falta o Rafael confirmar na tela** — mais que qualquer outra fatia,
porque cor/modo escuro é decisão de gosto: a paleta escura foi calibrada
com as fórmulas de contraste (WCAG), não olhando pra tela de verdade.
Bem provável que precise de ajuste fino, como aconteceu com a paleta
clara na F4 (três rodadas de correção).

### ☑ Fatia 44 — Bug: preview customizado não aceita imagem externa via drag-and-drop
Relatado pelo Rafael (2026-08-02): arrastar um `.png`/`.jpeg` do
gerenciador de arquivos do sistema para cima de um asset na grade não
faz nada — devia definir a imagem como capa customizada (Fatia 10).

**Investigado sem reproduzir na época** (ver `assetdeck/ui/asset_grid.py`):
`_dropped_image`, `dropEvent`, `dragEnterEvent`/`dragMoveEvent`
diferenciam corretamente drop externo (`hasUrls()`) de drop interno
(`MIME_ASSETS`, Fatia 10b) e emitem `image_dropped` certinho num teste
direto com `QDropEvent` sintético (offscreen). Hipótese principal na
época: integração XDND do SO — sem confirmação.

**Buraco de cobertura fechado em 2026-08-03**: `tests/test_asset_grid_drop.py`
— 4 testes com `QDropEvent`/`QDragEnterEvent` DE VERDADE contra a
`AssetGridView`. Passaram, reforçando a lógica Python sem provar a causa.

**Causa raiz confirmada em 2026-08-05** (ver Fatia 51): não é XDND geral —
é especificamente soltar DENTRO da mesma view que iniciou o arrasto. O
mesmo fix da Fatia 51 (fallback por posição real do cursor) cobre este
caso também, já que os dois passam pelo mesmo `_apply_drop`. **Falta o
Rafael confirmar na tela** especificamente para o caso de imagem externa
(ele confirmou o caso asset-sobre-asset, que motivou a Fatia 51).

### ☑ Fatia 51 — Bug: arrastar asset sobre outro asset da grade não funciona
Relatado pelo Rafael (2026-08-05), variante do Fatia 44: arrastar uma
imagem (asset já indexado) sobre um `.blend`/`.fbx` pra definir como
preview (Fatia 10b) não fazia nada.

**Reproduzido com log real** (não sintético): instrumentei
`startDrag`/`dragEnterEvent`/`dropEvent`/`_on_asset_preview_dropped` em
INFO (nível padrão, sem flag extra) e pedi pro Rafael tentar uma vez. Log
de 5 tentativas reais: `startDrag` dispara e retorna todas as 5 vezes,
`dragEnterEvent` NUNCA aparece — nem uma. Rafael confirmou que outros
arrastos (Tags, Coleções, Blender) funcionam normalmente, isolando o
problema para "soltar DENTRO da mesma view que iniciou o arrasto"
especificamente — não é XDND quebrado em geral.

**Tentativa de reproduzir sinteticamente com QTest (mouse real via `xcb`,
display `:0`, não offscreen) esgotada sem sucesso**: replica o SINTOMA
(`startDrag` dispara, nada mais chega) tanto para o caso próprio quanto
para grid→Coleções (que o Rafael confirma funcionar) — ou seja,
`QTest.mouseMove` não sustenta um `QDrag.exec()` nativo neste ambiente
pra NENHUM alvo, então não serve pra comparar "funciona" com "não
funciona". Descoberta lateral: `QCursor.pos()` também não acompanha
`QTest.mouseMove` aqui — é por isso que o fix não depende dele nesse
sentido (lê o cursor real do SO, não o sintético).

**Fix, sem depender de entender a causa exata no Qt/X11** (`asset_grid.py`):
depois que a chamada bloqueante nativa (`super().startDrag()` ou
`drag.exec()`) retorna, se `dropEvent` não confirmou entrega
(`_native_drop_handled` continua `False`), um fallback lê a posição REAL
do cursor (`QCursor.pos()`, não sintética) e aplica o efeito na mão se
ela cair sobre outro card desta mesma grade. `_apply_drop()` extraído
como lógica compartilhada entre o `dropEvent` nativo e o fallback — cobre
os dois casos (asset-sobre-asset E imagem externa) com um só caminho.
Soltar fora da grade (Blender/Tags/Coleções, que já funcionam) não é
afetado: `indexAt()` da posição do cursor dá inválido fora dos limites da
view, e o fallback só age quando o alvo é OUTRO card da própria grade.

6 testes novos em `tests/test_asset_grid_drop.py` (mockando `QCursor.pos`
para determinismo, já que ele não é confiável sob simulação): fallback
aplica corretamente; ignora quando o cursor está sobre a própria origem;
ignora quando está fora da grade (não rouba drops legítimos pra outro
widget); cobre o caso de imagem externa também; `dropEvent` marca entrega
nativa confirmada. 715 testes verdes.

**2ª rodada (mesmo dia): o fix funcionou, mas nada aparecia na tela.**
Rafael testou de novo e ainda "não foi possível". O log desta vez contava
outra história: `fallback` disparava, achava o alvo certo pela posição do
cursor, `_apply_drop retornou True`, `_on_asset_preview_dropped` recebia o
sinal — ou seja, o MECANISMO DE ARRASTO estava, desta vez, funcionando de
ponta a ponta. Conferi direto no banco real (`~/.local/share/assetdeck/
assetdeck.db` — esse caminho é local, meu acesso a ele é confiável, ao
contrário de caminhos dentro do SSD montado) e não havia NENHUMA linha
nova em `previews` para os assets testados: a cópia do arquivo estava
falhando silenciosamente.

Causa: `_on_asset_preview_dropped` nunca teve `try/except` em volta de
`previews_repo.add()` (que levanta `FileNotFoundError`/`OSError` se a
cópia falhar por qualquer motivo) — diferente do caminho irmão
(`_on_image_dropped`, protegido desde a Fatia 10). Como a falha acontece
DENTRO de um sinal Qt emitido de dentro de `startDrag()` (chamado pelo
C++ do Qt), a exceção não tinha como aparecer no log nem crashar o app:
simplesmente desaparecia — viola em espírito a regra do projeto de nunca
ter erro sem contexto logado.

Cheguei a suspeitar que `library_root` (com "BIBLIOTECA {CURA}" duplicado
no caminho do config) estivesse errado — **Rafael confirmou que é assim
mesmo, de propósito**, e que o SSD estava conectado. Minha checagem de "o
arquivo existe?" rodou pela minha própria ferramenta de terminal, que não
enxerga o SSD montado dele (limitação do MEU sandbox, não bug do config)
— descartada como pista. A causa real da falha na cópia continua
desconhecida; o fix não depende de saber qual é.

Fix: `_on_asset_preview_dropped` agora envolve `previews_repo.add()` num
`try/except (FileNotFoundError, OSError)`, loga com `log.exception()`
(origem, alvo, caminho tentado, `library_root`) e mostra a mensagem no
rodapé — mesmo padrão do `_on_image_dropped`. Continua tentando as outras
origens se o drop tiver mais de uma. Teste novo prova que era um bug
real: derruba com exceção não tratada SEM o fix (confirmado rodando
contra o código antigo via `git stash`), passa limpo COM o fix.

716 testes verdes.

**Confirmado pelo Rafael na tela (2026-08-05): está funcionando.** Preview
aplicado corretamente pelo fallback. Observação cosmética dele: durante o
arrasto, o cursor mostra o ícone de "bloqueado" o tempo todo, mesmo o
resultado saindo certo — mesma causa raiz (nenhuma janela confirma o
drop nativamente, então o Qt nunca troca o cursor pro de "aceito"; o
fallback aplica o efeito DEPOIS, mas não retroage no cursor mostrado
durante o gesto). Não afeta o funcionamento. Consertar isso direito
exigiria trocar `super().startDrag()` por um `QDrag` manual também no
caso de 1 item só (pra poder chamar `setDragCursor`), o que muda também o
preview visual do item arrastado — foi deixado como polimento opcional,
a critério do Rafael, não bloqueia o fechamento desta fatia.

**Pergunta do Rafael que virou um bug de performance real:** por que
demora ~1,5-2s pra assinalar o preview? Medi contra o banco real dele (23
mil assets): `AssetGridModel.reload()` chamava `_warmup()` — que varre a
biblioteca INTEIRA sem filtro (72.059 linhas no modo expandido) e confere
no disco se cada thumbnail já existe (~64.606 checagens) — TUDO síncrono
no thread principal. Medido: ~1,1s (388ms SQL + 379ms filtro Python +
335ms `dest.exists()` por item). E `reload()` roda a cada ação pequena
(preview, favorito, nota, tag), não só depois de varredura.

Fix: `reload()` virou barato (só `_requery()` — 11ms medido numa pasta
filtrada real dele); o pré-aquecimento foi pra `warmup_library()`,
chamada só de `_reload_all()` (que já é reservada pra pós-varredura/
rename em lote/agrupar — nunca pelas ações frequentes). 3 testes novos em
`tests/test_asset_grid_warmup.py`, confirmando via `git stash` que
derrubavam contra o código antigo.

**Medido de ponta a ponta com o banco real do Rafael: ~1100ms → ~11ms.**
719 testes verdes. Falta ele confirmar na tela que a trava sumiu.

### ☑ Fatia 52 — CAUSA REAL do drag-and-drop: o viewport da grade recusava todo drop
Rafael relatou de novo em 2026-08-06: arrastar imagem pra definir preview
"antes funcionava, agora não funciona mais", e o cursor mostra "bloqueado"
durante o arrasto. Isso fecha, com a causa verdadeira, o que as Fatias 44
e 51 tinham só contornado.

**Causa (uma linha):** `setMovement(QListView.Movement.Static)` — que a
Fatia 19b adicionou pra resolver o card que ficava preso — faz, dentro do
Qt, `viewport()->setAcceptDrops(false)`: ele assume que uma grade imóvel
não recebe drop nenhum. E quem recebe os eventos de arrasto do SISTEMA é
o **viewport**, não a view. O `setAcceptDrops(True)` da view só é
repassado pro viewport quando o valor MUDA (evento `AcceptDropsChange`);
como já estava `True` desde a linha anterior, o repasse nunca acontecia.
Resultado: o viewport recusava tudo, o X nunca marcava a janela como
alvo válido (daí o cursor de bloqueado) e `dragEnterEvent`/`dropEvent`
nunca disparavam. **Zero ocorrências deles nos 6 arquivos de log do
Rafael** — nenhuma, desde que o log foi instrumentado.

**Por que passou despercebido por tantas fatias:** os testes de
`test_asset_grid_drop.py` entregam o evento na mão pra view
(`view.dropEvent(...)`), pulando exatamente o widget quebrado. Passavam
verdes com o app 100% surdo a arrastos. A docstring do arquivo chegou a
concluir que "o bug é do gerenciador de arquivos ↔ Qt, não do app" —
estava errada, e foi corrigida.

**Fix:** `self.viewport().setAcceptDrops(True)` explícito, DEPOIS de
`setMovement`, no fim do bloco de drag-and-drop do `__init__`.

**Verificado com mouse REAL (XTEST/libXtst) e XDND entre processos** —
não sintético: um segundo processo Qt fazendo o papel do Nautilus
(`QDrag` com `text/uri-list`) e o app de verdade rodando sobre a testlib.
- ANTES do fix: `drag.exec()` da fonte devolve `IgnoreAction` (= cursor
  de bloqueado), nenhum `dragEnterEvent`/`dropEvent` no log, nada aplicado.
- DEPOIS do fix: devolve `CopyAction`, `dragEnterEvent` + `dropEvent`
  disparam, e o log confirma `Preview user adicionado ao asset ... (capa=True)`.
Vale para os dois casos: imagem externa → card, e asset da grade → card.

**Fallback da Fatia 51 REMOVIDO** (`_fallback_drop_by_cursor_position`,
`_native_drop_handled` e os 5 testes dele). Agora é comprovadamente
desnecessário — e era perigoso: decidia só pela coordenada do cursor, sem
saber qual JANELA estava por cima nem se o gesto tinha sido cancelado.
Soltar um asset no Blender aberto por cima da grade, ou apertar Esc no
meio do arrasto, aplicava um preview que ninguém pediu.

2 testes novos de regressão (`viewport().acceptDrops()` logo no
`__init__`, sem depender de tela) — confirmados via `git stash` que
derrubam contra o código antigo. **716 testes verdes.**

**Achado à parte, fora do código:** o log do Rafael mostrava TODA cópia de
preview falhando com `FileNotFoundError`. Não é bug do app — o SSD da
biblioteca não estava montado (`lsblk` mostrava `sdb1` LABEL=`SSD` sem
ponto de montagem, e `/media/rafael/` vazio), então `library_root`
apontava pra um caminho inexistente. Ele montou o disco e o problema
sumiu. Diagnóstico ficou mais difícil do que precisava: nos 6 arrastos
registrados no log dele, TODOS eram asset-sobre-asset — nenhum vinha do
gerenciador de arquivos (dá pra distinguir pelo formato no log:
`application/x-assetdeck-asset-ids` = veio da grade).

**Confirmado pelo Rafael na tela (2026-08-06): "está funcionando
perfeitamente"** — os dois casos (imagem externa → card e asset da grade
→ card). Mergeada na `main`.

**Ideia de melhoria que ficou de fora (decisão do Rafael):** hoje, quando
`library_root` não existe, o app só mostra uma mensagem discreta no
rodapé — e TODA ação de arquivo falha em silêncio prático. Valeria um
aviso visível na abertura ("a biblioteca não está acessível: <caminho>"),
que teria evitado esta ida e volta inteira.

### ☑ Fatia 46 — Teste da ponte falha com o app aberto
`tests/test_main_window.py::test_ponte_e_render_ficam_prontos` afirmava que
a ponte do Blender está escutando, mas ela usava a porta FIXA 45017
(`config.DEFAULTS["bridge_port"]`). Com o AssetDeck de verdade aberto na
máquina, a porta já estava tomada e o teste falhava — aconteceu duas vezes
durante o desenvolvimento, e nas duas o "erro" era só o app do Rafael
rodando.

Não era regressão de código, era teste sem isolamento. Corrigido como o
TODO já sugeria: a fixture `janela` (usada por TODOS os testes de
`test_main_window.py`, não só este) agora escreve `bridge_port: 0` no
config.json isolado ANTES de instanciar a `MainWindow` — porta 0 pede pro
SO escolher uma livre, então nunca colide com uma instância real aberta.
Zero asserção enfraquecida; `test_ponte_e_render_ficam_prontos` ganhou uma
checagem a mais (`_bridge.port > 0`, confere que o Qt realmente subiu numa
porta de verdade, não só que `listening` ficou True).

**Verificado propositalmente** (não só teoria): um `QTcpServer` de teste
ocupou a 45017 de propósito ANTES de rodar a suíte — sem o fix o teste
falhava do jeito descrito; com o fix, passa igual.
**Deu certo quando:** `pytest -q` continua verde mesmo com algo ocupando a
porta 45017. 577 testes verdes.

### ☑ Fatia 45 — Cor e ícone de tag não sobrevivem ao sidecar
Achado ao fatiar a 33. O sidecar gravava tags como lista plana de caminhos
(`["Materiais/Madeira"]`) e a restauração em `indexer/scanner.py` chamava
`get_or_create_path`, que recria a hierarquia **sem cor e sem ícone**. Ou
seja: apagar o banco e reindexar devolvia as tags, mas cinzas e sem ícone
— buraco que existia desde a Fatia 8 (cor); o ícone só herdou o mesmo
problema na Fatia 33.

**Sidecar formato 2** (`sidecar/writer.py`, `FORMAT_VERSION = 2`): `tags`
virou lista de `{"path", "chain": [{"name","color","icon"}, ...]}` — a
cadeia INTEIRA (raiz até a folha), não só o nome de cada elo. Precisava
ser a cadeia toda, não só a folha: um ancestral como "Materiais" tem cor
própria mesmo sem ser a tag diretamente atribuída ao asset, e só aparece
em sidecars onde alguma folha descende dele.

- `db/repos/tags.py`: `tag_chain()` (lê a cadeia com cor/ícone) e
  `get_or_create_chain()` (recria com cor/ícone — um elo que já existe no
  banco NÃO é sobrescrito, mesma regra "soma, nunca substitui" da Fatia 35).
- `sidecar/reader.py::_restorable_tags` normaliza os DOIS formatos (1 e 2)
  pro mesmo formato de saída — `scanner.py` não precisa saber de qual
  veio. Sidecars formato 1 (os que já existem na biblioteca real do
  Rafael) continuam sendo lidos, só sem cor/ícone — nunca existiu neles.
- `read_sidecar` aceita `assetdeck` 1 OU 2 (só uma versão 3+ desconhecida
  é rejeitada).
- **Bridge com o Blender não mudou:** `bridge/handlers.py` usa
  `assets_repo.get_bundle()["tags"]`, que continua `list[str]` — só o
  sidecar (`sidecar/writer.py`) busca a cadeia detalhada direto via
  `tags_repo`, sem tocar no formato usado pela ponte.
- Zero DDL: `tags.color`/`tags.icon` já existiam desde o schema v1.

**Deu certo quando:** setar cor numa tag raiz e ícone numa subtag,
taggear um asset com a folha, apagar o banco e reindexar — cor e ícone de
TODOS os elos da cadeia voltam idênticos (não só o nome). 588 testes
verdes (era 582).

---

## Pendências fora do código
- ☐ Rafael rodar: `sudo apt remove -y blender` (remove o 4.0.2 redundante;
  o projeto usa o 5.2 do Flatpak).
- ☐ Quando o app estiver maduro: cadastrar a biblioteca real do SSD como
  segunda library (o caminho é configuração, nunca hardcoded).

### ☑ Fatia 53 — biblioteca que muda de ponto de montagem (o app acha sozinho)
Rafael relatou em 2026-08-09: arrastar imagem pra definir preview "não
acontece nada", mesmo com o cursor mostrando "+", e **com o SSD montado**.

**O drag-and-drop estava certo** — a Fatia 52 resolveu de verdade. O log
mostra o gesto chegando inteiro ao fim: `dropEvent` → `_apply_drop` →
`_on_asset_preview_dropped`. Quebrava no passo seguinte, ao COPIAR:

    FileNotFoundError: Imagem de preview não existe:
      /media/rafael/SSD/Documentos/{cura}/.../CURA_Poltrona Calligaris_Lazy.jpg

**Causa:** o SSD é montado automaticamente e o ponto de montagem MUDA entre
sessões. Estava gravado `/media/rafael/SSD/...`; naquele dia o mesmo disco
apareceu em `/mnt/284A670E4A66D7D8/...` (`lsblk`: `sdb1 LABEL=SSD` montado
em `/mnt/<uuid>`, e `/media/rafael/` vazio). É a MESMA classe de problema
do "achado à parte" da Fatia 52 — só que ali o disco estava desmontado e
aqui ele está montado em outro lugar, que é bem mais traiçoeiro: parece
tudo certo na tela.

**Por que era invisível:** a grade continua inteira (as miniaturas vêm do
cache), então nada denuncia o problema até você tentar LER um arquivo
original. E o único aviso era uma mensagem discreta no rodapé.

**Fix — `assetdeck/library_root.py` (novo):**
- `resolve(caminho)` — se o caminho não existir, procura a MESMA biblioteca
  nos pontos de montagem do sistema (`/media/<user>/*`, `/run/media/<user>/*`,
  `/mnt/*`), casando o FINAL do caminho. Vence o sufixo mais longo que
  existir (quanto mais pedaços batem, menor a chance de coincidência).
- `repoint(conn, antiga, nova)` — grava a raiz nova em `libraries.root_path`.

**Os DOIS lugares têm de mudar juntos** (config.json + `libraries.root_path`):
só o config faria `libraries.get_or_create` criar uma library NOVA e vazia,
e os 72 mil assets do Rafael sumiriam da grade. `assets.rel_path` é
relativo, então nada mais precisa mudar.

**Na abertura (`app._confirmar_biblioteca`)**, depois do `QApplication` e
antes da janela:
- achou em outro lugar → pergunta "quer que eu passe a usar o caminho novo?"
  e reaponta os dois lugares no "Sim";
- não achou em lugar nenhum → avisa (disco desconectado?) e oferece escolher
  a pasta;
- `--screenshot` → só loga e segue (diálogo modal travaria a captura).

9 testes novos (`tests/test_library_root.py`), incluindo o caso real do
Rafael e ponto de montagem ilegível (disco removido no meio do caminho não
pode derrubar a abertura do app).

**Fecha a "ideia de melhoria que ficou de fora" registrada na Fatia 52.**

## F6 — Polydex + ajustes de UX/visual (a fazer)

Roadmap fechado com o Rafael em 2026-08-14, comparando com o Polydex
(importador de assets da Poliigon) e a lista de ajustes que ele levantou
usando o app. Plano completo com arquivo:linha de cada item em
`/home/rafael/.claude/plans/ok-coisas-que-achei-iterative-barto.md`. Ordem:
baratos primeiro, depois médios, depois as fatias grandes (multi-biblioteca,
visualizador 3D, redesenho de menu/barra superior).

### ☑ Fatia 59 — Nome do asset cortado no card
Rafael relatou: nomes grandes não cabiam no card e não dava pra saber o
nome (texto centralizado, cortava sem aviso — nem o começo nem o fim
completos). Trocado `_paint_name()`
(`assetdeck/ui/asset_card_delegate.py`) de centralizado + quebra em até 2
linhas para **alinhado à esquerda, 1 linha, com reticências** no que não
couber (`QFontMetrics.elidedText`). Continua verticalmente centrado no
espaço reservado (`NAME_HEIGHT`, sem mudar — não mexe na geometria do
card).

**Achado no caminho:** o app estava com `config.json` apontando pra
biblioteca REAL do Rafael (419GB, 50 mil assets) em vez da testlib —
sobra de sessão anterior, contra a regra do `CLAUDE.md`. Reapontado pra
`assetdeck-testlib` antes de qualquer teste. Confirmado com ele que era
sobra, não intencional.

**Deu certo quando:** testado contra a testlib real (`MT_PM_V148_
Acoelorrhaphe_wrig...`) — nome aparece alinhado à esquerda com "…" no
corte, em vez de cortar/quebrar sem aviso. 758 testes verdes (4 falhas
pré-existentes, sem relação com esta fatia — testes de render/textura que
dependem do Blender de verdade, ambiente sem Blender funcional agora).

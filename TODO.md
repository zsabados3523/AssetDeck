# TODO.md — Roadmap e estado atual

## Estado atual (2026-08-01)

**F0, F1 e F2 completos.** 16 fatias entregues e validadas pelo Rafael na
tela dele.

| | |
|---|---|
| Testes | 215 verdes (`pytest -q`) |
| Schema | migrations 001–005 aplicadas (ver SCHEMA.md) |
| Biblioteca de trabalho | testlib: 750 arquivos → 391 assets → **127 visíveis** (dependências ocultas) |
| Add-on do Blender | v0.4.0, Blender 5.2 Flatpak |

**F3 completa** (Fatias 17–23 + fixes da 17b/19b). Batch rename já mergeado
na `main`; falta o Rafael confirmar na tela a branch
`fatia-19b-drag-ghost-fix` (fix do arrasto + reset da Smart Collection),
que contém TUDO. Depois disso: F4 é opcional e fica para uma próxima
conversa (decisão dele).

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

### ☐ Fatia 17 — Collections manuais  ← **COMEÇAR AQUI**
As tabelas `collections` e `collection_items` existem desde o schema v1 e
nunca ganharam UI. Painel lateral (junto de pastas e tags), criar / renomear /
excluir, arrastar assets para dentro, subpastas de coleção, ordem manual.
**Reusar:** `ui/tag_tree.py` (o drag-and-drop com `MIME_ASSETS` já funciona)
e `db/repos/tags.py` (hierarquia, soft delete, `descendants`).
**Deu certo quando:** criar "Projeto Casa X", arrastar 5 assets, clicar nela
e ver só esses 5; fechar e reabrir mantém tudo.

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

### ☑ Fatia 19b — Bug: "fantasma" preso ao arrastar um asset
Causa confirmada em `ui/asset_grid.py`: `AssetGridView.dropEvent` caía em
`super().dropEvent(event)` quando o drop não tinha alvo válido dentro da
própria grade (caminho morto, o modelo não usa `InternalMove`) — trocado
por `event.ignore()` + `self.viewport().update()`. O `startDrag`
customizado da Fatia 17b também passou a forçar `self.viewport().update()`
depois do `drag.exec(...)`.
**Deu certo quando:** arrastar um asset e soltar em espaço vazio da própria
grade faz o card voltar limpo pro lugar de origem, sem cópia grudada.

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

## F4 — Opcional
Auto-tagging local via Ollama (Qwen2.5-VL 7B) · checagem seamless/tileable ·
render de previews em lote com cena de estúdio configurável · busca por cor
dominante · listar texturas faltando de um .blend · múltiplas bibliotecas na UI.

---

## Pendências fora do código
- ☐ Rafael rodar: `sudo apt remove -y blender` (remove o 4.0.2 redundante;
  o projeto usa o 5.2 do Flatpak).
- ☐ Quando o app estiver maduro: cadastrar a biblioteca real do SSD como
  segunda library (o caminho é configuração, nunca hardcoded).

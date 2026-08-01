# TODO.md — Roadmap e estado atual

## Estado atual (2026-08-01)

**F0, F1 e F2 completos.** 16 fatias entregues e validadas pelo Rafael na
tela dele.

| | |
|---|---|
| Testes | 189 verdes (`pytest -q`) |
| Schema | migrations 001–005 aplicadas (ver SCHEMA.md) |
| Biblioteca de trabalho | testlib: 750 arquivos → 391 assets → **127 visíveis** (dependências ocultas) |
| Add-on do Blender | v0.4.0, Blender 5.2 Flatpak |

**Próximo passo: F3 — Fatia 21 (Busca booleana + substring).**

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

### ☐ Fatia 19b — Bug: "fantasma" preso ao arrastar um asset
Relatado pelo Rafael com print: arrastar um card na grade às vezes deixa
uma cópia dele "presa" visualmente no lugar onde o mouse soltou, em vez de
ele voltar pro lugar de origem (o dado no banco não muda, é só visual).
**Suspeita já investigada, pronta pra quando entrar esta fatia:**
`AssetGridView.dropEvent` (`ui/asset_grid.py`) cai em
`super().dropEvent(event)` quando o drop não tem alvo válido dentro da
própria grade — caminho morto, já que o modelo não usa
`InternalMove` (não há reordenar por drop). É provável que esse caminho
deixe a view num estado de repaint inconsistente. O `startDrag` customizado
da Fatia 17b (mesmo arquivo) também nunca força `self.viewport().update()`
depois do `drag.exec(...)`. Fix provável: trocar o fallback por
`event.ignore()` + `self.viewport().update()`, e forçar o mesmo update ao
final do `startDrag` customizado.
**Deu certo quando:** arrastar um asset e soltar em espaço vazio da própria
grade (ou em qualquer lugar sem soltar de fato) faz o card voltar limpo
pro lugar de origem, sem nenhuma cópia grudada na tela.

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

### ☐ Fatia 21 — Busca booleana + substring
Operadores E/OU/NÃO. Inclui a limitação encontrada na Fatia 12: hoje
"quartzite" NÃO acha "StoneQuartziteTile", porque o FTS5 casa por início de
palavra.

### ☐ Fatia 22 — Custom properties na UI
EAV tipado (`property_defs` / `property_values`) existe desde o v1, sem UI.
Campos que o Rafael inventa depois (Fornecedor, Licença…).

### ☐ Fatia 23 — Batch rename
**Por último de propósito:** é a única exceção ao somente-leitura. Exige
pré-visualização e confirmação explícita antes de tocar em qualquer arquivo.

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

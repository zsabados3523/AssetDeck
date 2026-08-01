# SCHEMA.md — Modelo de dados do AssetDeck (fonte da verdade)

**Versão do schema: 2**

| Migration | O que fez |
|---|---|
| 001_initial.sql | Schema v1 completo (Fatia 1) |
| 002_group_locked.sql | `assets.group_locked` — trava de agrupamento corrigido à mão (Fatia 6) |
| 003_hidden.sql | `assets.hidden` — imagem usada como preview de modelo pode ser ocultada da grade (Fatia 10b) |
| 004_dependency.sql | `assets.is_dependency` — texturas que acompanham um .blend/.fbx irmão (detecção automática) (Fatia 13) |
| 005_phash.sql | `files.phash` — dHash (64 bits) para achar a mesma textura em resoluções/formatos diferentes; NULL para não-raster (Fatia 20) |

## Regra de ouro
Toda mudança aqui = **nova migration** (nunca editar uma antiga) + **avisar o
Rafael antes**. O banco guarda a versão aplicada; o app migra sozinho ao abrir.

## As duas ideias centrais

**1. Asset ≠ arquivo.** Um *asset* é a "coisa" que você procura (a textura
"Concreto Rústico"); os *arquivos* são os pedaços físicos dela (os 6 mapas
PBR). Por isso existem duas tabelas separadas, `assets` e `files`.

**2. Identidade estável.** Cada asset ganha um `uuid` — um código único que
NUNCA muda, mesmo que você renomeie ou mova as pastas. Quando um arquivo some
do lugar esperado, o app procura pelo `content_hash` (impressão digital do
conteúdo) e religa sozinho. O sidecar `.json` também carrega o uuid: se você
mover a pasta com o `.json` junto, a religação é imediata.

---

## Tabelas

### `schema_migrations`
Histórico de versões do banco: qual migration foi aplicada e quando.
É o que permite evoluir o schema sem nunca corromper dados antigos.

| coluna | tipo | descrição |
|---|---|---|
| version | INTEGER PK | número da migration (1, 2, 3…) |
| name | TEXT | nome do arquivo aplicado |
| applied_at | TEXT | data/hora da aplicação |

### `libraries`
Cada linha é uma raiz de biblioteca. Hoje só a testlib; a de 650GB no SSD
entra como segunda linha no futuro (múltiplas bibliotecas já suportadas).

| coluna | tipo | descrição |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT NOT NULL | ex.: "Testlib" |
| root_path | TEXT NOT NULL UNIQUE | caminho absoluto da raiz |
| created_at / updated_at / deleted_at | TEXT | soft delete como em tudo |

### `assets` — a unidade lógica
Uma linha = uma "coisa" da sua biblioteca: um set PBR inteiro, um HDRI, um
modelo, um cutout. Ratings, favorito e notas moram aqui porque pertencem à
coisa, não a um arquivo.

| coluna | tipo | descrição |
|---|---|---|
| id | INTEGER PK | uso interno |
| uuid | TEXT NOT NULL UNIQUE | identidade estável, nunca muda |
| library_id | INTEGER NOT NULL → libraries | |
| name | TEXT NOT NULL | nome exibido (editável) |
| asset_type | TEXT NOT NULL | `texture` `pbr_set` `hdri` `cutout` `reference` `model` `scene` `vector` `ies` `lut` `psd` `other` |
| rating | INTEGER NULL, 1–5 | NULL = sem nota (diferente de nota zero) |
| starred | INTEGER NOT NULL DEFAULT 0 | favorito |
| notes | TEXT | anotações livres |
| group_locked | INTEGER NOT NULL DEFAULT 0 | 1 = agrupamento corrigido à mão; o agrupador automático não mexe mais (migration 002) |
| hidden | INTEGER NOT NULL DEFAULT 0 | 1 = oculto da grade (ex.: imagem que virou preview de um modelo); reversível via "Mostrar ocultos" (migration 003) |
| is_dependency | INTEGER NOT NULL DEFAULT 0 | 1 = textura que acompanha um .blend/.fbx irmão (mapa de um material convertido, textura de um modelo). Recalculado a cada varredura (migration 004) |
| created_at / updated_at / deleted_at | TEXT | |

### `files` — os arquivos físicos
N arquivos por asset, um deles marcado `is_primary` (o "principal": o
basecolor de um set PBR, o .blend de um modelo). `rel_path` é relativo à raiz
da biblioteca — assim a biblioteca inteira pode mudar de disco sem quebrar nada.

| coluna | tipo | descrição |
|---|---|---|
| id | INTEGER PK | |
| asset_id | INTEGER NOT NULL → assets | |
| rel_path | TEXT NOT NULL | caminho relativo à raiz da library |
| size_bytes | INTEGER NOT NULL | |
| mtime_ns | INTEGER NOT NULL | data de modificação (detecta mudanças baratas) |
| content_hash | TEXT | impressão digital do conteúdo |
| hash_algo | TEXT NOT NULL DEFAULT 'blake2b-fp1m' | algoritmo usado (permite evoluir) |
| phash | TEXT NULL | dHash (64 bits, hex) do conteúdo VISUAL — acha a mesma textura em resolução/formato diferente, onde `content_hash` não bate. Só raster; NULL para o resto (migration 005) |
| is_primary | INTEGER NOT NULL DEFAULT 0 | arquivo principal do asset |
| map_role | TEXT DEFAULT 'none' | `basecolor` `normal` `roughness` `glossiness` `height` `ao` `metallic` `specular` `opacity` `emission` `none` |
| width / height | INTEGER | resolução (imagens) |
| has_alpha | INTEGER | tem transparência? |
| bit_depth | INTEGER | 8 / 16 / 32 bits |
| missing_since | TEXT NULL | quando o arquivo sumiu do caminho (para relocalizar) |
| created_at / updated_at / deleted_at | TEXT | |

Índices: `rel_path`, `content_hash`, `asset_id`.

**Sobre o hash**: `blake2b-fp1m` = fingerprint de tamanho + primeiro 1MB +
último 1MB. Rápido mesmo em .blend de gigabytes. Se um dia precisar de hash
completo, entra como novo `hash_algo` sem quebrar nada.

### `tags` — hierárquicas
Árvore em N níveis via `parent_id` (ex.: Materiais → Madeira → Nogueira).
Cor, ícone e ordem customizada por tag.

| coluna | tipo | descrição |
|---|---|---|
| id | INTEGER PK | |
| parent_id | INTEGER NULL → tags | NULL = tag raiz |
| name | TEXT NOT NULL | UNIQUE junto com parent_id |
| color | TEXT | ex.: `#8B5A2B` |
| icon | TEXT | nome de ícone |
| sort_order | INTEGER NOT NULL DEFAULT 0 | ordem manual entre irmãs |
| created_at / updated_at / deleted_at | TEXT | |

### `tag_aliases` — sinônimos e bilíngue
Buscar "madeira" acha packs marcados "wood". Tabela separada para uma tag ter
quantos apelidos precisar.

| coluna | tipo | descrição |
|---|---|---|
| id | INTEGER PK | |
| tag_id | INTEGER NOT NULL → tags | |
| alias | TEXT NOT NULL | UNIQUE junto com tag_id |
| lang | TEXT NULL | `pt`, `en` ou NULL |

### `asset_tags` — a ligação M:N
Quem taggeou o quê. `source` distingue tag manual de tag sugerida por IA
(F4/Ollama); `confidence` guarda a certeza da IA (a UI poderá mostrar
"sugestões" separadas das suas tags).

| coluna | tipo | descrição |
|---|---|---|
| asset_id + tag_id | PK composta | |
| source | TEXT NOT NULL DEFAULT 'manual' | `manual` ou `ai` |
| confidence | REAL NULL | 0.0–1.0, só para `ai` |
| created_at | TEXT | |

### `previews` — 1:N por asset
Um asset tem VÁRIAS imagens de preview, ordenadas, com uma marcada como capa.
Nunca existirá coluna única `thumbnail_path`.

| coluna | tipo | descrição |
|---|---|---|
| id | INTEGER PK | |
| asset_id | INTEGER NOT NULL → assets | |
| file_path | TEXT NOT NULL | no cache do app OU imagem escolhida pelo usuário |
| kind | TEXT NOT NULL | `thumbnail` `image` `render` `embedded` |
| origin | TEXT NOT NULL | `auto` `user` `blender` |
| sort_order | INTEGER NOT NULL DEFAULT 0 | |
| is_cover | INTEGER NOT NULL DEFAULT 0 | no máx. 1 capa por asset (regra no app) |
| created_at / deleted_at | TEXT | |

### `property_defs` + `property_values` — campos que você inventa depois (EAV tipado)
Quer um campo "Fornecedor" ou "Licença"? Cria a definição numa tabela e os
valores na outra — sem mexer no schema. O valor vai para a coluna do tipo
certo (texto, número, sim/não ou data), nunca tudo espremido em texto.

`property_defs`:
| coluna | tipo | descrição |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT NOT NULL UNIQUE | ex.: "Fornecedor" |
| value_type | TEXT NOT NULL | `text` `number` `bool` `date` |
| created_at / deleted_at | TEXT | |

`property_values`:
| coluna | tipo | descrição |
|---|---|---|
| id | INTEGER PK | |
| asset_id | INTEGER NOT NULL → assets | UNIQUE junto com property_id |
| property_id | INTEGER NOT NULL → property_defs | |
| value_text / value_number / value_bool / value_date | um preenchido conforme o tipo | |

### `collections` + `collection_items` — listas manuais
"Projeto Casa X": você arrasta assets para dentro, na ordem que quiser.
Suporta subpastas de coleção via `parent_id`.

`collections`: id, name, parent_id → collections, sort_order, created/updated/deleted_at
`collection_items`: collection_id + asset_id (PK composta), sort_order

### `smart_collections` — buscas salvas (conceito DISTINTO)
Não guarda assets — guarda uma **query em JSON** ("tipo=hdri E rating≥4").
O resultado é calculado na hora, sempre atual.

| coluna | tipo | descrição |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT NOT NULL | |
| query_json | TEXT NOT NULL | filtros serializados |
| sort_order | INTEGER NOT NULL DEFAULT 0 | |
| created_at / updated_at / deleted_at | TEXT | |

### `assets_fts` — busca rápida (FTS5)
Tabela virtual do SQLite espelhando `assets.name` + nomes/aliases de tags do
asset. É o que faz a busca ser instantânea com milhares de itens. Mantida em
sincronia pelo app; pode ser reconstruída do zero a qualquer momento (é só
índice, não é dado).

---

## Sidecar `.json` — o espelho ao lado dos assets
Um por asset, criado ao lado do arquivo principal:
`<nome-do-arquivo-principal>.assetdeck.json`

```json
{
  "assetdeck": 1,
  "uuid": "9f3c…",
  "name": "Concreto Rústico 4K",
  "asset_type": "pbr_set",
  "rating": 4,
  "starred": true,
  "notes": "usei na fachada do projeto X",
  "tags": ["Materiais/Concreto", "Rústico"],
  "custom": {"Fornecedor": "ambientCG"},
  "files": ["ConcreteRustic_4K_basecolor.jpg", "…"]
}
```

Regras:
- O app **só cria/atualiza sidecars** — nunca toca nos seus assets.
- Escrito de forma atômica (arquivo temporário + rename) para nunca ficar pela metade.
- Na reindexação, um sidecar encontrado **restaura** os metadados para o banco
  (é o seguro contra corrupção do .db, junto com o backup rotativo diário).

## Estratégia de relocalização (resumo)
1. Rescan acha o arquivo no `rel_path` esperado com mesmo tamanho+mtime → OK.
2. Sumiu? Marca `missing_since` e procura o mesmo `content_hash` em outro
   caminho → religa e atualiza `rel_path`.
3. Pasta movida com sidecar junto → o `uuid` do `.json` religa na hora.
4. Nada encontrado → asset fica "perdido" (visível, filtrável), NUNCA apagado.

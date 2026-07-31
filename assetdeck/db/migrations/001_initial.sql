-- Migration 001 — Schema v1 completo (espelho de SCHEMA.md)
-- Regra de ouro: NUNCA editar este arquivo depois de aplicado.
-- Mudanças de schema = nova migration + aviso ao Rafael.

-- Raízes de biblioteca (múltiplas bibliotecas suportadas desde já)
CREATE TABLE libraries (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    root_path   TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT,
    deleted_at  TEXT
);

-- A unidade lógica: um asset é a "coisa" (set PBR, HDRI, modelo...),
-- não um arquivo. uuid é a identidade estável que nunca muda.
CREATE TABLE assets (
    id          INTEGER PRIMARY KEY,
    uuid        TEXT NOT NULL UNIQUE,
    library_id  INTEGER NOT NULL REFERENCES libraries(id),
    name        TEXT NOT NULL,
    asset_type  TEXT NOT NULL CHECK (asset_type IN
        ('texture','pbr_set','hdri','cutout','reference','model',
         'scene','vector','ies','lut','psd','other')),
    rating      INTEGER CHECK (rating BETWEEN 1 AND 5),  -- NULL = sem nota
    starred     INTEGER NOT NULL DEFAULT 0 CHECK (starred IN (0,1)),
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT,
    deleted_at  TEXT
);
CREATE INDEX idx_assets_library ON assets(library_id);
CREATE INDEX idx_assets_type    ON assets(asset_type);

-- Arquivos físicos: N por asset, um marcado is_primary.
-- rel_path é relativo à raiz da library (a biblioteca pode trocar de disco).
CREATE TABLE files (
    id            INTEGER PRIMARY KEY,
    asset_id      INTEGER NOT NULL REFERENCES assets(id),
    rel_path      TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL,
    mtime_ns      INTEGER NOT NULL,
    content_hash  TEXT,
    hash_algo     TEXT NOT NULL DEFAULT 'blake2b-fp1m',
    is_primary    INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0,1)),
    map_role      TEXT NOT NULL DEFAULT 'none' CHECK (map_role IN
        ('basecolor','normal','roughness','glossiness','height','ao',
         'metallic','specular','opacity','emission','none')),
    width         INTEGER,
    height        INTEGER,
    has_alpha     INTEGER CHECK (has_alpha IN (0,1)),
    bit_depth     INTEGER,
    missing_since TEXT,   -- preenchido quando o arquivo some (relocalização)
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT,
    deleted_at    TEXT
);
CREATE INDEX idx_files_asset    ON files(asset_id);
CREATE INDEX idx_files_rel_path ON files(rel_path);
CREATE INDEX idx_files_hash     ON files(content_hash);

-- Tags hierárquicas (N níveis via parent_id)
CREATE TABLE tags (
    id          INTEGER PRIMARY KEY,
    parent_id   INTEGER REFERENCES tags(id),
    name        TEXT NOT NULL,
    color       TEXT,
    icon        TEXT,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT,
    deleted_at  TEXT,
    UNIQUE (parent_id, name)
);
-- UNIQUE(parent_id, name) não pega duplicatas entre tags raiz (parent NULL);
-- este índice parcial cobre esse caso:
CREATE UNIQUE INDEX idx_tags_root_name ON tags(name) WHERE parent_id IS NULL;

-- Sinônimos e bilíngue PT/EN: "madeira" acha packs "wood"
CREATE TABLE tag_aliases (
    id      INTEGER PRIMARY KEY,
    tag_id  INTEGER NOT NULL REFERENCES tags(id),
    alias   TEXT NOT NULL,
    lang    TEXT,           -- 'pt', 'en' ou NULL
    UNIQUE (tag_id, alias)
);

-- Ligação asset<->tag, distinguindo tag manual de sugestão de IA
CREATE TABLE asset_tags (
    asset_id    INTEGER NOT NULL REFERENCES assets(id),
    tag_id      INTEGER NOT NULL REFERENCES tags(id),
    source      TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','ai')),
    confidence  REAL CHECK (confidence BETWEEN 0.0 AND 1.0),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (asset_id, tag_id)
);

-- Previews 1:N — nunca uma coluna única thumbnail_path
CREATE TABLE previews (
    id          INTEGER PRIMARY KEY,
    asset_id    INTEGER NOT NULL REFERENCES assets(id),
    file_path   TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('thumbnail','image','render','embedded')),
    origin      TEXT NOT NULL CHECK (origin IN ('auto','user','blender')),
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_cover    INTEGER NOT NULL DEFAULT 0 CHECK (is_cover IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at  TEXT
);
CREATE INDEX idx_previews_asset ON previews(asset_id);

-- Custom properties: EAV tipado (campos inventados depois, sem mexer no schema)
CREATE TABLE property_defs (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    value_type  TEXT NOT NULL CHECK (value_type IN ('text','number','bool','date')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at  TEXT
);
CREATE TABLE property_values (
    id            INTEGER PRIMARY KEY,
    asset_id      INTEGER NOT NULL REFERENCES assets(id),
    property_id   INTEGER NOT NULL REFERENCES property_defs(id),
    value_text    TEXT,
    value_number  REAL,
    value_bool    INTEGER CHECK (value_bool IN (0,1)),
    value_date    TEXT,
    UNIQUE (asset_id, property_id)
);

-- Collections manuais (listas arrastadas à mão, com subpastas)
CREATE TABLE collections (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    parent_id   INTEGER REFERENCES collections(id),
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT,
    deleted_at  TEXT
);
CREATE TABLE collection_items (
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    asset_id      INTEGER NOT NULL REFERENCES assets(id),
    sort_order    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (collection_id, asset_id)
);

-- Smart collections: buscas salvas em JSON (conceito distinto de collection)
CREATE TABLE smart_collections (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    query_json  TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT,
    deleted_at  TEXT
);

-- Busca instantânea por nome/tags (índice, reconstruível a qualquer momento)
CREATE VIRTUAL TABLE assets_fts USING fts5(name, tags, content='');

-- Migration 004 — assets.is_dependency
--
-- Texturas que vivem ao lado de um .blend/.fbx/.obj são DEPENDÊNCIAS dele,
-- não materiais avulsos: os mapas de um material Poliigon convertido em
-- .blend, ou as texturas de um modelo de vegetação. O Rafael quer ver o
-- .blend do material, não os 6 mapas soltos que o compõem.
--
-- Detectado automaticamente a cada varredura (indexer/dependencies.py) e
-- ocultável por um toggle na UI. Não é apagar: os assets continuam lá.
ALTER TABLE assets ADD COLUMN is_dependency INTEGER NOT NULL DEFAULT 0;
CREATE INDEX idx_assets_dependency ON assets(is_dependency);

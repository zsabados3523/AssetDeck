-- Migration 003 — assets.hidden
--
-- Quando uma imagem da própria biblioteca vira preview de um modelo, o
-- Rafael pode escolher OCULTÁ-LA da grade (ela vira "material de preview",
-- não um asset de interesse). Ocultar não é apagar: hidden=1 só a tira da
-- visualização padrão, e o checkbox "Mostrar ocultos" traz de volta.
ALTER TABLE assets ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0;

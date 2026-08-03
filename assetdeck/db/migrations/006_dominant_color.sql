-- Migration 006 — files.dominant_color
--
-- Cor média (RGB, em hex "#rrggbb") do arquivo, para o filtro de busca por
-- cor (Fatia 39). Calculada reamostrando a imagem para 1x1 pixel — mesma
-- ideia de "abrir uma vez só" do phash (Fatia 20/migration 005).
--
-- Calculado só para arquivos raster; NULL para HDR/EXR/modelos/vetores etc.,
-- igual width/height/phash hoje.
ALTER TABLE files ADD COLUMN dominant_color TEXT;

-- Migration 005 — files.phash
--
-- O content_hash (blake2b de tamanho + pedaços do arquivo) só pega
-- arquivos IDÊNTICOS byte a byte. Não pega a mesma textura salva de novo
-- em outra resolução ou formato — é para isso que serve o phash: um dHash
-- (difference hash) de 64 bits, robusto a mudança de tamanho/formato.
--
-- Calculado só para arquivos raster (Fatia 20); NULL para HDR/EXR/modelos/
-- vetores etc., igual width/height hoje.
ALTER TABLE files ADD COLUMN phash TEXT;
CREATE INDEX idx_files_phash ON files(phash);

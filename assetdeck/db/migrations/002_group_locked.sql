-- Migration 002 — trava de agrupamento manual
--
-- Quando o Rafael corrige um agrupamento na mão (desagrupar um set PBR ou
-- juntar assets manualmente), o resultado ganha group_locked = 1 e o
-- agrupador automático passa a respeitar a decisão dele para sempre.
ALTER TABLE assets ADD COLUMN group_locked INTEGER NOT NULL DEFAULT 0;

# TODO.md — Roadmap e estado atual

## Estado atual (2026-07-31)
- Fatias 1 e 2 concluídas e validadas pelo Rafael (740 assets da testlib
  indexados; revarredura idempotente; 27 testes verdes).
- **Em andamento: Fatia 3 — grid de thumbnails** (inclui .dwg→vector e
  .mtlx→other no mapa de extensões, a pedido do Rafael).

## Como ler este arquivo
Uma fatia por vez, em branch própria. Cada fatia termina com: pytest verde,
critério de "deu certo" verificado pelo Rafael na tela, e commit.

---

## F0 — MVP

### ☑ Fatia 1 — Esqueleto vivo (concluída 2026-07-31)
Pacote `assetdeck`, config XDG, logging, **schema v1 COMPLETO como
migration 001**, backup rotativo do .db, janela abrindo, `--screenshot`,
testes de migração.
**Deu certo quando:** `python -m assetdeck` abre uma janela "AssetDeck —
0 assets"; `pytest -q` verde; existe um backup do .db em
`~/.local/share/assetdeck/backups/`.

### ☑ Fatia 2 — Indexação em background (concluída 2026-07-31)
Scanner em thread varre a testlib e grava `files`/`assets` (1 arquivo =
1 asset por enquanto; agrupamento PBR vem na Fatia 6). Barra de progresso.
**Deu certo quando:** a janela mostra a contagem subindo até ~753 sem
congelar; fechar e reabrir mantém os dados.

### ☐ Fatia 3 — Grid de thumbnails
Thumbs de jpg/png/tif em grid virtualizada, cache em disco, painel de
detalhes (resolução, tamanho, formato, caminho), abrir pasta / abrir com app
padrão.
**Deu certo quando:** rolar a grid é fluido; segunda abertura é instantânea
(cache); clicar num asset mostra os detalhes; "abrir pasta" funciona.

### ☐ Fatia 4 — Busca e filtros básicos *(fecha o F0)*
Busca por nome via FTS5, toggle "mostrar subpastas", filtro por tipo.
**Deu certo quando:** digitar filtra em tempo real com milhares de itens.

## F1 — Vira útil

### ☐ Fatia 5 — Sidecars JSON + notas
Writer/reader do `.assetdeck.json` + primeiro metadado editável (notas),
validando o ciclo db → json → (rescan) → db.
**Deu certo quando:** editar a nota cria o .json ao lado do asset; apagar o
.db e reindexar recupera a nota do sidecar.

### ☐ Fatia 6 — Agrupamento PBR
Heurística por sufixo (_basecolor/_albedo/_diff, _rough/_gloss, _nrm/_normal,
_disp/_height, _ao, _metal, _spec), resolução no nome, padrões ambientCG/
Poliigon/Textures.com. Capa = basecolor. **Correção manual obrigatória**
(juntar/separar arquivos de um asset na mão).
**Deu certo quando:** um set de 6 mapas da testlib aparece como 1 card.

### ☐ Fatia 7 — Thumbs especiais
EXR/HDR via imageio+numpy com tonemap (gamma 2.2/Reinhard); PNG com alpha
sobre fundo xadrez.
**Deu certo quando:** HDRIs da testlib deixam de ser quadrados pretos;
cutouts mostram o xadrez.

### ☐ Fatia 8 — Tags
Hierarquia N níveis, cor/ícone/ordem, aliases PT/EN, as 3 formas de taggear
(arrastar, checkbox interativo, diálogo Ctrl+T), copiar/colar/substituir tags.
**Deu certo quando:** buscar "madeira" acha asset taggeado "wood".

### ☐ Fatia 9 — Ratings, favoritos e filtros combinados
Estrelas, starred, filtros por tipo/resolução/tag/rating combináveis.

### ☐ Fatia 10 — Previews customizados *(fecha o F1)*
Drag-and-drop de imagem sobre o card define preview; galeria 1:N com capa.

## F2 — Blender (fatias 11–15)
Socket localhost + add-on para **Blender 5.2 Flatpak** · arrastar set PBR →
node group montado · arrastar HDRI → World · import .fbx/.obj/.blend
(link e append) · salvar seleção da cena de volta → biblioteca · thumbs de
modelo via render headless (`flatpak run org.blender.Blender -b -P`).
**Risco a verificar antes:** permissões do sandbox Flatpak
(`flatpak info --show-permissions org.blender.Blender`).

## F3 — Power user
Galeria múltipla por asset · auto-assign de previews por padrão de nome em
lote · Smart Collections · custom properties na UI · duplicados por
perceptual hash · batch rename (com confirmação explícita — única exceção ao
somente-leitura) · relocalizar assets perdidos · busca booleana · tag aliases
na UI.

## F4 — Opcional
Auto-tagging local via Ollama (Qwen2.5-VL 7B) · checagem seamless/tileable ·
render de previews em lote com cena de estúdio configurável · busca por cor
dominante · texturas faltando de um .blend · múltiplas bibliotecas na UI.

---

## Pendências fora do código
- ☐ Rafael rodar: `sudo apt remove -y blender` (remove o 4.0.2 redundante).
- ☐ Quando o app estiver maduro: cadastrar a biblioteca real do SSD como
  segunda library.

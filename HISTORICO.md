# HISTÓRICO.md — a conversa do AssetDeck, compactada

Compilado em **2026-08-28**, relendo as ~15 conversas do projeto (grupo
"Asset Deck" + worktrees) do começo ao fim. É um mapa: a narrativa, as
decisões e o porquê delas, os becos sem saída, as armadilhas que voltam
sempre, e o que atravessa mais de uma sessão. O detalhe fatia a fatia
continua no `TODO.md` (3800+ linhas, é o diário); o modelo de dados no
`SCHEMA.md`; o visual no `REDESIGN.md`/`REDESIGN-V2.md`. Aqui é o resumo
de tudo isso junto, mais o que não estava escrito em lugar nenhum.

---

## 1. O que é o AssetDeck

DAM (Digital Asset Manager) local de assets 2D/3D para Linux, inspirado no
**Connecter** (Windows), integrado ao **Blender 5.2**. Uso pessoal do
Rafael (arquiteto/archviz), **100% offline**, sem conta, sem nuvem, sem
telemetria. Começou em **2026-07-31**.

Os cinco requisitos inegociáveis (de `PROJECT.md`):
1. **Somente-leitura sobre a biblioteca.** Hoje com três exceções, todas
   pedidas explicitamente pelo Rafael e iniciadas por ele: criar sidecars
   `.json`, `batch_rename` (Fatia 23) e `mover` (Fatia 85).
2. **Metadados em SQLite (WAL) + espelho `.json` ao lado dos assets**, com
   backup rotativo diário. Motivo: o Connecter corrompia bibliotecas sem
   recuperação — o medo de perder metadados é a razão de metade das
   decisões de arquitetura.
3. **100% offline** — matou a `imageio` (baixa binário em runtime).
4. **UI nunca congela** — indexação em thread/processos, cache de thumbs.
5. **Soft delete em tudo** (`deleted_at`) — nada é apagado de verdade.

Ideia central do schema: **asset ≠ arquivo**. Um *asset* é a "coisa" que
você procura (a textura "Concreto Rústico"); os *arquivos* são os pedaços
(os 6 mapas PBR). Duas tabelas, `assets` e `files`. Cada asset tem um
`uuid` estável que nunca muda; quando um arquivo some, o app religa pelo
`content_hash`.

---

## 2. Estado atual (2026-08-28) — leia antes de mexer

| | |
|---|---|
| **Onde o código vive** | `/home/rafael/00 - PROJETOS/assetdeck-correcoes` (worktree isolado na `main`). A pasta original `assetdeck` está com **HEAD solta de propósito** no commit da Fatia 51b (`a099248`) — TODO.md de lá está velho (para na Fatia 53). Há ainda worktrees `assetdeck-fatia97/98/101` para fatias em revisão. |
| **Última fatia na `main`** | **Fatia 102** — capa com fundo transparente + 3-point lighting + Cycles (`837d599`, 2026-08-27). |
| **Testes** | ~950 verdes. As "4-5 falhas de ambiente do Blender" que assombraram meses foram resolvidas na Fatia 102 (faltava `--factory-startup` em `missing_textures.py`). |
| **Schema** | migrations 001–006 aplicadas (ver `SCHEMA.md`). |
| **Biblioteca de dev** | `/home/rafael/00 - PROJETOS/assetdeck-testlib` — **NUNCA apontar para outra** (regra do `CLAUDE.md`). Existe um `assetdeck-testlib.tar.zst` (~4GB) de backup ao lado. |
| **Biblioteca real** | Mudou de lugar 3 vezes durante o projeto. Hoje: `/mnt/sdb1/Documentos/{cura}/BIBLIOTECA {CURA}/BIBLIOTECA {CURA}/` — ~13k `.blend`, ~53k assets, ~28k pastas, disco a 95%. O `{cura}` e o `BIBLIOTECA {CURA}` duplicado **são de propósito** (Rafael confirmou 2x). |
| **Blender** | Instalação **nativa/portátil** em `~/Apps/blender-5.2.0-linux-x64/` (lançada por `~/.local/bin/blender`). **Não é mais Flatpak** — trocado em 2026-08-10. O perfil dele tem V-Ray 7.40 e EasyHDRI instalados, que travam o Blender headless — por isso todo comando usa `--factory-startup`. |
| **Banco de dev sujo** | `~/.local/share/assetdeck/assetdeck.db` tem 72k+ assets órfãos da biblioteca real (`library_id=2`), sobra de testes de 2026-08-04. Rafael pediu para **não limpar**. A Fatia 69 isolou grade/pastas/contagens por biblioteca ativa; sobra vazamento cosmético no checklist de extensões. |

**Fases concluídas:** F0 (MVP) · F1 (útil) · F2 (Blender) · F3 (power
user) · F4 (redesign visual v1) · F5 (v2.0) · F6 (Polydex + UX). **F7**
(revisão visual ao vivo — Fase 7 do roadmap F6) está no meio.

---

## 3. Linha do tempo por fases

### F0 — MVP (Fatias 1–4, 2026-07-31)
Esqueleto vivo: pacote, config XDG, logging, schema v1 como migration 001,
backup rotativo, `--screenshot`. Indexação em thread idempotente
(`missing_since`, nunca apaga). Grid de thumbs com cache por
`content_hash`. Busca FTS5 (prefixo, sem acento), árvore de pastas,
**rolagem suave** (que voltou a quebrar duas vezes depois — Fatias 14/15).

### F1 — Vira útil (Fatias 5–10b)
Sidecars `.json` (apagar o banco e reindexar recupera tudo). Agrupamento
PBR (127 sets na testlib) com correção manual travável (**migration 002**,
`group_locked`). HDR/EXR tonemapado (Reinhard). Tags hierárquicas N níveis
com cor e aliases PT/EN ("madeira" acha "wood"). Ratings/favoritos/edição
em massa. Previews customizados por drag (**migration 003**, `hidden`).

### F2 — Blender (Fatias 11–16)
Ponte socket 127.0.0.1 + token, add-on instalado pelo próprio AssetDeck.
Decisão-chave (sugestão do Rafael): **o add-on é ponte, não importador** —
arrastar do AssetDeck aciona o menu nativo do Blender; o add-on só
acrescenta o que o Blender não faz (HDRI→World, material PBR, "& Place").
Detecção de **dependências** (texturas que acompanham um `.blend` irmão →
**migration 004**, `is_dependency` — ocultas por padrão porque o fluxo do
Rafael converte cada material num `.blend` e ele quer ver o `.blend`, não
os 6 mapas). Render headless de capas com enquadramento automático +
relocalização de texturas (packs Maxtree vêm com caminhos quebrados —
renderizavam magenta).

### F3 — Power user (Fatias 17–23)
Collections manuais + Smart Collections (query em JSON, sempre recalculada).
Relocalizar assets perdidos (`relocator.py`, revisão manual, nunca fusão
automática). Duplicados por perceptual hash (**migration 005**, `phash`).
Busca booleana E/OU/NÃO + substring (`LIKE` como reforço do FTS para
"quartzite" achar "StoneQuartziteTile"). Custom properties na UI (EAV
tipado, já existia no schema). **Batch rename** — a primeira exceção ao
somente-leitura, formato perguntado ao Rafael antes de programar.

### F4 — Redesign visual v1 (Fatias 24–30, + executável)
Três rodadas de correção vendo na tela. **O que morreu:** fundo lavanda
(pesado), fundo "vidro fosco" (não há o que borrar entre dois brancos, e o
blur do Qt borra o próprio conteúdo), seleção em barra sólida colorida
(dominava a tela), **ícone por tag** (Fatia 29 — descartada, tag continua
só por cor). **O que ficou:** tema claro estilo Craft — fundo branco liso,
cartões brancos separados por contorno quase invisível + sombra discreta,
**monocromático** (cor só em tag e no chip de extensão), Inter só com
variação de peso, cantos 8px, reconhecimento do tipo de asset **por texto**
(chip `.FBX`/`.EXR`), não por cor. Regra nova e permanente:
**nenhum `setStyleSheet` fora de `ui/theme.py`** (tudo vira token → `$nome`
no `theme.qss`; há teste proibindo cor literal). Executável: `.desktop` em
`~/.local/share/applications/`, ícone próprio (cubo isométrico escolhido
pelo Rafael), `setDesktopFileName`/`StartupWMClass` para o dock casar a
janela. **Tag `alpha-1.0`** marcada em `d6f7135` (2026-08-02).

### F5 — v2.0 (Fatias 31–53)
Barra de categorias estilo Connecter (6 botões com ícone+rótulo+contador; a
1ª tentativa — botão só de ícone — foi reprovada na tela). Navegação de
pastas com histórico. 26 ícones de tag desenhados à mão. **Visualizador
HDRI/EXR em OpenGL** (dois modos: ambiente e esfera de reflexo; viabilidade
medida antes, sem dependência nova). Templates de tags de
Arquitetura/Visualização (3 níveis, o mesmo tronco podado). Barra de menus
(Arquivo/Editar/Ferramentas/Configurações/Janela). Compatibilidade
Revit/SketchUp/USD/Alembic (só catalogar, 7 linhas no `EXT_MAP`). Render em
lote com cena configurável. **Busca por cor dominante** (**migration 006**,
`dominant_color`; `color_distance` como função SQL customizada). Listar
texturas faltando de um `.blend`. **Redesign visual v2** (Fatias 43–50) —
ver §4. **A saga do drag-and-drop** (Fatias 44/51/52) — ver §6. Biblioteca
que muda de ponto de montagem: o app acha sozinho (`library_root.py`).

### F6 — Polydex + ajustes de UX/visual (Fatias 54–102)
Roadmap fechado 2026-08-14 comparando com o **Polydex** (importador da
Poliigon, só Windows) + lista grande de ajustes do Rafael usando o app.
Ordem: baratos → médios → grandes → revisão visual ao vivo por último.

- **Fase 1 (baratos):** nome do card elidido, cantos do preview recortados
  de verdade (era só contorno), badge de "tem tag", **remover as 5 estrelas
  de nota** (só UI, schema intacto), ordenar assets.
- **Fase 2 (comportamento):** reindexação menos redundante, preview/HDRI
  "sem piscar" (idas e vindas — ver §6).
- **Fases 3–4:** barra superior de 4 faixas → 2, **janela única de
  configurações** (`SettingsWindow`, 6 categorias, era 5 menus de topo).
- **Fase 5 (múltiplas bibliotecas):** import pro Blender automático
  (`.blend` importa direto, Shift traz o menu antigo; **Link, não Append** —
  escolha do Rafael; objeto linkado vem embrulhado num Empty local para dar
  pra mover). Grade/pastas/contagens filtram pela biblioteca ativa
  (Fatia 69). **Seletor de biblioteca** na UI (Fatia 70) — trocar de
  biblioteca **fecha e reabre o app**, de propósito.
- **Fase 6 (visualizador 3D):** POC só `.obj` (Fatia 71) → `.fbx` (via
  `assimp-py`, não `pyassimp` que está quebrado no 3.12) e `.blend` (o
  próprio Blender headless exporta `.obj`, cacheado por `content_hash`).
- **Fase 7 (revisão visual ao vivo, Fatias 73+):** cor de destaque **azul →
  laranja** (`#B8460D`/`#FF8A4C`), raio maior, **sombra do card removida de
  vez** depois de 3 rodadas (o `QListView` recorta a pintura na célula;
  sombra suave precisa vazar; engordar a célula custa assets por tela —
  virou mudança de cor de fundo do card). Feedback de verdade nos controles
  (o Qt **não anima QSS**). Painel de detalhes com seções recolhíveis
  (mockup aprovado antes). Visualizadores 3D numa casca só
  (`ViewerWindow`). Muitos ajustes pós-uso real na biblioteca dele.

**Fatia 102** é a última na `main`: capa com fundo transparente (PNG RGBA),
3-point lighting (só quando o `.blend` não traz luz), **Cycles** em vez de
EEVEE (pedido explícito). De quebra, achou a causa das "falhas de ambiente"
do Blender: `missing_textures.py` sem `--factory-startup`.

---

## 4. Decisões estruturais e o porquê

| Decisão | Escolha | Por quê |
|---|---|---|
| GUI | PySide6 6.11 (Qt) | Nativo Linux, grid aguenta milhares de itens |
| Banco | SQLite WAL | Zero servidor, leitura concorrente com escrita |
| Sidecar `.json` ao lado do asset | Sim, atômico (tmp+rename) | Se o `.db` morrer, os metadados sobrevivem junto dos arquivos. **Formato 2** (Fatia 45): `tags` guarda a cadeia inteira com cor/ícone de cada elo, senão reindexar devolvia tag cinza |
| EXR/HDR | OpenCV (`.hdr`) + bindings oficiais OpenEXR (`.exr`) | Pillow não lê HDR; **imageio descartada** (baixa binário em runtime) |
| Blender alvo | 5.2, **portátil** (era Flatpak até 2026-08-10) | É o que o Rafael usa; o 4.0.2 do apt foi descartado |
| Layout da grid | `SinglePass` + `uniformItemSizes` + `Movement.Static` | Em lotes o scrollbar descobria o tamanho tarde e a rolagem saltava (Fatia 15). `Static` corrigiu o card que ficava preso (Fatia 19b) — e causou o bug de drag da Fatia 52 |
| Add-on | Ponte, não importador | Sugestão do Rafael no F2 |
| Cor de destaque | Monocromático (F4) → azul (v2) → **laranja** (F7) | Rafael sempre escolhe **vendo mockup da janela inteira**, nunca no abstrato — ver §8 |
| Múltiplas bibliotecas | `libraries` no schema desde o v1; UI só na Fatia 70 | Trocar de biblioteca reindexando é aceitável; reabrir o app é o preço (decisão dele) |
| Import no Blender | Link, não Append | Append incha o arquivo numa biblioteca grande; Link quebra se o disco remontar noutro ponto — o Empty local resolve o "não dá pra mover linkado" |
| Varredura | 4 processos (`spawn`), 1 thread de OpenCV cada, `nice 10` | 8 processos pioravam (I/O do disco externo); 16 threads de OpenCV por processo afogavam a máquina (Fatia 91) |

---

## 5. O que foi avaliado e morreu (não re-perguntar)

- **Fundo lavanda / vidro fosco / seleção em barra colorida** (F4) — Rafael
  reprovou na tela.
- **Ícone por tag** (Fatia 29) — tag continua identificada só por cor.
- **Auto-tagging por IA / checagem seamless-tileable** — tirados da lista
  do v2.0 por decisão dele (as tabelas `asset_tags.source='ai'` e
  `confidence` no schema são resquício disso).
- **Mover asset para outra categoria arrastando** (F3) — Tag/Collection já
  resolve reclassificar; mover arquivo físico é do gerenciador do sistema.
- **Nota (rating) de 5 estrelas** — removida da UI na Fatia 62 (schema,
  sidecar e protocolo da ponte mantidos).
- **Trigram tokenizer no FTS** — resolveria o "substring" sozinho, mas
  quebra insensibilidade a acento e termos curtos ("4k"/"2k").
- **Decodificar imagem em resolução reduzida para acelerar o phash**
  (Fatia 86) — mudaria o phash e quebraria o agrupamento de duplicados
  (igualdade exata, sem tolerância).
- **Diálogos com cantos arredondados** — testado e revertido; a barra de
  título do gerenciador de janelas deixa costura feia.
- **Visualizador 3D/HDRI embutido (overlay) em vez de janela própria** —
  tentado e revertido no mesmo dia (Fatia 65): um `QOpenGLWidget` em
  qualquer lugar da árvore de uma janela muda o modo de composição da
  **janela inteira** na 1ª aparição → o app todo piscava. `PreviewPopup`
  (sem OpenGL) pôde virar overlay; os visualizadores 3D não.
- **Link de compartilhamento pro cliente comentar** (no ClientDeck, §7) —
  esbarra no "100% offline"; Rafael quer pensar numa 3ª opção.

---

## 6. Armadilhas técnicas que voltam sempre

### Qt
- **Subclasse de `QWidget` filha ignora `background` do QSS** sem
  `WA_StyledBackground`.
- **`QListView::item` no QSS mata a rolagem.** `url()` no QSS precisa de
  caminho absoluto.
- **Estilizar `QTreeView::branch` faz o Qt voltar ao azul padrão dele** e
  some com as setas de expandir. A pastilha arredondada na árvore teve que
  ser pintada pela própria view em `drawRow` (rect = linha inteira), depois
  de várias tentativas (Fatias 43, 51b, 78).
- **`border-radius` maior que METADE da altura → o Qt descarta a regra
  inteira em silêncio** e o botão volta a ser retângulo. Pegou 3 vezes
  (Fatias 76, 78, 79b, 95). Medir a altura real e travar em teste.
- **Widgets que pintam cor em Python não passam pelo QSS.** Todo widget
  novo que tinge algo precisa de `refresh_theme()` e entrar em
  `MainWindow._refresh_theme_dependent_widgets()` — senão o modo escuro /
  troca de tema fica pela metade.
- **O Qt não anima QSS** (não existe `transition`). Só o delegate do card,
  pintado à mão, tem animação de verdade.
- **`setCornerWidget` não transfere posse no PySide** — guardar referência
  em `self` ou o widget é coletado.
- **`QAction.menu()` chamado 2x na mesma comprehension** aciona bug do
  shiboken ("Internal C++ object already deleted").
- **Luminância relativa satura perto do preto** — usar `contrast_ratio()`,
  não diferença de luminância, para medir degrau entre dois tons escuros.
- **Nenhuma fonte da máquina tem o glifo ★** (medido com `QRawFont`) — daí
  os ícones SVG desenhados à mão.
- **`prewarm_gl_viewers()`** (fix do "piscar") causou 3 regressões próprias:
  janela não maximizava (Fatias 83, 94, 97), visualizador abria minimizado
  (`hide()` marca a janela como iconificada no X → `WA_DontShowOnScreen`,
  Fatia 93), e ~2s a mais na abertura (Fatia 83 mediu).

### Testes / verificação
- **`--screenshot` usa `win.grab()`** — repinta o widget, **não passa pelo
  compositor**. Não serve para conferir sombra, máscara, cantos
  arredondados nem decoração de janela. Para o que o Rafael vê:
  `QApplication.primaryScreen().grabWindow(0)` com o app aberto de verdade,
  ou XTEST/libXtst com mouse real.
- **`grab()` de um widget isolado não mostra o fundo do app.** Teste de
  canto arredondado tem que grabar a JANELA e comparar a quina com o meio
  da aresta.
- **Validar efeito de card na GRADE montada, nunca num card isolado** —
  vizinho e recorte de célula são o que quebra (Fatia 74).
- **Headless não força `:hover` num `QPushButton`** (`QToolButton` aceita,
  `QPushButton` não). Medir o pixel, não confiar no olho.
- **`QOpenGLWidget` derruba o processo no modo offscreen do pytest** — a
  matemática (câmera etc.) mora fora do widget de propósito, coberta pelo
  pytest normal; o render se confere com `DISPLAY=:0` + `.grab()`.
- **`processEvents()` sozinho nunca despacha `DeferredDelete`** — o fixture
  `qt_settle` no `conftest.py` faz o flush escopado por widget (escopar por
  `None` causava segfault na suíte inteira). Cortou a suíte pela metade.
- **Teste de token tem que enumerar TODOS os widgets que consomem o token**,
  não uma amostra (Fatia 79b: o teste passou com o bug vivo).
- **Arrasto testado sem mouse real não prova nada** (regra desde a Fatia
  52) — os testes entregavam o evento na mão para a view, pulando o
  viewport quebrado, e passavam verdes com o app 100% surdo.
- **`bridge_port` fixo (45017)** fazia o teste falhar com o app do Rafael
  aberto — a fixture usa porta 0.

### A saga do drag-and-drop (Fatias 19b → 44 → 51 → 52)
Arrastar imagem para definir preview "não funcionava". Investigado por
sessões, com 2 diagnósticos errados no caminho. **Causa real (Fatia 52,
uma linha):** `setMovement(Static)` (adicionado na 19b para o card não
ficar preso) faz o Qt chamar `viewport()->setAcceptDrops(false)` — e quem
recebe o arrasto do sistema é o **viewport**, não a view. O
`setAcceptDrops(True)` da view só propaga quando o valor MUDA. Fix:
`self.viewport().setAcceptDrops(True)` explícito depois do `setMovement`.
O "fallback por posição do cursor" da Fatia 51 foi removido (era perigoso —
aplicava preview em drag cancelado ou solto no Blender por cima). **Duas
das idas e vindas foram porque o SSD estava desmontado / remontado noutro
ponto**, não bug do app — o que motivou o `library_root.py` (Fatia 53) e a
Fatia 100 (aviso de "N sumidos" no rodapé).

### Blender
- **O Flatpak tem `/tmp` próprio** — scripts/renders têm que ficar em
  `~/.cache/assetdeck` ou `~/.local/share/assetdeck` (vale para testes:
  `tmp_path` do pytest não serve para integração com o Blender).
- **Caminhos de script têm que ser absolutos** (relativo resolve contra
  `/app/blender` no sandbox).
- **`--factory-startup` é obrigatório** em toda chamada headless — o perfil
  do Rafael (V-Ray, EasyHDRI) trava o processo ao encerrar. Faltou em
  `missing_textures.py` até a Fatia 102 e era registrado como "falha de
  ambiente inevitável" desde a Fatia 90.
- **`bpy.data.images.new()` sem religar a material some silenciosamente ao
  salvar** — precisa de `use_fake_user = True` (senão o teste de integração
  dá falso-negativo).
- Packs Maxtree: `.blend` aponta para subpasta quando os mapas estão numa
  pasta IRMÃ → render relocaliza em memória (arquivo do usuário intocado).

---

## 7. Eventos que atravessam sessões

- **Flatpak → Blender portátil (2026-08-10).** Rafael trocou. O
  `installer.py` só procurava `~/.var/app/org.blender.Blender/...`; passou a
  procurar `~/.config/blender` também. A correção ficou numa branch não
  mergeada e foi trazida via cherry-pick na Fatia 68. `CLAUDE.md` e
  `PROJECT.md` atualizados.
- **Add-on V-Ray Cosmos → Cycles.** Projeto SEPARADO que nasceu de dores do
  Rafael com V-Ray/Cosmos travando o Blender headless do AssetDeck. Mora em
  `Blender Addons/Vray Converter` (fora do repo do AssetDeck). A sessão
  "Plugin Blender Vray para Cycles" (2026-08-28) é debug de instalação
  desse add-on (o instalador derramava arquivos soltos em `addons/` em vez
  de criar `vray_blender/`, e como `root`). **Não confundir com o
  AssetDeck.** Ver memória `vray-cosmos-addon-proximos-passos`.
- **Chaos Cosmos.** ~6.475 modelos em `~/Documentos/CHAOS COSMOS`, cada
  `.blend` com `previews/` (`_01`, `_02`, alguns com nome de hash) e
  `textures_cache/`. Motivou as Fatias 81/84 (preview por nome alcançando
  pasta irmã e subpasta) e 85 (mover a PASTA do asset, não o arquivo). Foi
  o que cruzou o limite O(n²) da contagem da lateral (Fatia 87, ~28k
  pastas → app não abria).
- **A biblioteca real e o ponto de montagem.** Mudou de
  `SSD externo NTFS` → `/media/rafael/SSD` → `/mnt/284A.../` (uuid) → hoje
  `/mnt/sdb1/...`. O ponto de montagem MUDA entre sessões. `library_root.py`
  (Fatia 53) procura a mesma biblioteca nos pontos de montagem do sistema
  casando o final do caminho, e reaponta config.json + `libraries.root_path`
  juntos (só o config faria os 72k assets sumirem da grade).
- **testlib.** `/home/rafael/00 - PROJETOS/assetdeck-testlib` (4GB, 750
  arquivos → 391 assets → 127 visíveis). Backup em `assetdeck-testlib.tar.zst`.
  Várias vezes o `config.json` amanheceu apontando para a biblioteca real
  (sobra de sessão) — sempre reapontado antes de testar (regra do CLAUDE.md).
- **Worktrees.** O projeto migrou da pasta `assetdeck` (HEAD solta na Fatia
  51b) para `assetdeck-correcoes` (na `main`). O `.venv` da pasta antiga
  sumiu no meio de uma sessão (não foi comando do agente). Ver memória
  `assetdeck-worktree-isolado`.
- **ClientDeck / "freelance manager".** Projeto irmão (gerenciador de
  archviz para clientes). Tem um crossover **somente-leitura e opcional**:
  abre o SQLite do AssetDeck de fora (`mode=ro`), sem importar nada do
  código, para vincular assets renderizados a entregas de cliente. Se o
  banco do AssetDeck não existir, a seção some. Ver plano
  `acho-que-podemos-implementar-hazy-shore.md`.
- **RustDesk.** Rafael às vezes testa via celular controlando o PC — mudou
  o diagnóstico do "piscar" do HDRI na Fatia 65.
- **GitHub.** Remoto `zsabados3523/AssetDeck`. A `main` foi publicada até a
  Fatia 58 em 2026-08-14 a pedido dele; a branch do V-Ray fica de fora.

---

## 8. Como o Rafael trabalha (o que já está decidido)

- **Não programa.** Explicar cada comando ANTES de rodar. Ele usa o app
  desktop, não o terminal — o agente roda os comandos. `sudo` pede senha →
  entregar o comando `apt`/`pkexec` pronto para ele.
- **Uma fatia por vez, branch própria, pytest verde, e merge na `main` só
  depois de ele confirmar na tela.** Sempre.
- **Mockup ANTES de qualquer reorganização de layout/menu.** A lição mais
  cara do projeto: na Fatia 43 o agente perguntou "quer cor de destaque?"
  no abstrato, ele disse não — e depois reclamou que queria o overhaul
  completo. O que funciona: montar a **janela inteira em HTML**, direções
  diferentes lado a lado, e deixar ele escolher olhando. Ele vetou cor no
  abstrato e escolheu azul em 10 segundos vendo 4 botões juntos. Ver
  memória `mockup-antes-de-mudanca-de-layout-ou-menu`.
- **A máquina é dele e ele a usa enquanto o agente trabalha.** Avisar antes
  de rodar a suíte completa (~3–35 min) ou reprodução pesada — ele sente o
  CPU. A varredura roda com `nice` e 1 thread de OpenCV por isso.
- **Ao fatiar, dizer explicitamente o que a fatia NÃO cobre** (lição da
  Fatia 50 — o recorte de duas fatias deixou metade do mockup de fora sem
  avisar).
- **Consolidar tudo numa branch só antes de pedir teste** (lição da Smart
  Collection reset — ele testou uma branch sem o fix).
- **Testar contra os dados DELE, não só os do teste** — nomes de pack sem
  espaço (`MT_PM_V148_Acoelorrhaphe_...`) estouravam larguras de painel que
  a testlib nunca revelava (Fatias 51b, 79, 82).
- **Ele decide o schema, a UX e o gosto visual.** O agente mede o custo e
  apresenta o trade-off; ele escolhe (Link vs Append, cor média vs k-means,
  paleta fixa vs seletor livre, OpenGL sabendo do custo...).
- Fala português. Todos os docs do projeto são em português.

---

## 9. Índice das conversas

Grupo "Asset Deck" (+ worktrees). IDs locais, para reabrir com
`list_events`. Datas = última atividade.

| Sessão (id curto) | Período | O que produziu |
|---|---|---|
| `9d512fcc` "Configurar ambiente do projeto" | 07-31 → 08-17 | **Sessão-tronco.** Ambiente, arquitetura (PROJECT/SCHEMA/TODO), boa parte das fatias iniciais; retomada mais tarde até a Fatia ~78 (sanfona do painel de detalhes). 2891 msgs. |
| `3964bf7a` "F3 Fatia 17 — Collections manuais" | 08-01 | Fecha a F3 (17–19b), levanta as 3 perguntas do Rafael (visual, executável, biblioteca real) que viram a F4. |
| `f4fd5532` "F4 redesign moderno" | 08-02 | F4: tema Craft, executável no menu do Zorin, ícone do app, `alpha-1.0`. Fix do ícone no dock (`setDesktopFileName`). |
| `80c1d665` "Assetdeck tags bug e ícone" | 08-03 | Fatias 36/40 e vizinhas; destrava fatias que dependiam do Blender. |
| `d948d240` "Fatia 39 desenvolvimento" | 08-03 | Fatia 39 (busca por cor) + Fatia 43 (overhaul visual, modo escuro real) — e a crítica do Rafael que gerou o `REDESIGN-V2.md`. |
| `5be5203b` "Investigar widgets de teste" (worktree) | 08-02 | Fixture `qt_settle` no `conftest.py` — suíte de ~27s para ~13s, sem segfault. |
| `9263e7a9` "AssetDeck visual overhaul mockups" | 08-04 | Redesign v2 (Fatias 44–50) via mockups da janela inteira. Depois: troca do banco para a biblioteca real reaproveitando um snapshot de 02-08 (evitou reindexar 579GB). |
| `51b56597` "Arrastar imagem para preview de asset" | 08-06 | Fatia 52 — a **causa real** do drag-and-drop (viewport recusava todo drop). SSD estava desmontado nas idas e vindas. |
| `548af3b2` "Corrigir installer.py (Flatpak morto)" (worktree) | 08-10 | Blender portátil: `installer.py` passa a achar `~/.config/blender`. Branch não mergeada na hora (trazida na Fatia 68). |
| `65518940` "Thumbnail falha em EXR de canal único" (worktree) | 08-14 | `hdr.py`: EXR de 1 canal (displacement/roughness) vira cinza em vez de `ValueError`. |
| `e163b850` "Arrastar previews para modelo 3D" | 08-14 | Merge das Fatias 53–58 na `main`, publica no GitHub, separa a branch do V-Ray como projeto à parte. Propõe tags de templates com base no Connecter. |
| `bb96a48e` "Assetdeck feature research" | 08-16 | **O roadmap F6** (comparação com o Polydex) — `ok-coisas-que-achei-iterative-barto.md`. Fatia 67 (janela única de configurações). |
| `a4a00670` "Continuação anterior" | 08-27 | **Maratona F6/F7.** Da Fase 5 até a Fatia 102. 4567 msgs. É a sessão "atual" antes desta. |
| `4ac962e0` "Blend import reset e texturas Cosmos" | 08-27 | Fatias 101/101b — preview por nome alcançando `_Blender_Cycles`/`_Cycles` e sequências `_preview1`; 649 previews assinalados em 3 rodadas contra o banco real. `purge_missing`. |
| `4431ed83` "Plugin Blender Vray para Cycles" | 08-28 | **Não é AssetDeck.** Debug de instalação do add-on V-Ray (arquivos soltos em `addons/`, dono `root`). |

Sessões relacionadas fora do grupo: `464317e4` "Gerenciador de projeto
Archviz" (ClientDeck, com o crossover read-only), `12ebbcf4` "Gscatter addon
não funciona" (port do GScatter para o Blender 5.2 — contexto Blender do
Rafael, V-Ray 7.40).

---

## 10. O que está em aberto

- **F7 / Fase 7 do roadmap F6 não fechou.** Etapa 1 (janela principal) e
  Etapa 2 (`SettingsWindow`) feitas; Etapa 3 (diálogos secundários) parcial;
  a "revisão visual geral ao vivo" com o Rafael continua pendente por
  design — precisa dele na tela.
- **Abertura lenta.** ~15s na biblioteca real. Medido: ~2,2s só no
  `prewarm_gl_viewers`, ~2s "assentar UI/scan" ainda não investigado, e
  montar ~28k itens de árvore. Três caminhos possíveis registrados na
  investigação (Fatia 83 / "app demora pra abrir"), decisão do Rafael.
- **EM ABERTO — o programa fecha sozinho ao mexer em tags** (relato de
  08-23). Sem diagnóstico: não é exceção Python, não é OOM, não é
  `rebuild_fts`. Queda de nível C++, o Qt derruba em silêncio. A Fatia 99
  armou um `faulthandler` permanente (`~/.local/share/assetdeck/logs/quedas.txt`)
  esperando a próxima queda.
- **`_reload_all`/warmup ainda congela ~1,7s** na thread da UI na biblioteca
  real — mover para a thread da varredura muda o que o `ScanWorker` devolve,
  ficou como próxima.
- **Enquadramento inicial do visualizador 3D** usa a maior meia-dimensão da
  caixa, não o raio da esfera — margem justa em objeto alto e estreito.
- **`is_dependency` levemente desatualizado após `mover`** até a próxima
  reindexação (não quebra nada).
- **Múltiplas bibliotecas:** `config.py` ainda aceita só uma raiz por vez;
  o vazamento cosmético de extensões no checklist da barra de categorias
  (banco de dev sujo).
- **Pendências fora do código:** `sudo apt remove -y blender` (remove o
  4.0.2 redundante); cadastrar a biblioteca real do SSD como segunda
  library quando o app amadurecer.

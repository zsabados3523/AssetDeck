# PROJECT.md — AssetDeck

DAM (Digital Asset Manager) local de assets 2D/3D para Linux, inspirado no
Connecter, integrado ao Blender. Uso pessoal do Rafael, 100% offline, sem
conta, sem nuvem, sem telemetria.

## Requisitos inegociáveis
1. **Somente-leitura sobre a biblioteca.** O app NUNCA move, renomeia ou apaga
   arquivos do usuário. A única escrita permitida dentro da biblioteca é a
   CRIAÇÃO de sidecars `.json` novos.
2. **Metadados em SQLite + espelho em `.json`** ao lado dos assets, com backup
   rotativo diário do `.db`. Motivo: o Connecter corrompia bibliotecas sem
   recuperação.
3. **100% offline.**
4. **UI nunca congela**: indexação em background, cache de thumbnails.
5. **Soft delete em tudo** (`deleted_at`) — nada é apagado de verdade.

## Decisões tomadas
| Decisão | Escolha | Por quê |
|---|---|---|
| Biblioteca de desenvolvimento | `/home/rafael/00 - PROJETOS/assetdeck-testlib` (4GB, 750 arquivos reais) | Testar contra dados reais sem arriscar os 650GB |
| Biblioteca real | SSD externo NTFS (entra depois) | Caminho raiz é **configuração**, nunca hardcoded |
| Sidecars `.json` | Ao lado dos assets | Se o banco morrer, os metadados sobrevivem junto dos arquivos |
| GUI | PySide6 6.11 (Qt) | Nativo Linux, grid aguenta milhares de itens |
| Banco | SQLite em modo WAL | Zero servidor, leitura concorrente com escrita |
| Blender alvo | **5.2 via Flatpak** (`flatpak run org.blender.Blender`) | É o que o Rafael usa; o 4.0.2 do apt foi descartado |
| EXR/HDR | **OpenCV** (`.hdr`) + **bindings oficiais OpenEXR** (`.exr`), tonemap Reinhard | Pillow não lê HDR. **imageio foi descartado**: o leitor dele baixa binário em runtime, o que viola o 100% offline |
| Tipos de asset | inclui **ies, lut, vector, psd** além dos do brief | Descobertos na testlib real |
| Layout da grid | `SinglePass` + `uniformItemSizes` | Em lotes, o scrollbar descobria o tamanho tarde e a rolagem saltava (Fatia 15) |
| Papel do add-on | **Ponte, não importador** (sugestão do Rafael, F2) | Arrastar do AssetDeck aciona o menu nativo do Blender; o add-on só acrescenta o que o Blender não faz (HDRI→World, material PBR do set, Append/Link com "& Place") |
| Dependências | Texturas ao lado de um `.blend`/`.fbx` irmão são marcadas e ocultas por padrão | O fluxo do Rafael converte cada material num `.blend`; ele quer ver o `.blend`, não os 6 mapas |

## Ambiente (verificado)
- ZorinOS 18.1 · Python 3.12.3 · venv em `.venv` · PySide6 6.11.1 (xcb OK) ·
  pytest 9.1.1 · git branch `main`
- `sudo` pede senha → instalações de sistema são feitas pelo Rafael com
  comando pronto.
- Dados do app (padrão XDG):
  - Config: `~/.config/assetdeck/config.json`
  - Banco: `~/.local/share/assetdeck/assetdeck.db`
  - Backups: `~/.local/share/assetdeck/backups/`
  - Previews escolhidos/renderizados: `~/.local/share/assetdeck/previews/`
  - Cache de thumbs: `~/.cache/assetdeck/thumbs/`
- Dependências Python em `requirements.txt` (PySide6, Pillow, opencv-python-headless,
  numpy, OpenEXR, pytest).

## Arquitetura de módulos (estado real)
```
assetdeck/
  __main__.py            # python -m assetdeck [--screenshot PATH [--screenshot-delay MS]]
  app.py                 # bootstrap: config → logging → banco → backup → janela
  config.py              # caminhos XDG + config.json + token da ponte
  logging_setup.py       # log em arquivo rotativo + console
  db/
    connection.py        # SQLite WAL, foreign_keys ON, busy_timeout
    migrate.py           # aplica migrations/ em ordem; nunca editar antigas
    migrations/          # 001_initial · 002_group_locked · 003_hidden · 004_dependency
    repos/               # assets · tags · previews · libraries
  indexer/
    scanner.py           # varredura idempotente em thread; missing_since; sidecars
    grouper.py           # agrupamento PBR + correção manual travável
    dependencies.py      # marca texturas que acompanham um .blend/.fbx irmão
    (relocator.py)       # PREVISTO para a Fatia 19, ainda não escrito
  thumbs/
    preview.py           # fachada: escolhe raster ou hdr
    raster.py            # jpg/png/tif (Pillow) + resgate de PNG com iCCP ruim
    hdr.py               # .hdr (OpenCV) e .exr (OpenEXR) + tonemap Reinhard
    pipeline.py          # fila em QThreadPool, com prioridade e warmup
    cache.py             # cache por content_hash + THUMB_VERSION
  sidecar/
    writer.py, reader.py # espelho .json (só CRIA arquivos novos)
  backup/rotate.py       # backup diário do .db, com poda segura
  bridge/                # F2 — ponte com o Blender
    protocol.py          # JSON por linha, 127.0.0.1, token
    server.py            # QTcpServer assíncrono (não trava a UI)
    handlers.py          # lógica dos comandos, testável sem socket nem Qt
    installer.py         # instala o add-on no Blender Flatpak
  blender/               # F2 — chamadas headless
    render.py            # fila de render de capas (subprocess)
    scripts/render_thumb.py   # roda DENTRO do Blender
  ui/
    main_window.py       # janela, filtros, menus, ponte, render
    asset_grid.py        # modelo + view da grade (drag interno e externo)
    details_panel.py     # detalhes, estrelas, galeria, tags, notas
    folder_tree.py · tag_tree.py · tag_dialogs.py · type_filter.py
    preview_popup.py     # duplo clique: preview ampliado padronizado
    scan_worker.py · render_worker.py   # threads com sinais Qt
blender_addon/assetdeck_bridge/   # add-on (v0.4.0)
  __init__.py            # painel na sidebar N
  client.py              # socket + erros legíveis em português
  materials.py           # monta o node group PBR
  drops.py               # File Handlers: HDRI→World, textura→material
  importer.py            # .blend → menu Append/Link (& Place)
  exporter.py            # salvar seleção da cena na biblioteca
  thumbs.py              # miniaturas dentro do Blender
tests/                   # 163 testes
```

## Fluxo de dados
- A **UI (thread principal)** só LÊ o banco, via `db/repos`.
- O **indexer** e o **pipeline de thumbs** rodam em threads/pool e escrevem no
  banco por uma fila única (um escritor por vez — SQLite gosta assim).
- Sinais Qt avisam a UI quando há dados novos; a grid atualiza sem travar.
- A biblioteca do usuário é sempre somente-leitura (exceção única: criar
  sidecars `.json`).

## Descobertas do F2 (verificadas na máquina, não presumidas)
- **Sandbox do Flatpak**: `shared=network` (socket localhost funciona) e
  `filesystems=host` (o Blender lê a biblioteca). Confirmado com tráfego real.
- **⚠ O Flatpak tem `/tmp` PRÓPRIO.** O Blender não enxerga o `/tmp` do host:
  scripts, renders e arquivos de troca têm de ficar em `~/.cache/assetdeck`
  ou `~/.local/share/assetdeck`. Vale também para testes — `tmp_path` do
  pytest não serve para integração com o Blender.
- **Caminhos de script devem ser absolutos**: um caminho relativo é resolvido
  contra `/app/blender` dentro do sandbox.
- **Packs comerciais com texturas quebradas**: os `.blend` da Maxtree apontam
  para uma subpasta quando os mapas estão numa pasta IRMÃ — renderizavam
  magenta. O render relocaliza em memória (o arquivo do usuário não é tocado).
- Caminho do add-on: `~/.var/app/org.blender.Blender/config/blender/5.2/scripts/addons`.

## Riscos anotados
- **Biblioteca real em NTFS**: sem inotify confiável; a relocalização por
  content_hash (Fatia 19) e o rescan manual cobrem isso.
- **Busca por início de palavra**: o FTS5 não acha "quartzite" dentro de
  "StoneQuartziteTile". Tratado na Fatia 21.

## Documentos irmãos
- `SCHEMA.md` — modelo de dados. Fonte da verdade.
- `TODO.md` — roadmap em fatias e estado atual.
- `CLAUDE.md` — regras de trabalho.

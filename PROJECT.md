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

## Decisões tomadas (2026-07-31)
| Decisão | Escolha | Por quê |
|---|---|---|
| Biblioteca de desenvolvimento | `/home/rafael/00 - PROJETOS/assetdeck-testlib` (4GB, 753 arquivos reais) | Testar contra dados reais sem arriscar os 650GB |
| Biblioteca real | SSD externo NTFS (entra depois) | Caminho raiz é **configuração**, nunca hardcoded |
| Sidecars `.json` | Ao lado dos assets | Se o banco morrer, os metadados sobrevivem junto dos arquivos |
| GUI | PySide6 6.11 (Qt) | Nativo Linux, grid virtualizada aguenta milhares de itens |
| Banco | SQLite em modo WAL | Zero servidor, leitura concorrente com escrita |
| Blender alvo | **5.2 via Flatpak** (`flatpak run org.blender.Blender`) | É o que o Rafael usa; o 4.0.2 do apt foi descartado |
| EXR/HDR | imageio + numpy com tonemap | Pillow não lê HDR |
| Tipos de asset | inclui **ies, lut, vector, psd** além dos do brief | Descobertos na testlib real |

## Ambiente (verificado)
- ZorinOS 18.1 · Python 3.12.3 · venv em `.venv` · PySide6 6.11.1 (xcb OK) ·
  pytest 9.1.1 · git branch `main`
- `sudo` pede senha → instalações de sistema são feitas pelo Rafael com
  comando pronto.
- Dados do app (padrão XDG):
  - Config: `~/.config/assetdeck/config.json`
  - Banco: `~/.local/share/assetdeck/assetdeck.db`
  - Backups: `~/.local/share/assetdeck/backups/`
  - Cache de thumbs: `~/.cache/assetdeck/thumbs/`

## Arquitetura de módulos
```
assetdeck/
  __main__.py            # python -m assetdeck [--screenshot PATH]
  app.py                 # QApplication + MainWindow
  config.py              # caminhos XDG + config.json (raiz da biblioteca etc.)
  logging_setup.py       # log em arquivo + console; erros legíveis
  db/
    connection.py        # SQLite WAL, foreign_keys ON, um único escritor
    migrate.py           # aplica migrations/ em ordem
    migrations/          # 001_initial.sql, 002_..., nunca editar antigas
    repos/               # queries por domínio (assets, tags, collections…)
  indexer/
    scanner.py           # varredura em thread; nunca bloqueia a UI
    grouper.py           # heurística de agrupamento PBR (Fatia 6)
    relocator.py         # relocalizar assets movidos (F3)
  thumbs/
    pipeline.py          # fila de jobs em QThreadPool
    raster.py            # jpg/png/tif via Pillow
    hdr.py               # exr/hdr via imageio + tonemap (Fatia 7)
    cache.py             # cache em disco por content_hash
  sidecar/
    writer.py, reader.py # espelho .json (só cria arquivos novos)
  backup/
    rotate.py            # backup rotativo diário do .db
  ui/
    main_window.py, asset_grid.py, details_panel.py, search_bar.py
blender_addon/           # F2 — add-on para Blender 5.2 Flatpak
tests/
```

## Fluxo de dados
- A **UI (thread principal)** só LÊ o banco, via `db/repos`.
- O **indexer** e o **pipeline de thumbs** rodam em threads/pool e escrevem no
  banco por uma fila única (um escritor por vez — SQLite gosta assim).
- Sinais Qt avisam a UI quando há dados novos; a grid atualiza sem travar.
- A biblioteca do usuário é sempre somente-leitura (exceção única: criar
  sidecars `.json`).

## Riscos anotados
- **Flatpak sandbox (F2)**: o add-on dentro do Blender Flatpak precisa de
  socket localhost e de acesso aos arquivos da biblioteca. Verificar com
  `flatpak info --show-permissions org.blender.Blender` antes de desenhar o F2.
- **Biblioteca real em NTFS**: sem inotify confiável; a relocalização por
  content_hash (F3) e o rescan manual cobrem isso.

## Documentos irmãos
- `SCHEMA.md` — modelo de dados. Fonte da verdade.
- `TODO.md` — roadmap em fatias e estado atual.
- `CLAUDE.md` — regras de trabalho.

# AssetDeck

[![CI](https://github.com/zsabados3523/AssetDeck/actions/workflows/ci.yml/badge.svg)](https://github.com/zsabados3523/AssetDeck/actions/workflows/ci.yml) [![Release](https://img.shields.io/github/v/release/zsabados3523/AssetDeck)](https://github.com/zsabados3523/AssetDeck/releases) [![License: MIT](https://img.shields.io/github/license/zsabados3523/AssetDeck)](LICENSE)

English | [Português (Brasil)](README.pt-BR.md)

Local, standalone 2D and 3D digital asset manager (DAM) for Windows, macOS, and Linux — textures, PBR materials, HDRIs, 3D models, IES light profiles, LUTs, and vectors — featuring built-in 3D viewers, flexible organization, and direct Blender integration. Built for personal and studio workflows: **100% offline**, no account required, no cloud dependencies, and zero telemetry.

The asset library on disk is **strictly read-only by default**: AssetDeck never modifies or moves your files on its own. Only two explicit actions write to disk, and both require user confirmation: **batch renaming** (with live conflict preview) and **moving assets** (dragging grid cards into folder tree nodes). Neither action ever deletes files.

Metadata (tags, notes, ratings, favorites, collections) is stored in a local SQLite database with WAL mode and automatic daily backups, accompanied by a sidecar `.assetdeck.json` file next to each asset — if the database is ever rebuilt, your metadata is restored automatically during the next scan.

---

## Gallery

### Main Interface (Light and Dark Mode)

| Light Mode | Dark Mode |
|---|---|
| ![AssetDeck in light mode](docs/screenshots/biblioteca-claro.png) | ![AssetDeck in dark mode](docs/screenshots/biblioteca-escuro.png) |
| *Asset grid with sidebar navigation, categories, filters, and detailed inspection panel showing a PBR material.* | *Dark theme with WCAG high contrast, sharp thumbnails, hierarchical tags, and complete technical specifications.* |

### Integrated 3D Viewers (OpenGL)

| HDRI / EXR Viewer | 3D Model Viewer |
|---|---|
| ![HDRI Viewer](docs/screenshots/visualizador-hdri.png) | ![3D Model Viewer](docs/screenshots/visualizador-modelo-3d.png) |
| *360° equirectangular projection, orbit rotation, reflective sphere mode, and dynamic range exposure readout.* | *Real-time 3D orbit with diffuse lighting, smooth normal shading, and material inspection (.mtl).* |

### Organization and Advanced Search

| Sidebar Organization (Folders, Tags, and Collections) | Boolean Operator Search |
|---|---|
| ![Sidebar collections and tags](docs/screenshots/colecoes-tags.png) | ![Search with boolean operators](docs/screenshots/busca-operadores.png) |
| *Disk folder tree, color-coded hierarchical tags, manual collections, and dynamic smart collections.* | *Combined search by name and advanced filters (`concrete AND industrial`, `wood OR metal`, `NOT metal`).* |

### Settings Center (Light and Dark Mode)

| Settings in Light Mode | Settings in Dark Mode |
|---|---|
| ![Settings window in light mode](docs/screenshots/configuracoes.png) | ![Settings window in dark mode](docs/screenshots/configuracoes-escuro.png) |
| *Database maintenance, active library, scan on startup, parallel worker processes, and Blender bridge configuration.* | *System settings, maintenance, and preferences faithfully adapted to the dark theme.* |

### Tools and First Run

| Batch Rename | Duplicate Detection | First Run (Empty State) |
|---|---|---|
| ![Batch rename](docs/screenshots/renomear-lote.png) | ![Review duplicates](docs/screenshots/duplicatas.png) | ![Empty state](docs/screenshots/estado-vazio.png) |
| *Batch text find-and-replace with live change preview and conflict validation.* | *Grouping of identical files or resized variants using perceptual hashing (pHash).* | *Welcome screen guiding library folder selection on first run.* |

---

## Features

- **Read-only library by default:** The app analyzes, fingerprints, and reads metadata without touching your asset files. The only disk write operations (moving assets and batch renaming) require explicit confirmation.
- **Automatic PBR grouping:** Automatically groups complementary map files (`_basecolor`, `_normal`, `_roughness`, `_height`, `_metallic`, `_ao`, etc.) into a single PBR material card with a representative preview.
- **Automatic cover and preview association:** Automatically links eponymous preview images (`Chair.blend` + `Chair.jpg`) or `previews/` folders and pack catalogs to their respective 3D model.
- **Dedicated-window 3D viewers:**
  - **HDRIs and EXRs:** 360° equirectangular spherical projection, orbit and zoom controls, reflective chrome sphere mode to evaluate lighting, and accurate resolution reading.
  - **3D Models:** Three-dimensional camera orbit for `.obj`, `.fbx` (via Assimp), and `.blend` (via headless Blender), with automatic framing, vertex and polygon counts, and material inspection.
- **Offline thumbnail generation:** Deterministic thumbnail cache indexed by the original file's `content_hash`. Includes tonemapping with dynamic range compression (global Reinhard + 2.2 gamma curve) for `.hdr` and `.exr`, and crisp vector rendering for `.svg`.
- **Advanced search and multi-faceted filtering:**
  - Boolean query syntax (`concrete AND rustic`, `stone OR metal`, `NOT brick`).
  - Filter by asset type (Texture, PBR Material, 3D Model, HDRI, IES, LUT, Vector).
  - Filter by file extension, star rating, favorites, and dominant image color.
- **Structured and flexible organization:**
  - **Hierarchical tags:** Tag tree with customizable colors and icons.
  - **Bilingual synonyms and aliases:** Associates English and Portuguese terms (e.g., `Wood` = `Madeira`, `Concrete` = `Concreto`).
  - **Manual collections:** Arbitrary groupings arranged in a tree structure without duplicating files on disk.
  - **Smart collections:** Saved queries that dynamically re-evaluate criteria against the database.
  - **Ratings and notes:** 1-to-5 star ratings, favorite bookmarks, and freeform markdown notes.
  - **Custom properties (EAV):** User-defined typed fields (Text, Number, Boolean, Date), such as *Vendor*, *Resolution*, or *License*.
- **Visual duplicate detection:** Perceptual hashing (pHash) algorithm detects identical images even when saved across different resolutions or formats.
- **Metadata resilience with sidecars:** A companion `.assetdeck.json` file is mirrored alongside each asset to preserve tags, notes, and ratings independently of the SQLite database.
- **Native Blender integration:** Local socket bridge with security token authentication allows dragging assets straight into the 3D viewport and triggers headless thumbnail rendering for 3D models.

---

## Download

Pre-compiled binaries for Windows, macOS, and Linux are available on the official [Releases](https://github.com/zsabados3523/AssetDeck/releases) page.

> [!IMPORTANT]
> **Notice regarding unsigned executables:** Because AssetDeck is an independently maintained open-source project, release binaries are not signed with commercial developer certificates:
> - **Windows:** Windows SmartScreen may show the alert *"Windows protected your PC"*. Click **More info** and then **Run anyway**.
> - **macOS:** Gatekeeper may block the initial launch. **Right-click** the application and select **Open**, or go to **System Settings → Privacy & Security** and click **Open Anyway**.
> - **Linux:** Download the `.tar.gz` archive, extract the contents, make the binary executable with `chmod +x assetdeck`, and run `./assetdeck`.

---

## Installation from Source

### Requirements

- Python 3.12+
- [Blender](https://www.blender.org/) 4.x or 5.x (optional, for drag-and-drop viewport bridge and headless thumbnail rendering)

### Step-by-Step

1. Clone the repository and navigate into the project directory:
   ```bash
   git clone https://github.com/zsabados3523/AssetDeck.git
   cd AssetDeck
   ```

2. Create and activate an isolated virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   # On Windows (PowerShell): .venv\Scripts\Activate.ps1
   ```

3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Launch the application:
   ```bash
   python -m assetdeck
   ```

5. (Optional on Linux) Install the desktop shortcut in your system application menu:
   ```bash
   python install_desktop_entry.py
   ```

---

## Getting Started

1. **Set the library folder:**
   When launching AssetDeck for the first time, you will be greeted by the initial empty state. Select the folder where your existing 3D assets and textures are organized. You can change or update this path at any time in `config.json` or through the settings window.

2. **Index your files:**
   AssetDeck **does not scan disk files automatically on startup** by default, avoiding unnecessary slowdowns with large libraries containing tens of thousands of assets. Click the **Reindex** button in the top toolbar whenever you add new files to the directory. If you prefer automatic scanning at launch, enable the option in *Settings → Maintenance → Scan library on startup*.

3. **Install the Blender bridge (optional):**
   Within AssetDeck, go to *Settings → Blender → Install / update add-on...* to copy the extension directly into Blender's add-ons folder. Next, in Blender, open *Edit → Preferences → Add-ons*, enable **AssetDeck Bridge**, and use the panel in the 3D viewport sidebar (`N`) to receive dropped models, materials, and world environments.

---

## Data Storage by Operating System

AssetDeck strictly adheres to standard operating system directory conventions (implemented in `assetdeck/config.py`). Default locations:

| Operating System | Configuration (`config.json`) | Database, logs, and backups | Thumbnail cache |
|---|---|---|---|
| **Linux** | `~/.config/assetdeck/` | `~/.local/share/assetdeck/` | `~/.cache/assetdeck/` |
| **Windows** | `%APPDATA%\assetdeck\` | `%LOCALAPPDATA%\assetdeck\` | `%LOCALAPPDATA%\assetdeck\cache\` |
| **macOS** | `~/Library/Application Support/assetdeck/` | `~/Library/Application Support/assetdeck/` | `~/Library/Caches/assetdeck/` |

> [!TIP]
> All paths can be overridden using environment variables, ideal for portable installations or automation scripts:
> - `ASSETDECK_CONFIG_DIR`: Directory containing `config.json`
> - `ASSETDECK_DATA_DIR`: Directory containing `assetdeck.db`, backups, and logs
> - `ASSETDECK_CACHE_DIR`: Directory containing the thumbnail and mesh cache

---

## Technologies

- **Graphical User Interface:** PySide6 (Qt 6.11) with modular QSS stylesheets and a design token system calibrated for WCAG contrast compliance.
- **Local Database:** SQLite 3 structured with WAL (Write-Ahead Logging) mode and versioned schema migrations.
- **Graphics and Shaders:** OpenGL 3.30 Core Profile (`QOpenGLWidget`) with custom GLSL shaders for 360° equirectangular HDRIs and 3D meshes.
- **Image and Data Processing:** Pillow (PIL), NumPy, OpenCV, and the official OpenEXR library.
- **3D Integration:** Native OBJ parser, FBX support via Assimp, and headless Blender automation scripts.

---

## How to Regenerate Documentation Screenshots

The repository includes deterministic tools to generate a synthetic, copyright-free demo library and capture all interface screenshots without relying on user configuration:

```bash
# 1. Generate the synthetic demo library in an isolated temporary directory
python tools/make_demo_library.py "/tmp/claude-1000/shots/AssetDeck Demo"

# 2. Run the deterministic screenshot capture script (outputs images to docs/screenshots/)
QT_QPA_PLATFORM=offscreen python tools/capture_screenshots.py
```

The script automatically sets up an isolated environment in `/tmp`, indexes the synthetic files, populates demonstration metadata (tags, collections, ratings, properties), and saves optimized screenshots to `docs/screenshots/`.

---

## Contributing

Contributions are warmly welcomed! Please consult our [CONTRIBUTING.md](CONTRIBUTING.md) guide ([versão em português](CONTRIBUTING.pt-BR.md)) and our [Code of Conduct](CODE_OF_CONDUCT.md) for development workflows, automated testing, and community standards.

There are many ways you can help improve AssetDeck:

- **Testing on real Windows and macOS hardware:** Core development primarily targets Linux, so testing on physical Windows (10/11) and macOS (Apple Silicon and Intel) machines is vital for validating keyboard shortcuts, font rendering, path separators, and UI stability. If you encounter bugs, please file an issue including log excerpts (`assetdeck.log` or `quedas.txt`).
- **Fixing bugs and implementing enhancements:** Check out open issues on GitHub, particularly those tagged [`good first issue`](https://github.com/zsabados3523/AssetDeck/labels/good%20first%20issue) and [`help wanted`](https://github.com/zsabados3523/AssetDeck/labels/help%20wanted).
- **Translations and UI localization (i18n):** Today, the entire AssetDeck interface is hardcoded in Portuguese (pt-BR) and no internationalization infrastructure exists yet in the codebase. Contributions to establish an i18n framework (such as `gettext` or Qt/PySide Linguist tooling) and translate the interface into English and other languages are especially appreciated.
- **Packaging and distribution:** Assistance with code signing and notarization on macOS (Apple Developer ID / Gatekeeper), Windows installer generation (Inno Setup / MSIX), and Linux packages (AppImage, Flatpak).
- **Documentation and tutorials:** Writing step-by-step guides, practical Blender integration tutorials, and improving technical/architectural documentation.
- **New asset formats:** Proposing and writing parsers/loaders for additional 3D model, material, texture, or vector file formats.
- **Sharing feedback and experiences:** Join conversations, provide feedback, or ask questions in our [GitHub Discussions](https://github.com/zsabados3523/AssetDeck/discussions).

To run the test suite:
```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

---

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for more information.

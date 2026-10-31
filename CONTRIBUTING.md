# Contributing to AssetDeck

English | [Português (Brasil)](CONTRIBUTING.pt-BR.md)

Thank you for your interest in contributing to AssetDeck! This document outlines how to set up your development environment, run the project, execute tests, and follow project guidelines when submitting a Pull Request.

## Code of Conduct and Security

- By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).
- To report security vulnerabilities privately and responsibly, please refer to our [Security Policy](SECURITY.md).

## How to Report Bugs

If you find a bug in AssetDeck:

1. Check whether the problem has already been reported in the [repository Issues](https://github.com/zsabados3523/AssetDeck/issues).
2. Open a new report using the [Bug Report](.github/ISSUE_TEMPLATE/bug.yml) form.
3. Specify your operating system, execution mode (pre-compiled binary or from source), and detailed reproduction steps.
4. Attach relevant log excerpts (`assetdeck.log` or `quedas.txt`). In the application, you can open the logs directory directly from **Settings → Maintenance → Open logs folder** or **Help → Open logs folder** (located at `~/.local/share/assetdeck/logs` on Linux, `%LOCALAPPDATA%\assetdeck\logs` on Windows, and `~/Library/Application Support/assetdeck/logs` on macOS).

## How to Propose Features

New ideas and improvements are warmly welcomed:

1. For conceptual discussions or design questions, consider starting a thread in [Community Discussions](https://github.com/zsabados3523/AssetDeck/discussions).
2. For formal feature proposals, submit an issue using the [Feature Request](.github/ISSUE_TEMPLATE/feature.yml) form.
3. Describe the practical motivation in your 3D/artistic workflow and detail the expected behavior in the app.

## Areas Where Help is Welcome

If you would like to collaborate on code or testing, here are some priority areas:

- **Testing on real Windows and macOS systems:** Verifying shortcuts, font rendering, file paths, and GUI stability across various operating system versions.
- **Translations and UI localization (i18n):** Today, the UI is hardcoded in Portuguese (pt-BR) with no internationalization framework implemented yet; contributions to enable i18n (gettext / Qt Linguist) and translate the app into English and other languages are welcomed.
- **Packaging and distribution:** Creating installers, digital code signing and notarization for Windows (SmartScreen) and macOS (Gatekeeper / Apple Developer ID), and Linux packages (AppImage / Flatpak).
- **Documentation and tutorials:** Usage guides, Blender integration tutorials, and technical architecture documentation.
- **New asset formats:** Loaders and importers for additional 3D model formats, materials, textures, or vector files.
- **Bug fixing and improvements:** Check open issues tagged with [`good first issue`](https://github.com/zsabados3523/AssetDeck/labels/good%20first%20issue) and [`help wanted`](https://github.com/zsabados3523/AssetDeck/labels/help%20wanted).

## Running the Project

1. **Clone the repository and set up a virtual environment with Python 3.12:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Launch the application:**
   ```bash
   python -m assetdeck
   ```

## Running Tests

Before submitting a Pull Request, run the automated test suite in headless mode (without opening GUI windows):

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

All tests must pass.

## Development Guidelines and Rules

- **One change per PR:** Keep Pull Requests small, atomic, and focused on a single objective.
- **Read-only library:** The user's asset library is strictly read-only. The app never moves, renames, or deletes files on its own. The only two permitted disk-modifying operations are batch rename (`batch_rename`) and moving assets (`mover`), which always require explicit user confirmation and operate safely.
- **No silent exceptions:** Handle exceptions with context and record them in the log (`log.warning`, `log.error`, or `log.exception`). Never use bare `except: pass` without proper handling or logging.
- **No `setStyleSheet` outside `assetdeck/ui/theme.py`:** Colors, radii, spacing, and fonts must be declared as tokens in `theme.py` and referenced via `$name` in `theme.qss`.
- **Do not weaken tests:** If a test fails, fix the code and implementation; never relax or disable test assertions to make a test pass.

# Changelog

English | [Português (Brasil)](CHANGELOG.pt-BR.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-10-31

### Added
- Local 2D and 3D digital asset manager for Linux, Windows, and macOS (textures, HDRIs, 3D models, PBR materials, LUTs, IES light profiles, and vectors).
- 100% offline philosophy: no telemetry, no user accounts, and no dependencies on external services or cloud infrastructure.
- File library strictly read-only by default, ensuring original assets are never altered without explicit authorization.
- On-demand background directory scanning and indexing triggered by the user.
- Automatic grouping of PBR material texture maps (`_basecolor`, `_normal`, `_roughness`, etc.) into a single grid card.
- High-quality thumbnail generation and caching, including tonemapping for high-dynamic-range images (`.hdr` and `.exr`).
- Visual duplicate detection using perceptual hashing (identifies similar images across resizes or format conversions).
- Organization system with hierarchical tags (custom colors and aliases), manual collections, filter-based smart collections, favorites, and star ratings.
- Metadata storage in local SQLite database with automatic backup routine and `.json` sidecar mirror alongside each asset for disaster recovery.
- Advanced search with boolean operators (`AND`, `OR`, `NOT`) and combined filters for asset type, file extension, rating, resolution, and dominant color.
- Integrated interactive 3D viewers for HDRIs (360° spherical projection and mirror reflection sphere) and 3D models (`.blend`, `.fbx`, `.obj`) with orbit camera and automatic framing.
- Automatic association of cover/preview images with 3D models via name matching (`Chair.blend` + `Chair.jpg`) and numbered variant support.
- Batch file rename utility with text replacement rules and live on-disk conflict preview.
- Asset relocation feature by dragging cards into folder tree items, moving dependencies (textures and sidecars) with a safety confirmation dialog.
- Local Blender bridge over TCP socket on `127.0.0.1` with secure token authentication:
  - Blender add-on for direct insertion of HDRIs into World, PBR materials with pre-configured node groups, and model linking/appending.
  - Headless model thumbnail and cover rendering executed through the Blender binary.
- Multi-library support with quick switching between library roots in the top toolbar.
- Desktop graphical user interface built with PySide6/Qt featuring native light and dark modes.

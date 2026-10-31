# Security Policy — AssetDeck

English | [Português (Brasil)](SECURITY.pt-BR.md)

AssetDeck takes the security and privacy of its users very seriously. As a tool designed for 3D creators and artists managing local file libraries, our security model is architected to be simple, transparent, and strictly local.

## Supported Versions

Security fixes are applied to the main branch (`main`) and the latest stable release.

| Version | Supported |
| --- | --- |
| 0.1.x | :white_check_mark: |
| < 0.1.0 | :x: |

## Security Model and Architecture

To understand the project's security boundaries, please note the following architectural characteristics:

- **100% Offline:** AssetDeck does not make network requests to the internet, contains no telemetry, never communicates with external servers, and requires no user account.
- **Read-only library by default:** The application never deletes, renames, or modifies files in your library without explicit instruction. The only exceptions are batch renaming and moving assets between folders — both display a detailed confirmation dialog before touching disk.
- **Local Blender bridge (`assetdeck/bridge`):**
  - The internal server uses `QTcpServer` and listens **exclusively on the loopback address `127.0.0.1`** (default port `45017`). No external connections or traffic from other local network machines are accepted.
  - Communication requires a **secret token** randomly generated upon first launch (`secrets.token_urlsafe(24)`) and stored in the local configuration file (`config.json`).
  - Every command sent by the Blender add-on must provide the matching token; connections without a token or with an invalid token are immediately rejected (`bad_token`).
  - The protocol operates via single-line JSON messages with a strict maximum size of 256 KB (`MAX_MESSAGE_BYTES`), preventing buffer overflow or resource exhaustion from malformed requests.

## How to Report a Vulnerability

If you have identified a security vulnerability in AssetDeck, we appreciate your help in disclosing it responsibly.

> **Important:** Please **DO NOT open public issues** on the repository to report vulnerabilities that could put users at risk.

To report a vulnerability privately:

1. Navigate to the **Security** tab of the GitHub repository.
2. Click **Advisories** or use the direct link: [Report a vulnerability](https://github.com/zsabados3523/AssetDeck/security/advisories/new).
3. Fill out the report with the following details:
   - Clear description of the vulnerability.
   - Detailed steps to reproduce the issue (including a proof of concept if applicable).
   - Affected operating systems and versions.
   - Estimated impact.

Your report will be reviewed confidentially by project maintainers. We will coordinate fixing the issue, testing, and releasing a new version prior to publishing any technical disclosure.

# AssetDeck

Gerenciador de assets 2D/3D local para Linux (texturas, HDRIs, modelos,
materiais...), com integração ao Blender. Uso pessoal, **100% offline** —
sem conta, sem nuvem, sem telemetria.

A biblioteca de arquivos é **somente-leitura**: o AssetDeck nunca move,
renomeia ou apaga nada dentro dela. Os metadados (tags, notas, favoritos)
ficam num banco SQLite local, com um espelho em `.json` ao lado de cada
asset — se o banco se perder, os metadados voltam sozinhos na próxima
indexação.

## Requisitos

- Linux (desenvolvido e testado no Zorin OS)
- Python 3.12
- [Blender](https://www.blender.org/) 5.2, opcional — só necessário se você
  quiser usar a ponte com o Blender (arrastar assets direto pra cena).
  O projeto assume a versão via Flatpak:
  ```bash
  flatpak install flathub org.blender.Blender
  ```

## Instalação

Clone o repositório e entre na pasta:

```bash
git clone git@github.com:zsabados3523/AssetDeck.git
cd AssetDeck
```

Crie um ambiente virtual Python e instale as dependências (isola os
pacotes do projeto do resto do sistema, então não precisa de `sudo`):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Rodando o app

Com o ambiente virtual ativado (`source .venv/bin/activate`, se ainda não
estiver):

```bash
python -m assetdeck
```

Na primeira execução, o AssetDeck cria um `config.json` em
`~/.config/assetdeck/config.json` com uma biblioteca de exemplo. Pra
apontar pra uma biblioteca sua, edite a chave `"library_root"` nesse
arquivo com o caminho absoluto da pasta que você quer indexar (o app só
lê essa pasta — nunca escreve nela).

Dados do app ficam em (padrão XDG, não versionado no git):
- Config: `~/.config/assetdeck/config.json`
- Banco + backups + logs: `~/.local/share/assetdeck/`
- Cache de miniaturas: `~/.cache/assetdeck/`

### Atalho no menu de aplicativos (opcional)

```bash
python install_desktop_entry.py
```

Cria uma entrada no menu de aplicativos do sistema, pra abrir o AssetDeck
sem precisar do terminal depois da primeira instalação.

## Rodando os testes

```bash
pytest -q
```

## Estrutura do projeto

- `assetdeck/` — código do app (UI em PySide6/Qt, indexação, banco SQLite)
- `blender_addon/` — add-on do Blender (a "ponte": arrastar do AssetDeck
  aciona o menu nativo do Blender, com Append/Link e material PBR do set)
- `tests/` — suíte de testes (`pytest`)
- `PROJECT.md` — visão geral, decisões de arquitetura
- `SCHEMA.md` — modelo de dados do banco (fonte da verdade)
- `TODO.md` — roadmap e estado atual do projeto

## Sobre a biblioteca de teste

O repositório não inclui uma biblioteca de assets de exemplo — os arquivos
de teste automatizado (`pytest`) geram suas próprias imagens sintéticas
sob demanda, então **não é preciso nenhuma biblioteca real pra rodar os
testes ou contribuir com código**.

Se alguém te passou uma pasta de teste separada (fora do git, por conta
do tamanho), basta apontar `"library_root"` no `config.json` pra ela.
Vale checar a licença dos arquivos antes de reaproveitá-los em outro
lugar — bibliotecas de asset compradas costumam proibir redistribuição.

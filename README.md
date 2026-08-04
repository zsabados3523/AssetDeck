# AssetDeck

Gerenciador de assets 2D/3D local para Linux — texturas, HDRIs, modelos,
materiais PBR, LUTs, perfis de luz IES, vetores — com integração direta ao
Blender. Feito para uso pessoal: **100% offline**, sem conta, sem nuvem, sem
telemetria.

A biblioteca de arquivos é **somente-leitura**: o AssetDeck nunca move,
renomeia ou apaga nada dentro dela. Os metadados (tags, notas, favoritos,
avaliações) ficam num banco SQLite local, com um espelho em `.json` ao lado
de cada asset — se o banco se perder, os metadados voltam sozinhos na
próxima indexação.

<p align="center">
  <img src="docs/screenshots/biblioteca-escuro.png" alt="AssetDeck em modo escuro, com um HDRI selecionado" width="860">
</p>

## Para que serve

Você aponta o AssetDeck para uma pasta de assets já organizada no disco. Ele
indexa em segundo plano (sem travar a janela), gera miniaturas — inclusive
para `.hdr`/`.exr` com tonemap, que o Linux não teria como abrir de outro
jeito — e agrupa automaticamente os arquivos de um mesmo material PBR
(`_basecolor`, `_normal`, `_roughness`...) num card só. Daí em diante:

- **Organiza sem mexer no disco.** Tags hierárquicas com cor e apelido
  (`madeira` = `wood`), coleções manuais, coleções inteligentes (um filtro
  salvo que se atualiza sozinho), avaliação por estrelas e favoritos.
- **Acha o que você procura.** Busca por nome com operadores booleanos
  (`concreto E rústico`, `pedra OU metal`, `NÃO metal`), filtro por tipo de
  asset, extensão, nota, resolução e até por cor dominante da imagem.
- **Detecta duplicatas de verdade**, mesmo quando o arquivo mudou de
  resolução ou formato (hash perceptual de conteúdo visual, não só nome ou
  bytes idênticos).
- **Conversa com o Blender.** Um add-on próprio (a "ponte", não um
  importador) deixa arrastar um asset do AssetDeck direto para dentro da
  cena: HDRI vira World, um set PBR vira material com node group pronto,
  modelos entram por Append/Link. Também gera capas em lote renderizando
  dentro do Blender, headless.
- **Resolve manutenção chata de biblioteca grande:** renomear em lote com
  padrão de texto, religar texturas que sumiram do caminho original de um
  `.blend`, e apontar para mais de uma pasta-raiz (trocando qual está ativa
  pelo menu Arquivo).

## Screenshots

| Modo escuro | Modo claro |
|---|---|
| ![Modo escuro](docs/screenshots/biblioteca-escuro.png) | ![Modo claro](docs/screenshots/biblioteca-claro.png) |

Da esquerda para a direita: **lateral** com pastas, tags, coleções e coleções
inteligentes (cada seção com contador e recolhível); **grade** com os filtros
de tipo de asset e o caminho de navegação; **painel de detalhes** com
miniatura, ficha técnica, avaliação, galeria de previews e tags do asset
selecionado. O rodapé mostra se a ponte com o Blender está conectada e o
tamanho total da biblioteca.

## Requisitos

- Linux (desenvolvido e testado no Zorin OS)
- Python 3.12
- [Blender](https://www.blender.org/) 5.2, opcional — só necessário se você
  quiser usar a ponte com o Blender (arrastar assets direto pra cena). O
  projeto assume a versão via Flatpak:
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

### Ponte com o Blender (opcional)

Com o Blender 5.2 instalado via Flatpak, use **Ferramentas → Blender →
Instalar / atualizar add-on…** dentro do app para copiar o add-on da ponte
para a pasta de add-ons do Blender. Depois é só ativá-lo em *Edit →
Preferences → Add-ons* no Blender — ele aparece como um painel na barra
lateral (tecla `N`) das viewports 3D.

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

- `assetdeck/` — código do app
  - `ui/` — interface em PySide6/Qt (janela, tema, grade, painéis, diálogos)
  - `db/` — SQLite (conexão, migrations, repositórios)
  - `indexer/` — varredura de disco, agrupamento PBR, dependências
  - `thumbs/` — geração e cache de miniaturas (raster e HDR/EXR)
  - `bridge/` — servidor da ponte com o Blender (protocolo próprio via socket)
  - `blender/` — chamadas headless ao Blender (render de capas)
- `blender_addon/` — add-on do Blender (a ponte: recebe o que o AssetDeck
  arrasta e aciona o menu nativo do Blender)
- `tests/` — suíte de testes (`pytest`)
- `docs/screenshots/` — imagens usadas neste README
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

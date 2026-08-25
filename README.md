# AssetDeck

Gerenciador de assets 2D/3D local para Linux — texturas, HDRIs, modelos,
materiais PBR, LUTs, perfis de luz IES, vetores — com integração direta ao
Blender. Feito para uso pessoal: **100% offline**, sem conta, sem nuvem, sem
telemetria.

A biblioteca de arquivos é **somente-leitura por padrão**: o AssetDeck não
mexe em nada dentro dela por conta própria. Existem duas ações que escrevem
no disco, e as duas só acontecem quando você pede explicitamente —
**renomear em lote** e **mover assets** (arrastando um card da grade para
uma pasta). As duas mostram antes o que vai acontecer, e nunca apagam nada.

Os metadados (tags, notas, favoritos, avaliações) ficam num banco SQLite
local, com um espelho em `.json` ao lado de cada asset — se o banco se
perder, os metadados voltam sozinhos na próxima indexação.

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
- **Abre HDRI e modelo 3D de verdade, sem sair do app.** Duplo clique num
  `.hdr`/`.exr` abre um visualizador com a imagem projetada em volta da
  câmera (e um modo "esfera de reflexo", pra julgar a luz); num
  `.blend`/`.fbx`/`.obj`, o modelo aparece com câmera orbitando. Miniatura
  achatada não deixa avaliar nem luz nem forma.
- **Arruma a biblioteca sem sair do programa.** Arrastar assets da grade
  para uma pasta da árvore MOVE os arquivos no disco (com confirmação, e
  levando junto texturas, previews e sidecars do asset). É a saída pra
  aquele modelo que foi parar na pasta errada há dois anos.
- **Casa preview com modelo automaticamente.** `Cadeira.blend` +
  `Cadeira.jpg` viram um card só, com a imagem de capa — inclusive quando o
  pack traz vários previews numerados (`_001`, `_002`), como o Chaos Cosmos.
- **Resolve manutenção chata de biblioteca grande:** renomear em lote com
  padrão de texto, religar texturas que sumiram do caminho original de um
  `.blend`, e apontar para mais de uma pasta-raiz (trocando qual está ativa
  pelo seletor no canto superior direito).

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

### Visualizador de HDRI e de modelo 3D

<p align="center">
  <img src="docs/screenshots/visualizador-hdri.png" alt="Visualizador de HDRI, com a imagem projetada em volta da câmera" width="860">
</p>

Duplo clique num `.hdr`/`.exr` abre o HDRI projetado em volta da câmera —
arrastar gira a vista, e o modo **esfera de reflexo** põe uma esfera
espelhada no meio da cena pra julgar a luz. O mesmo visualizador atende
`.blend`, `.fbx` e `.obj`, aí com câmera orbitando e um botão para
reenquadrar o modelo.

## Requisitos

- Linux (desenvolvido e testado no Zorin OS)
- Python 3.12
- [Blender](https://www.blender.org/) 5.2, opcional — necessário para a
  ponte (arrastar assets direto pra cena), para gerar capas de modelos e
  para abrir `.blend` no visualizador 3D. O app aceita o Blender instalado
  via Flatpak **ou** um binário `blender` no `PATH`, nessa ordem:
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

### Indexar a biblioteca

O AssetDeck **não varre a biblioteca sozinho ao abrir** — numa biblioteca
grande isso são vários minutos de disco e CPU sem ninguém ter pedido. Quem
manda é o botão **Reindexar**, na barra de cima: clique nele depois de
copiar arquivos novos para a pasta.

Se você preferir o comportamento antigo, ligue **Configurações →
Manutenção → Varrer a biblioteca ao abrir**.

Dados do app ficam em (padrão XDG, não versionado no git):
- Config: `~/.config/assetdeck/config.json`
- Banco + backups + logs: `~/.local/share/assetdeck/`
- Cache de miniaturas: `~/.cache/assetdeck/`

Se o programa fechar sozinho alguma vez, `~/.local/share/assetdeck/logs/`
guarda dois arquivos úteis: `assetdeck.log` (o que ele estava fazendo) e
`quedas.txt` (onde ele estava no instante da queda).

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
  - `ui/` — interface em PySide6/Qt (janela, tema, grade, painéis, diálogos,
    visualizador 3D)
  - `db/` — SQLite (conexão, migrations, repositórios)
  - `indexer/` — varredura de disco, agrupamento PBR, dependências
  - `thumbs/` — geração e cache de miniaturas (raster e HDR/EXR)
  - `bridge/` — servidor da ponte com o Blender (protocolo próprio via socket)
  - `blender/` — chamadas headless ao Blender (render de capas)
  - `mover.py` — mover assets entre pastas (planeja, confirma, executa)
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

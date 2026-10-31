# Changelog

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

## [0.1.0] - 2026-10-31

### Adicionado
- Gerenciador de assets 2D e 3D local para Linux, Windows e macOS (texturas, HDRIs, modelos 3D, materiais PBR, LUTs, perfis de luz IES e vetores).
- Filosofia 100% offline: sem telemetria, sem contas de usuário e sem dependência de serviços externos ou nuvem.
- Biblioteca de arquivos estritamente somente-leitura por padrão, garantindo que o acervo original não seja modificado sem autorização explícita.
- Indexação e varredura de diretórios em segundo plano acionada sob demanda pelo usuário.
- Agrupamento automático de texturas de conjuntos de materiais PBR (`_basecolor`, `_normal`, `_roughness`, etc.) em um único card na grade.
- Geração e cache de miniaturas de alta qualidade, incluindo suporte a tonemap para imagens de alto alcance dinâmico (`.hdr` e `.exr`).
- Detecção de duplicatas por hash perceptual de conteúdo visual (identifica imagens semelhantes mesmo com redimensionamento ou mudança de formato).
- Sistema de organização com tags hierárquicas (com suporte a cores e apelidos), coleções manuais, coleções inteligentes por regras de filtro, favoritos e avaliação por estrelas.
- Armazenamento de metadados em banco de dados SQLite local, com rotina de backup automático e espelho `.json` sidecar ao lado de cada asset para recuperação de dados.
- Busca avançada por texto com operadores booleanos (`E`, `OU`, `NÃO`) e filtragem combinada por tipo de asset, extensão de arquivo, avaliação, resolução e cor dominante.
- Visualizador interativo integrado de HDRIs (projeção esférica 360° e esfera de reflexo espelhada) e modelos 3D (`.blend`, `.fbx`, `.obj`) com órbita de câmera e enquadramento.
- Associação automática de arquivos de capa a modelos 3D por correspondência de nome (`Cadeira.blend` + `Cadeira.jpg`) e suporte a variações numeradas.
- Ferramenta de renomeação em lote de arquivos com regras de substituição de texto e pré-visualização das alterações em disco.
- Funcionalidade de movimentação de assets arrastando cards da grade para pastas da árvore, movendo dependências (texturas e sidecars) com diálogo de confirmação.
- Ponte local com o Blender via socket TCP em `127.0.0.1` com autenticação por token seguro:
  - Add-on do Blender para inserção direta de HDRIs no World, materiais PBR com node groups configurados e modelos por Append/Link.
  - Renderização headless de capas e miniaturas diretamente através do executável do Blender.
- Suporte a múltiplos diretórios raiz de biblioteca com seletor rápido no topo da janela.
- Interface gráfica construída em PySide6/Qt com suporte nativo a modo claro e modo escuro.

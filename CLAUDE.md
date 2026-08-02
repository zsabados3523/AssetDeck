# AssetDeck — regras de trabalho

## Sobre o usuário
Rafael não programa. Explique cada comando ANTES de executar.
Nunca assuma conhecimento de terminal, git ou Python além do básico.
Rafael usa o app desktop, não o terminal — execute os comandos você mesmo.

## Regras absolutas
- A biblioteca de teste é "/home/rafael/00 - PROJETOS/assetdeck-testlib". NUNCA aponte para outro caminho.
- O app é somente-leitura sobre a biblioteca. Nada move, renomeia ou apaga.
- Nenhum `except` silencioso. Todo erro é logado com contexto.
- Nenhum dado mockado no código de produção. Mock só em teste.
- Não enfraqueça um teste para ele passar. Conserte o código.
- Se o escopo do que pedi não couber, me diga — não entregue parcial em silêncio.
- Antes de tocar no schema do banco, leia SCHEMA.md e me avise da mudança.
- Nenhum `setStyleSheet` fora de `ui/theme.py`. Cor, raio e fonte novos entram
  como token lá e viram `$nome` no `ui/theme.qss`.

## Fluxo
- Uma fatia por vez, em branch própria.
- Sempre rode pytest antes de dizer que terminou.
- Ao terminar: o que testar, como testar, e faça o commit você mesmo.

## Comandos do projeto
- Rodar app: source .venv/bin/activate && python -m assetdeck
- Testes: pytest -q
- Screenshot da UI: python -m assetdeck --screenshot /tmp/ui.png
- Blender (5.2, alvo do projeto): flatpak run org.blender.Blender

## Documentos de contexto
- PROJECT.md — visão, decisões e arquitetura de módulos.
- SCHEMA.md — modelo de dados. Fonte da verdade.
- TODO.md — roadmap e estado atual.
- REDESIGN.md — plano do redesign visual (F4), fatias 25 a 30.

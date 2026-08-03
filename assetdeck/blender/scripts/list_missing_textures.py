"""Roda DENTRO do Blender (blender -b -P) para listar texturas com
caminho quebrado num .blend. NUNCA escreve nada — nem no .blend, nem em
disco. Recebe, depois de '--': <arquivo.blend>

Tenta a mesma relocalização automática que render_thumb.py já faz
(bpy.ops.file.find_missing_files, só na cópia em memória) e reporta só o
que CONTINUA quebrado depois — é o que sobraria pro usuário resolver
manualmente, já que o render já resolve o resto sozinho.

Duplica ~15 linhas de render_thumb.py de propósito, em vez de importar
de lá: aquele script chama main() incondicionalmente no nível do módulo
(sem guarda de __main__), então importar de lá dispararia um render
inteiro por engano.
"""

import json
import os
import sys

import bpy

NIVEIS_BUSCA = 2  # quantas pastas subir procurando texturas perdidas


def texturas_perdidas():
    return [img for img in bpy.data.images
            if img.filepath and img.source == "FILE"
            and not os.path.isfile(bpy.path.abspath(img.filepath))]


def relocalizar(blend_path):
    """Mesma lógica de render_thumb.py::relocalizar_texturas — só que
    aqui o resultado importa é a CONTAGEM recuperada, não o efeito
    colateral (que já é o mesmo: só ajusta a cópia em memória)."""
    perdidas = texturas_perdidas()
    if not perdidas:
        return 0
    base = os.path.dirname(os.path.abspath(blend_path))
    for _ in range(NIVEIS_BUSCA):
        base = os.path.dirname(base)
        try:
            bpy.ops.file.find_missing_files(directory=base)
        except Exception as exc:  # noqa: BLE001 — nunca derruba a checagem
            print("ASSETDECK_AVISO relocalizacao falhou:", exc, flush=True)
            break
        if not texturas_perdidas():
            break
    return len(perdidas) - len(texturas_perdidas())


def argumentos():
    if "--" not in sys.argv:
        raise SystemExit("Uso: blender -b -P list_missing_textures.py -- entrada.blend")
    resto = sys.argv[sys.argv.index("--") + 1:]
    if not resto:
        raise SystemExit("Falta o argumento: entrada.blend")
    return resto[0]


def main():
    entrada = argumentos()
    bpy.ops.wm.open_mainfile(filepath=entrada)
    recuperadas = relocalizar(entrada)

    perdidas = [
        {"nome": img.name, "caminho_esperado": bpy.path.abspath(img.filepath)}
        for img in texturas_perdidas()
    ]
    saida = {"perdidas": perdidas, "recuperadas_auto": recuperadas}
    print("ASSETDECK_TEXTURAS_JSON " + json.dumps(saida), flush=True)


main()

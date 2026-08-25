"""O rastreador de quedas (Fatia 99).

Uma queda de nível C++ — falha de segmentação no Qt/OpenGL — não deixa
traceback nenhum: o processo some e o log termina no meio da frase. Foi
exatamente o que aconteceu com o "o programa simplesmente fecha" ao mexer
em tags, em 2026-08-23, e por isso o defeito segue sem diagnóstico.

O teste mais importante daqui derruba um processo DE VERDADE e confere que
sobrou pilha em disco. Sem isso, o resto é só conferir que uma função foi
chamada.
"""

import subprocess
import sys

from assetdeck.logging_setup import armar_rastreador_de_quedas


def test_o_arquivo_de_quedas_e_criado_e_anota_a_abertura(tmp_path):
    destino = armar_rastreador_de_quedas(tmp_path)

    assert destino == tmp_path / "quedas.txt"
    assert destino.exists()
    assert "AssetDeck iniciado" in destino.read_text(encoding="utf-8")


def test_o_arquivo_acumula_em_vez_de_apagar(tmp_path):
    """Uma queda que só acontece de vez em quando não pode depender de
    alguém estar olhando na hora — o registro anterior tem de sobreviver à
    próxima abertura."""
    armar_rastreador_de_quedas(tmp_path)
    (tmp_path / "quedas.txt").write_text("marca antiga\n", encoding="utf-8")
    armar_rastreador_de_quedas(tmp_path)

    assert "marca antiga" in (tmp_path / "quedas.txt").read_text(encoding="utf-8")


def test_uma_queda_de_verdade_deixa_a_pilha_em_disco(tmp_path):
    """Derruba um processo com falha de segmentação real e exige que o
    arquivo tenha a pilha do Python.

    `faulthandler._sigsegv()` provoca a falha de propósito — é como o
    próprio CPython testa isso. Num subprocesso, claro: o pytest não
    sobreviveria.
    """
    script = f'''
import sys
sys.path.insert(0, {str(__import__("pathlib").Path(__file__).parent.parent)!r})
from assetdeck.logging_setup import armar_rastreador_de_quedas
armar_rastreador_de_quedas(__import__("pathlib").Path({str(tmp_path)!r}))

def funcao_que_derruba_o_processo():
    import faulthandler
    faulthandler._sigsegv()

funcao_que_derruba_o_processo()
'''
    r = subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=60)

    assert r.returncode != 0, "o processo devia ter caído"
    registro = (tmp_path / "quedas.txt").read_text(encoding="utf-8")
    assert "Fatal Python error" in registro, (
        f"a queda não deixou pilha nenhuma:\n{registro}")
    assert "funcao_que_derruba_o_processo" in registro, (
        "a pilha não diz ONDE o processo estava — que é o único motivo "
        f"disto existir:\n{registro}")

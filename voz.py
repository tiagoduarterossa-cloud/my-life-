"""
Voz neural para o Rosserini: transforma texto em som com as vozes do Microsoft Edge (pacote edge-tts).
Soa muito mais natural do que a voz do tablet. Precisa de internet e de: pip install edge-tts

Os sons ficam guardados na pasta vozes/ (fora do GitHub). Frases repetidas nao voltam a ser pedidas.
Se alguma coisa falhar, devolve None e a central usa a voz do tablet.
"""

import asyncio
import hashlib
from pathlib import Path

PASTA = Path(__file__).resolve().parent / "vozes"

# vozes em portugues. As de Portugal primeiro.
VOZES = [
    ("pt-PT-DuarteNeural", "Duarte (Portugal, rapaz)"),
    ("pt-PT-RaquelNeural", "Raquel (Portugal, rapariga)"),
    ("pt-BR-AntonioNeural", "António (Brasil)"),
    ("pt-BR-FranciscaNeural", "Francisca (Brasil)"),
    ("pt-BR-ThalitaMultilingualNeural", "Thalita (Brasil)"),
]


def disponivel():
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


def _ajuste(valor, unidade):
    """0.1 -> '+10%'; -5 -> '-5Hz'"""
    v = round(valor)
    return f"{'+' if v >= 0 else ''}{v}{unidade}"


def gerar(texto, voz="pt-PT-DuarteNeural", velocidade=1.08, tom=1.05):
    """devolve o caminho de um mp3 com o texto dito, ou None se nao der"""
    if not texto or not disponivel():
        return None
    if voz not in {v for v, _ in VOZES}:
        voz = VOZES[0][0]
    rate = _ajuste((velocidade - 1) * 100, "%")       # 1.08 -> +8%
    pitch = _ajuste((tom - 1) * 60, "Hz")             # 1.05 -> +3Hz
    chave = hashlib.sha1(f"{voz}|{rate}|{pitch}|{texto}".encode()).hexdigest()[:20]
    PASTA.mkdir(exist_ok=True)
    caminho = PASTA / f"{chave}.mp3"
    if caminho.exists() and caminho.stat().st_size > 0:
        return caminho
    try:
        import edge_tts

        async def _gravar():
            await edge_tts.Communicate(texto, voz, rate=rate, pitch=pitch).save(str(caminho))
        asyncio.run(asyncio.wait_for(_gravar(), timeout=20))
        if caminho.exists() and caminho.stat().st_size > 0:
            _arrumar()
            return caminho
    except Exception as e:
        print("voz neural falhou:", e)
    caminho.unlink(missing_ok=True)
    return None


def _arrumar(maximo=300):
    """nao deixa a pasta crescer para sempre: apaga os sons mais antigos"""
    sons = sorted(PASTA.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
    for p in sons[:-maximo]:
        p.unlink(missing_ok=True)

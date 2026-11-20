"""
Testes do Jarvis: verifica que cada frase de testes/frases.json continua a ser percebida como deve.
Corre com:  python testes/correr.py      (sai com erro se alguma frase falhar)
So usa a biblioteca padrao, para correr tambem no Termux.
"""
import json
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import assistente  # noqa: E402


def _igual(esperado, obtido):
    if isinstance(obtido, date):
        obtido = obtido.isoformat()
    return esperado == obtido


def correr(caminho=RAIZ / "testes" / "frases.json", mostrar=True):
    d = json.loads(Path(caminho).read_text(encoding="utf-8"))
    hoje = date.fromisoformat(d["hoje"])
    falhas = []
    for c in d["frases"]:
        intencao, campos = assistente.entender(c["frase"], hoje)
        erros = []
        if intencao != c["intencao"]:
            erros.append(f"intenção {intencao!r}, devia ser {c['intencao']!r}")
        for k, v in (c.get("campos") or {}).items():
            if not _igual(v, (campos or {}).get(k)):
                erros.append(f"{k} = {(campos or {}).get(k)!r}, devia ser {v!r}")
        if erros:
            falhas.append((c, erros))
    if mostrar:
        for c, erros in falhas:
            print(f"FALHOU  \"{c['frase']}\": " + "; ".join(erros) + (f"  ({c['nota']})" if c.get("nota") else ""))
        print(f"{len(d['frases']) - len(falhas)} de {len(d['frases'])} frases certas.")
    return falhas


if __name__ == "__main__":
    sys.exit(1 if correr() else 0)

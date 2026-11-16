"""
Camada 3 das rotinas: os aparelhos do quarto.

Para ja: tomada inteligente Shelly (Plug S, Plus Plug S, Gen3...). Fala com ela diretamente na rede de casa,
sem passar pela internet. Basta escrever o IP da tomada nas definicoes da central.

Para juntar outro aparelho: escreve uma funcao como tomada() e acrescenta a acao em rotinas.ACOES.
"""

import json
import urllib.request


def _pedir(url):
    with urllib.request.urlopen(url, timeout=4) as r:
        return json.loads(r.read() or b"{}")


def tomada(ip, estado):
    """estado: 'ligar', 'desligar' ou 'alternar'. Devolve (ok, mensagem).
    Experimenta primeiro a maneira das Shelly novas (Gen2/Gen3) e depois a das antigas (Gen1)."""
    if not ip:
        return False, "Ainda não configuraste a tomada (roda dentada > Dispositivos)."
    ip = ip.strip().replace("http://", "").strip("/")
    novas = {"ligar": "Switch.Set?id=0&on=true", "desligar": "Switch.Set?id=0&on=false", "alternar": "Switch.Toggle?id=0"}
    antigas = {"ligar": "on", "desligar": "off", "alternar": "toggle"}
    if estado not in novas:
        return False, "Estado inválido."
    try:
        _pedir(f"http://{ip}/rpc/{novas[estado]}")
        return True, "ok"
    except Exception:
        pass
    try:
        _pedir(f"http://{ip}/relay/0?turn={antigas[estado]}")
        return True, "ok"
    except Exception as e:
        return False, f"Não consegui falar com a tomada em {ip} ({e.__class__.__name__}). Está ligada e no mesmo Wi-Fi?"

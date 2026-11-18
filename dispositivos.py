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


# ---------- fita LED com WLED (cores, brilho, efeitos) ----------
# WLED e um programa gratis para controladores de fitas LED. Fala-se com ele na rede de casa: POST http://IP/json/state

CORES = {
    "vermelho": (255, 0, 0), "vermelha": (255, 0, 0), "azul": (0, 60, 255), "verde": (0, 255, 60), "roxo": (150, 0, 255),
    "roxa": (150, 0, 255), "rosa": (255, 0, 120), "laranja": (255, 90, 0), "amarelo": (255, 190, 0), "amarela": (255, 190, 0),
    "branco": (255, 255, 255), "branca": (255, 255, 255), "ciano": (0, 220, 255), "dourado": (255, 150, 30), "quente": (255, 140, 60),
}


def wled(ip, cor=None, brilho=None, ligar=None):
    """cor: (r, g, b); brilho: 0-100 %; ligar: True/False. Devolve (ok, mensagem)."""
    if not ip:
        return False, "Ainda não configuraste a fita LED (roda dentada > Dispositivos)."
    ip = ip.strip().replace("http://", "").strip("/")
    estado = {}
    if ligar is not None:
        estado["on"] = bool(ligar)
    if cor is not None:
        estado.update(on=True, seg=[{"col": [list(cor)]}])
    if brilho is not None:
        estado.update(on=True, bri=max(1, min(255, round(brilho * 2.55))))
    try:
        req = urllib.request.Request(f"http://{ip}/json/state", data=json.dumps(estado).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=4) as r:
            r.read()
        return True, "ok"
    except Exception as e:
        return False, f"Não consegui falar com a fita LED em {ip} ({e.__class__.__name__}). Está ligada e no mesmo Wi-Fi?"

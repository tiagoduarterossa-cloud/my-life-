"""
O que esta a funcionar: o Wi-Fi de casa, a internet e os servicos que mais usas.

E tudo visto A PARTIR DA TUA CASA: a central tenta mesmo ligar-se a cada servico e mede quanto tempo demora.
Nao ha nenhuma fonte publica que diga "o WhatsApp esta em baixo em Portugal", por isso a central faz o que
da para fazer a serio: se a internet funciona e so um servico falha, o problema e desse servico; se falha
tudo, o problema e a tua internet (ou o router, ou um apagao).
"""

import json
import shutil
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# (nome, grupo, endereco a testar)
SERVICOS = [
    ("Google", "internet", "https://www.google.com/generate_204"),
    ("Cloudflare", "internet", "https://1.1.1.1/cdn-cgi/trace"),
    ("WhatsApp", "comunicar", "https://web.whatsapp.com/"),
    ("Instagram", "comunicar", "https://www.instagram.com/"),
    ("TikTok", "comunicar", "https://www.tiktok.com/"),
    ("YouTube", "comunicar", "https://www.youtube.com/"),
    ("Microsoft Teams", "escola", "https://teams.microsoft.com/"),
    ("Spotify", "lazer", "https://open.spotify.com/"),
    ("SNS 24", "serviços públicos", "https://www.sns24.gov.pt/"),
    ("Proteção Civil", "serviços públicos", "https://prociv.gov.pt/"),
    ("IPMA", "serviços públicos", "https://www.ipma.pt/"),
    ("RTP Notícias", "notícias", "https://www.rtp.pt/noticias/"),
    ("CP Comboios", "transportes", "https://www.cp.pt/"),
    ("Metro de Lisboa", "transportes", "https://www.metrolisboa.pt/"),
]


def _testar_url(nome, grupo, url):
    t0 = time.time()
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0 (central do quarto; verificacao)"})
    try:
        with urllib.request.urlopen(req, timeout=6, context=ssl.create_default_context()) as r:
            r.read(2000)
            codigo = r.status
    except urllib.error.HTTPError as e:
        codigo = e.code          # o site respondeu (mesmo com erro): esta vivo
    except Exception as e:
        return {"nome": nome, "grupo": grupo, "ok": False, "ms": None, "erro": e.__class__.__name__}
    ms = round((time.time() - t0) * 1000)
    # 5xx = o servico respondeu mas esta com problemas
    return {"nome": nome, "grupo": grupo, "ok": codigo < 500, "ms": ms, "lento": ms > 3000, "codigo": codigo}


def _porta(ip, porta, t=2):
    try:
        with socket.create_connection((ip, porta), timeout=t):
            return True
    except OSError:
        return False


def _gateway():
    try:
        out = subprocess.run(["ip", "route"], capture_output=True, timeout=5, text=True).stdout
        for linha in out.splitlines():
            if linha.startswith("default via "):
                return linha.split()[2]
    except Exception:
        pass
    return None


def _wifi():
    if not shutil.which("termux-wifi-connectioninfo"):
        return None
    try:
        d = json.loads(subprocess.run(["termux-wifi-connectioninfo"], capture_output=True, timeout=15).stdout or b"null")
    except Exception:
        return None
    if not d:
        return None
    rssi = d.get("rssi")
    sinal = None if rssi is None else "excelente" if rssi >= -55 else "bom" if rssi >= -67 else "fraco" if rssi >= -78 else "muito fraco"
    return {"rede": (d.get("ssid") or "").strip('"'), "rssi": rssi, "sinal": sinal, "velocidade": d.get("link_speed_mbps"),
            "ip": d.get("ip"), "ligado": d.get("supplicant_state") == "COMPLETED"}


def verificar():
    """{wifi, router, internet, dns, servicos[], conclusao, quando}"""
    r = {"quando": time.strftime("%H:%M"), "wifi": _wifi()}
    gw = _gateway()
    r["router"] = {"ip": gw, "ok": bool(gw) and (_porta(gw, 80) or _porta(gw, 53) or _porta(gw, 443))} if gw else {"ip": None, "ok": None}
    r["internet"] = _porta("1.1.1.1", 443, 3) or _porta("8.8.8.8", 53, 3)
    try:
        socket.getaddrinfo("www.google.com", 443); r["dns"] = True
    except OSError:
        r["dns"] = False
    if r["internet"] and r["dns"]:
        with ThreadPoolExecutor(8) as ex:
            r["servicos"] = list(ex.map(lambda s: _testar_url(*s), SERVICOS))
    else:
        r["servicos"] = [{"nome": n, "grupo": g, "ok": False, "ms": None, "erro": "sem internet"} for n, g, _ in SERVICOS]
    r["conclusao"] = conclusao(r)
    return r


def conclusao(r):
    falham = [s["nome"] for s in r["servicos"] if not s["ok"]]
    if r["router"]["ok"] is False:
        return "O router não responde. Pode ter faltado a luz, ou o router está desligado ou avariado."
    if not r["internet"]:
        return "O Wi-Fi está ligado mas não há internet. O problema é a ligação do teu operador (ou um apagão na rua). Não é dos sites."
    if not r["dns"]:
        return "Há internet mas os nomes dos sites não se resolvem (DNS). Reiniciar o router costuma resolver."
    if not falham:
        lentos = [s["nome"] for s in r["servicos"] if s.get("lento")]
        return "Está tudo a funcionar." + (f" Lentos: {', '.join(lentos)}." if lentos else "")
    if len(falham) >= len(r["servicos"]) * 0.7:
        return "Quase nada responde, mas a ligação base existe. Deve ser um problema grande na rede do operador."
    return (f"A tua internet está bem. Não responde: {', '.join(falham)}. "
            "Quando só um serviço falha, o problema é do serviço e não teu. Confirma noutro aparelho ou com amigos.")


def frase(r):
    w = r.get("wifi")
    f = r["conclusao"]
    if w and w.get("sinal") in ("fraco", "muito fraco"):
        f += f" Atenção: o sinal do Wi-Fi aqui é {w['sinal']}."
    return f

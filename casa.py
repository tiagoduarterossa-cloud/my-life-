"""
A casa: sensores (janelas, portas), estado das luzes e verificacao da seguranca da rede de casa.

Sensores de janela/porta (ex.: Shelly Door/Window): nas "acoes" do sensor configura-se um URL para quando
abre e outro para quando fecha, apontados para a central:
    http://IP-DO-TABLET:8080/api/sensor?nome=janela-quarto&estado=aberta
    http://IP-DO-TABLET:8080/api/sensor?nome=janela-quarto&estado=fechada

Rede: so verifica a TUA rede e o TEU router (encriptacao do Wi-Fi, WPS, portas perigosas do router).
Nao ataca nem varre os aparelhos dos outros. Precisa da app Termux:API (com autorizacao de localizacao,
que o Android exige para ver as redes Wi-Fi).
"""

import json
import re
import shutil
import socket
import subprocess
import urllib.request

TABELAS = """
CREATE TABLE IF NOT EXISTS sensores (
    nome TEXT PRIMARY KEY,
    estado TEXT NOT NULL,
    quando TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""

ABERTOS = {"aberta", "aberto", "open", "1", "on", "true"}


def registar_sensor(con, nome, estado):
    nome = re.sub(r"[^\w\- ]", "", nome or "")[:40].strip() or "sensor"
    estado = (estado or "").strip().lower()[:20]
    con.execute("INSERT OR REPLACE INTO sensores (nome, estado, quando) VALUES (?,?,datetime('now','localtime'))", (nome, estado))
    return nome, estado


def _json(url, dados=None, metodo=None):
    req = urllib.request.Request(url, data=json.dumps(dados).encode() if dados is not None else None, method=metodo,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read() or b"{}")


def luzes(cfg):
    """[(nome, ligada True/False/None)]"""
    out = []
    if cfg.get("wled_ip"):
        try:
            out.append(("fita LED", bool(_json(f"http://{cfg['wled_ip']}/json/state").get("on"))))
        except Exception:
            out.append(("fita LED", None))
    if cfg.get("tomada_ip"):
        ip = cfg["tomada_ip"]
        try:
            out.append(("tomada", bool(_json(f"http://{ip}/rpc/Switch.GetStatus?id=0").get("output"))))
        except Exception:
            try:
                out.append(("tomada", bool(_json(f"http://{ip}/relay/0").get("ison"))))
            except Exception:
                out.append(("tomada", None))
    return out


def estado_casa(con, cfg):
    sens = [dict(r) for r in con.execute("SELECT * FROM sensores ORDER BY nome")]
    abertos = [s for s in sens if s["estado"] in ABERTOS]
    lz = luzes(cfg)
    return {"sensores": sens, "abertos": [s["nome"] for s in abertos],
            "luzes": [{"nome": n, "ligada": l} for n, l in lz], "luzes_ligadas": [n for n, l in lz if l]}


def frase_casa(e):
    partes = []
    if e["abertos"]:
        partes.append(f"Tens {'aberta' if len(e['abertos']) == 1 else 'abertas'}: {', '.join(e['abertos'])}.")
    if e["luzes_ligadas"]:
        partes.append(f"Está ligada: {', '.join(e['luzes_ligadas'])}.")
    if not partes:
        if not e["sensores"] and not e["luzes"]:
            return "Ainda não tenho sensores nem luzes ligados à central, por isso não consigo ver."
        return "Está tudo fechado e desligado."
    return " ".join(partes)


# ---------- seguranca da rede de casa ----------

PORTAS = {  # porta: (nome, nivel se estiver aberta no router, explicacao)
    23: ("Telnet", "perigo", "O Telnet é antigo e envia tudo sem encriptação, incluindo a palavra-passe. Deve estar desligado."),
    21: ("FTP", "cuidado", "Partilha de ficheiros sem encriptação. Se ninguém usa, deve estar desligado."),
    7547: ("TR-069", "cuidado", "Serve para o operador gerir o router à distância. Já houve ataques famosos por aqui; é normal em routers de operadoras."),
    5000: ("UPnP", "cuidado", "Deixa aparelhos abrirem portas sozinhos. Prático, mas os vírus também o usam."),
    22: ("SSH", "cuidado", "Acesso de administração. Se não sabes porque está ligado, pergunta a quem configurou o router."),
    80: ("página do router (http)", "info", "A página de configuração do router. Normal, mas confirma que a palavra-passe não é a que veio de fábrica."),
}


def _termux(cmd):
    if not shutil.which(cmd):
        return None
    try:
        return json.loads(subprocess.run([cmd], capture_output=True, timeout=20).stdout or b"null")
    except Exception:
        return None


def _gateway(ip):
    try:
        out = subprocess.run(["ip", "route"], capture_output=True, timeout=5, text=True).stdout
        m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", out)
        if m:
            return m[1]
    except Exception:
        pass
    return ".".join(ip.split(".")[:3] + ["1"]) if ip and ip.count(".") == 3 else None


def _porta_aberta(ip, porta):
    try:
        with socket.create_connection((ip, porta), timeout=0.8):
            return True
    except OSError:
        return False


def verificar_rede(ip_tablet=None):
    """devolve {nota: 0-100, verificacoes: [{nivel, titulo, texto}], wifi, router}"""
    v = []
    info = _termux("termux-wifi-connectioninfo") or {}
    ssid = (info.get("ssid") or "").strip('"')
    ip = info.get("ip") or ip_tablet
    rede = None
    scan = _termux("termux-wifi-scaninfo")
    if isinstance(scan, list) and ssid:
        rede = next((r for r in scan if r.get("ssid") == ssid), None)
    caps = (rede or {}).get("capabilities", "") if rede else ""
    if info == {} and scan is None:
        v.append({"nivel": "info", "titulo": "Wi-Fi", "texto": "Para ver a encriptação do Wi-Fi é preciso a app Termux:API (com autorização de localização)."})
    elif not caps:
        v.append({"nivel": "info", "titulo": "Wi-Fi", "texto": "Não consegui ler a encriptação da rede. Dá autorização de localização à app Termux:API e tenta outra vez."})
    elif "WPA3" in caps or "SAE" in caps:
        v.append({"nivel": "ok", "titulo": f"Wi-Fi «{ssid}»", "texto": "Usa WPA3, a encriptação mais recente e mais segura."})
    elif "WPA2" in caps or "RSN" in caps:
        tkip = "TKIP" in caps and "CCMP" not in caps
        v.append({"nivel": "cuidado" if tkip else "ok", "titulo": f"Wi-Fi «{ssid}»",
                  "texto": "Usa WPA2" + (" com TKIP, que é fraco: muda para AES/CCMP nas definições do router." if tkip else " com AES. É seguro, desde que a palavra-passe seja longa.")})
    elif "WEP" in caps:
        v.append({"nivel": "perigo", "titulo": f"Wi-Fi «{ssid}»", "texto": "Usa WEP, que se parte em minutos. É preciso mudar para WPA2 ou WPA3 já."})
    else:
        v.append({"nivel": "perigo", "titulo": f"Wi-Fi «{ssid}»", "texto": "A rede parece ABERTA, sem palavra-passe. Qualquer pessoa entra e pode ver o que se passa."})
    if "WPS" in caps:
        v.append({"nivel": "cuidado", "titulo": "WPS ligado", "texto": "O WPS (o botão/PIN para ligar aparelhos) tem falhas conhecidas. Se não o usam, desliguem-no no router."})
    router = _gateway(ip)
    if router:
        abertas = [p for p in PORTAS if _porta_aberta(router, p)]
        for p in abertas:
            nome, nivel, txt = PORTAS[p]
            v.append({"nivel": nivel, "titulo": f"Router: {nome} (porta {p}) aberto", "texto": txt})
        if not [p for p in abertas if PORTAS[p][1] in ("perigo", "cuidado")]:
            v.append({"nivel": "ok", "titulo": "Router", "texto": "Não encontrei portas perigosas abertas no router."})
    else:
        v.append({"nivel": "info", "titulo": "Router", "texto": "Não consegui descobrir o endereço do router."})
    v.append({"nivel": "info", "titulo": "Central", "texto": "A central não tem palavra-passe: qualquer pessoa no Wi-Fi de casa consegue usá-la. Põe um PIN (desafio 1 do README)."})
    pesos = {"ok": 0, "info": 0, "cuidado": 15, "perigo": 40}
    verificado = any(x["nivel"] != "info" for x in v)   # so ha nota se se conseguiu mesmo verificar alguma coisa
    nota = max(0, 100 - sum(pesos[x["nivel"]] for x in v)) if verificado else None
    return {"nota": nota, "verificacoes": v, "wifi": ssid, "router": router}


def frase_rede(r):
    if r["nota"] is None:
        return "Não consegui verificar a rede, por isso não te posso dizer se está segura. " + r["verificacoes"][0]["texto"]
    maus = [x for x in r["verificacoes"] if x["nivel"] in ("perigo", "cuidado")]
    if not maus:
        return f"A rede de casa parece segura: nota {r['nota']} em 100."
    pior = sorted(maus, key=lambda x: x["nivel"] != "perigo")[0]
    return f"Nota {r['nota']} em 100. Encontrei {len(maus)} coisa{'s' if len(maus) > 1 else ''} a melhorar. A mais importante: {pior['titulo']}. {pior['texto']}"

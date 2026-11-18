"""
Desastres naturais e apagoes.

- Avisos do IPMA (tempo perigoso) para o distrito mais perto da tua cidade
- Sismos (USGS): perto de ti (menos de 500 km) e os grandes no mundo inteiro
- Incendios ativos em Portugal (fogos.pt, servico da comunidade)
- Apagoes: o tablet esta sempre a carregar; se deixa de carregar de repente, provavelmente faltou a luz.
  Tambem avisa quando a internet cai. Precisa da app Termux:API.
"""

import json
import math
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from datetime import datetime

IPMA = os.environ.get("VIDA_IPMA", "https://api.ipma.pt/open-data/forecast/warnings/warnings_www.json")
USGS = os.environ.get("VIDA_USGS", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson")
FOGOS = os.environ.get("VIDA_FOGOS", "https://api.fogos.pt/v2/incidents/active")

DISTRITOS = {  # codigo IPMA: (nome, lat, lon)
    "AVR": ("Aveiro", 40.64, -8.65), "BJA": ("Beja", 38.02, -7.86), "BRG": ("Braga", 41.55, -8.42), "BGC": ("Bragança", 41.81, -6.76),
    "CBO": ("Castelo Branco", 39.82, -7.49), "CBR": ("Coimbra", 40.21, -8.43), "EVR": ("Évora", 38.57, -7.91), "FAR": ("Faro", 37.02, -7.93),
    "GDA": ("Guarda", 40.54, -7.27), "LRA": ("Leiria", 39.74, -8.81), "LSB": ("Lisboa", 38.72, -9.14), "PTG": ("Portalegre", 39.29, -7.43),
    "PTO": ("Porto", 41.15, -8.61), "STM": ("Santarém", 39.24, -8.69), "STB": ("Setúbal", 38.52, -8.89), "VCT": ("Viana do Castelo", 41.69, -8.83),
    "VRL": ("Vila Real", 41.30, -7.74), "VIS": ("Viseu", 40.66, -7.91), "MCS": ("Madeira", 32.65, -16.91),
}
NIVEIS = {"yellow": "amarelo", "orange": "laranja", "red": "vermelho"}
_cache, _lock = {}, threading.Lock()


def _json(url, validade=600):
    with _lock:
        c = _cache.get(url)
        if c and time.time() - c[0] < validade:
            return c[1]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (central do quarto)"})
    with urllib.request.urlopen(req, timeout=8) as r:
        d = json.loads(r.read(10_000_000))
    with _lock:
        _cache[url] = (time.time(), d)
    return d


def km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def distrito(lat, lon):
    return min(DISTRITOS, key=lambda k: km(lat, lon, DISTRITOS[k][1], DISTRITOS[k][2]))


def avisos_ipma(lat, lon):
    cod = distrito(lat, lon)
    agora = datetime.now().isoformat()[:16]
    out = []
    for a in _json(IPMA):
        if a.get("idAreaAviso") != cod or a.get("awarenessLevelID") not in NIVEIS:
            continue
        if (a.get("endTime") or "9999")[:16] < agora:
            continue
        out.append({"tipo": a.get("awarenessTypeName", "Tempo"), "nivel": NIVEIS[a["awarenessLevelID"]],
                    "ate": (a.get("endTime") or "")[11:16], "texto": (a.get("text") or "").strip()})
    ordem = {"vermelho": 0, "laranja": 1, "amarelo": 2}
    return {"distrito": DISTRITOS[cod][0], "avisos": sorted(out, key=lambda x: ordem[x["nivel"]])}


def sismos(lat, lon):
    perto, grandes = [], []
    for f in _json(USGS).get("features", []):
        p, (x, y, *_) = f["properties"], f["geometry"]["coordinates"]
        mag = p.get("mag") or 0
        d = km(lat, lon, y, x)
        s = {"mag": round(mag, 1), "onde": p.get("place", ""), "km": round(d), "hora": datetime.fromtimestamp(p["time"] / 1000).strftime("%H:%M")}
        if d < 500:
            perto.append(s)
        elif mag >= 6:
            grandes.append(s)
    return {"perto": sorted(perto, key=lambda s: -s["mag"])[:5], "grandes": sorted(grandes, key=lambda s: -s["mag"])[:3]}


def incendios(lat, lon):
    d = _json(FOGOS, 300)
    lista = d.get("data", d if isinstance(d, list) else [])
    perto = []
    for f in lista:
        try:
            dist = km(lat, lon, float(f.get("lat")), float(f.get("lng")))
        except (TypeError, ValueError):
            continue
        if dist < 40:
            perto.append({"onde": f.get("location") or f.get("concelho") or "", "km": round(dist), "estado": f.get("status", "")})
    return {"total_pais": len(lista), "perto": sorted(perto, key=lambda x: x["km"])[:5]}


def resumo(cfg):
    """junta tudo; cada parte pode falhar sozinha (sem internet, site em baixo)"""
    if not cfg.get("lat"):
        return {"erro": "Escolhe primeiro a tua cidade (roda dentada > Cidade)."}
    lat, lon = float(cfg["lat"]), float(cfg["lon"])
    r = {}
    for nome, f in (("ipma", avisos_ipma), ("sismos", sismos), ("fogos", incendios)):
        try:
            r[nome] = f(lat, lon)
        except Exception as e:
            r[nome] = {"erro": str(e.__class__.__name__)}
    r["energia"] = estado_energia()
    return r


def frase(r):
    if r.get("erro"):
        return r["erro"]
    partes = []
    ip = r.get("ipma", {})
    if ip.get("avisos"):
        a = ip["avisos"][0]
        partes.append(f"Segundo o IPMA, há aviso {a['nivel']} de {a['tipo'].lower()} em {ip['distrito']}" + (f" até às {a['ate']}" if a["ate"] else "") +
                      (f", e mais {len(ip['avisos']) - 1}" if len(ip["avisos"]) > 1 else "") + ".")
    sm = r.get("sismos", {})
    if sm.get("perto"):
        s = sm["perto"][0]
        partes.append(f"Segundo o USGS, houve um sismo de magnitude {s['mag']} a {s['km']} quilómetros, às {s['hora']}.")
    if sm.get("grandes"):
        s = sm["grandes"][0]
        partes.append(f"No mundo, o USGS registou um sismo forte de {s['mag']}: {s['onde']}.")
    fg = r.get("fogos", {})
    if fg.get("perto"):
        partes.append(f"Segundo os dados da Proteção Civil no fogos.pt, há {len(fg['perto'])} incêndio{'s' if len(fg['perto']) > 1 else ''} ativo{'s' if len(fg['perto']) > 1 else ''} a menos de 40 quilómetros, o mais perto a {fg['perto'][0]['km']}.")
    en = r.get("energia", {})
    if en.get("sem_luz"):
        partes.append(f"E parece que faltou a luz desde as {en['desde']}: o tablet está a funcionar a bateria.")
    if not partes:
        falhas = [k for k in ("ipma", "sismos", "fogos") if r.get(k, {}).get("erro")]
        nomes = {"ipma": "o IPMA", "sismos": "o USGS", "fogos": "o fogos.pt"}
        if len(falhas) == 3:
            return "Não consegui falar com nenhuma das fontes (IPMA, USGS, fogos.pt). Sem internet? Não vou adivinhar."
        return ("Tudo calmo: sem avisos do IPMA, sem sismos por perto e sem incêndios perto de ti." +
                (f" Atenção: {', '.join(nomes[f] for f in falhas)} não respondeu, por isso essa parte não sei." if falhas else ""))
    return " ".join(partes)


# ---------- apagoes e internet ----------

_energia = {"ligado": None, "desde": None, "sem_internet_desde": None, "historico": []}


def _bateria():
    if not shutil.which("termux-battery-status"):
        return None
    try:
        return json.loads(subprocess.run(["termux-battery-status"], capture_output=True, timeout=15).stdout or b"null")
    except Exception:
        return None


def _internet():
    for host in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            with socket.create_connection(host, timeout=3):
                return True
        except OSError:
            pass
    return False


def estado_energia():
    e = dict(_energia)
    return {"a_carregar": e["ligado"], "sem_luz": e["ligado"] is False and e["desde"] is not None, "desde": e["desde"],
            "sem_internet": e["sem_internet_desde"] is not None, "sem_internet_desde": e["sem_internet_desde"], "historico": e["historico"][-5:]}


def vigiar(db, falar=None):
    """thread: a cada 30 s ve se o tablet continua a carregar e se ha internet. Escreve alertas e fala."""
    def alerta(texto, dizer=None):
        with db() as con:
            con.execute("INSERT INTO alertas (texto) VALUES (?)", (texto,))
        if falar and dizer:
            try: falar(dizer)
            except Exception: pass

    def ciclo():
        while True:
            try:
                b = _bateria()
                if b:
                    ligado = b.get("plugged", "UNPLUGGED") != "UNPLUGGED"
                    agora = datetime.now().strftime("%H:%M")
                    if _energia["ligado"] is True and not ligado:
                        _energia["desde"] = agora; _energia["t0"] = time.time()
                        alerta(f"Possível falha de luz às {agora}: o tablet deixou de carregar (bateria a {b.get('percentage')}%).",
                               "Atenção. Parece que faltou a luz. Estou a funcionar a bateria.")
                    elif _energia["ligado"] is False and ligado and _energia.get("t0"):
                        mins = round((time.time() - _energia["t0"]) / 60)
                        _energia["historico"].append(f"{_energia['desde']} a {agora} ({mins} min)")
                        alerta(f"A luz voltou às {agora}. Esteve {mins} minutos sem luz.", f"A luz voltou. Estivemos {mins} minutos sem luz.")
                        _energia["desde"] = None; _energia["t0"] = None
                    _energia["ligado"] = ligado
                net = _internet()
                if not net and _energia["sem_internet_desde"] is None:
                    _energia["sem_internet_desde"] = datetime.now().strftime("%H:%M")
                    alerta(f"A internet caiu às {_energia['sem_internet_desde']}.")
                elif net and _energia["sem_internet_desde"] is not None:
                    alerta(f"A internet voltou às {datetime.now().strftime('%H:%M')} (caiu às {_energia['sem_internet_desde']}).")
                    _energia["sem_internet_desde"] = None
            except Exception as e:
                print("avisos:", e)
            time.sleep(30)
    threading.Thread(target=ciclo, daemon=True).start()

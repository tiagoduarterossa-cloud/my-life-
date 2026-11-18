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
import urllib.error
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
    "VRL": ("Vila Real", 41.30, -7.74), "VIS": ("Viseu", 40.66, -7.91),
    # Madeira e Acores: o IPMA divide-os em zonas
    "MCN": ("Madeira, costa norte", 32.84, -16.95), "MCS": ("Madeira, costa sul", 32.65, -16.91),
    "MRM": ("Madeira, serras", 32.75, -16.96), "MPS": ("Porto Santo", 33.07, -16.34),
    "AOC": ("Açores, grupo ocidental", 39.45, -31.18), "ACE": ("Açores, grupo central", 38.62, -27.9),
    "AOR": ("Açores, grupo oriental", 37.6, -25.4),
}
ILHAS = {"MCN", "MCS", "MRM", "MPS", "AOC", "ACE", "AOR"}
NIVEIS = {"yellow": "amarelo", "orange": "laranja", "red": "vermelho"}
_cache, _lock = {}, threading.Lock()
# o fogos.pt passou a pedir uma chave pessoal (cabecalho FOGOS-PT-AUTH). Pede-se em fogos.pt/api e guarda-se assim:
#   echo A-CHAVE > ~/central/fogos_token.txt
FOGOS_TOKEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fogos_token.txt")


class SemChave(Exception):
    pass


def _json(url, validade=600):
    with _lock:
        c = _cache.get(url)
        if c and time.time() - c[0] < validade:
            return c[1]
    cab = {"User-Agent": "central-do-quarto/1.0 (painel pessoal, uso privado)"}
    if url.startswith(FOGOS) and os.path.exists(FOGOS_TOKEN):
        cab["FOGOS-PT-AUTH"] = open(FOGOS_TOKEN).read().strip()
    req = urllib.request.Request(url, headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read(10_000_000))
    except urllib.error.HTTPError as e:
        if url.startswith(FOGOS) and e.code in (401, 403):
            raise SemChave("o fogos.pt pede uma chave (vê o README)")
        raise
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


def avisos_distritos():
    """todos os distritos e zonas das ilhas com o pior aviso ativo do IPMA, separando terra e mar
    (a agitacao maritima so afeta a costa, por isso nao pinta o distrito todo)"""
    agora = datetime.now().isoformat()[:16]
    ordem = {"amarelo": 1, "laranja": 2, "vermelho": 3}
    por = {}
    for a in _json(IPMA):
        cod, nivel = a.get("idAreaAviso"), NIVEIS.get(a.get("awarenessLevelID"))
        if cod not in DISTRITOS or not nivel or (a.get("endTime") or "9999")[:16] < agora:
            continue
        tipo = a.get("awarenessTypeName", "Tempo")
        t = por.setdefault(cod, {})
        if ordem[nivel] > ordem.get(t.get(tipo), 0):
            t[tipo] = nivel
    out = []
    for c, (n, la, lo) in DISTRITOS.items():
        t = por.get(c, {})
        terra = [v for k, v in t.items() if "mar" not in k.lower()]
        mar = [v for k, v in t.items() if "mar" in k.lower()]
        pior = lambda xs: max(xs, key=lambda v: ordem[v]) if xs else None
        out.append({"cod": c, "nome": n, "lat": la, "lon": lo, "nivel": pior(terra), "mar": pior(mar),
                    "tipos": [f"{k.lower()} ({v})" for k, v in sorted(t.items(), key=lambda kv: -ordem[kv[1]])]})
    return out


def vento():
    """vento agora em cada distrito e zona das ilhas (Open-Meteo): de onde vem, velocidade e rajadas"""
    cods = list(DISTRITOS)
    lat = ",".join(str(DISTRITOS[c][1]) for c in cods); lon = ",".join(str(DISTRITOS[c][2]) for c in cods)
    r = _json(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
              "&current=wind_speed_10m,wind_direction_10m,wind_gusts_10m&wind_speed_unit=kmh", 1800)
    r = r if isinstance(r, list) else [r]
    return [{"cod": c, "lat": DISTRITOS[c][1], "lon": DISTRITOS[c][2], "de": x["current"]["wind_direction_10m"],
             "vel": round(x["current"]["wind_speed_10m"]), "rajada": round(x["current"]["wind_gusts_10m"])} for c, x in zip(cods, r)]


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

_energia = {"ligado": None, "desde": None, "sem_internet_desde": None, "historico": [], "bateria": None, "leituras": []}


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
    # quanto tempo de bateria falta: so se ja houver leituras suficientes durante o apagao (10 min e 2% gastos)
    horas = None
    lt = e["leituras"]
    if len(lt) >= 2 and lt[-1][0] - lt[0][0] >= 600 and lt[0][1] - lt[-1][1] >= 2:
        por_hora = (lt[0][1] - lt[-1][1]) / ((lt[-1][0] - lt[0][0]) / 3600)
        horas = round(lt[-1][1] / por_hora, 1)
    return {"a_carregar": e["ligado"], "sem_luz": e["ligado"] is False and e["desde"] is not None, "desde": e["desde"],
            "bateria": e["bateria"], "horas_bateria": horas,
            "sem_internet": e["sem_internet_desde"] is not None, "sem_internet_desde": e["sem_internet_desde"], "historico": e["historico"][-5:]}


def vigiar(db, falar=None, ao_mudar=None):
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
                    _energia["bateria"] = b.get("percentage")
                    if not ligado and _energia["desde"]:
                        _energia["leituras"] = (_energia["leituras"] + [(time.time(), b.get("percentage") or 0)])[-200:]
                    if _energia["ligado"] is True and not ligado:
                        _energia["desde"] = agora; _energia["t0"] = time.time()
                        _energia["leituras"] = [(time.time(), b.get("percentage") or 0)]
                        alerta(f"Possível falha de luz às {agora}: o tablet deixou de carregar (bateria a {b.get('percentage')}%).",
                               "Atenção. Parece que faltou a luz. Estou a funcionar a bateria. Vou passar ao modo apagão para poupar energia.")
                        if ao_mudar:
                            try: ao_mudar(True)
                            except Exception as e: print("apagao:", e)
                    elif _energia["ligado"] is False and ligado and _energia.get("t0"):
                        mins = round((time.time() - _energia["t0"]) / 60)
                        _energia["historico"].append(f"{_energia['desde']} a {agora} ({mins} min)")
                        alerta(f"A luz voltou às {agora}. Esteve {mins} minutos sem luz.", f"A luz voltou. Estivemos {mins} minutos sem luz.")
                        _energia["desde"] = None; _energia["t0"] = None; _energia["leituras"] = []
                        if ao_mudar:
                            try: ao_mudar(False)
                            except Exception as e: print("apagao:", e)
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

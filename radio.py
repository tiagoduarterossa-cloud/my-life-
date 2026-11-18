"""
Radio pela internet, para o modo apagao.

Os enderecos das radios mudam muitas vezes, por isso nao estao escritos aqui: vem do radio-browser.info,
um diretorio publico de radios que verifica todos os dias quais e que funcionam. Ficam guardados num ficheiro
(radio_cache.json) para nao ser preciso perguntar sempre.

Atencao: isto so funciona se houver internet. Num apagao a serio o router da casa tambem se desliga, por isso
so ha internet se ligares o tablet ao hotspot do telemovel (e as redes moveis tambem podem falhar, como no
apagao de abril de 2025). A unica coisa que funciona sempre e um radio a pilhas em FM.
"""

import json
import os
import time
import urllib.parse
import urllib.request

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "radio_cache.json")
API = os.environ.get("VIDA_RADIO", "https://de1.api.radio-browser.info")
# (nome a mostrar, nome a procurar no diretorio)
ESTACOES = [("Antena 1 (RTP)", "Antena 1"), ("TSF", "TSF"), ("Renascença", "Renascença"),
            ("Antena 1 Açores", "Antena 1 Açores"), ("Antena 1 Madeira", "Antena 1 Madeira")]


def _procurar(nome):
    q = urllib.parse.urlencode({"name": nome, "countrycode": "PT", "hidebroken": "true", "order": "clickcount",
                                "reverse": "true", "limit": 5})
    req = urllib.request.Request(f"{API}/json/stations/search?{q}", headers={"User-Agent": "central-do-quarto/1.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        lista = json.loads(r.read(2_000_000))
    # prefere MP3 ou AAC (tocam em qualquer browser) e que estejam a funcionar na ultima verificacao
    boas = [x for x in lista if x.get("lastcheckok") == 1 and (x.get("codec") or "").upper() in ("MP3", "AAC", "AAC+")]
    x = (boas or lista or [None])[0]
    if not x:
        return None
    return {"url": x.get("url_resolved") or x.get("url"), "codec": x.get("codec"), "kbps": x.get("bitrate"),
            "verificado": (x.get("lastcheckoktime_iso8601") or "")[:10]}


def estacoes():
    """[{nome, url, codec, kbps, verificado}] - do cache se tiver menos de 1 dia, senao pergunta outra vez"""
    try:
        c = json.load(open(CACHE))
        if time.time() - c["quando"] < 86400 and c["lista"]:
            return {"lista": c["lista"], "fonte": "radio-browser.info", "de_cache": False}
    except Exception:
        c = None
    lista = []
    for mostrar, procurar in ESTACOES:
        try:
            r = _procurar(procurar)
            if r and r["url"]:
                lista.append(dict(r, nome=mostrar))
        except Exception:
            pass
    if lista:
        json.dump({"quando": time.time(), "lista": lista}, open(CACHE, "w"))
        return {"lista": lista, "fonte": "radio-browser.info", "de_cache": False}
    if c and c.get("lista"):   # sem internet agora: devolve os ultimos que se conheciam
        return {"lista": c["lista"], "fonte": "radio-browser.info (guardado)", "de_cache": True}
    return {"lista": [], "fonte": "radio-browser.info", "erro": "sem internet para encontrar as rádios"}

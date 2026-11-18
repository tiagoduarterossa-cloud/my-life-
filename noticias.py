"""
Noticias para o Jarvis: le os "feeds" RSS dos sites (gratis, sem conta) e a lista oficial da CISA
de vulnerabilidades que estao a ser exploradas em ataques reais.

Para mudar os sites, edita FONTES. Se um site mudar o endereco do feed, so esse deixa de aparecer.
"""

import json
import os
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

FONTES = {
    "portugal": [("Observador", "https://observador.pt/feed/"), ("Público", "https://feeds.feedburner.com/PublicoRSS"),
                 ("RTP Notícias", "https://www.rtp.pt/noticias/rss")],
    "mundo": [("BBC Mundo (EN)", "https://feeds.bbci.co.uk/news/world/rss.xml"), ("Observador", "https://observador.pt/feed/")],
    "tecnologia": [("Pplware", "https://pplware.sapo.pt/feed/"), ("The Verge (EN)", "https://www.theverge.com/rss/index.xml")],
    "ciber": [("The Hacker News (EN)", "https://feeds.feedburner.com/TheHackersNews"),
              ("BleepingComputer (EN)", "https://www.bleepingcomputer.com/feed/"), ("Krebs on Security (EN)", "https://krebsonsecurity.com/feed/")],
    "f1": [("Motorsport.com F1 (EN)", "https://www.motorsport.com/rss/f1/news/"), ("Autosport F1 (EN)", "https://www.autosport.com/rss/f1/news/")],
}
NOMES = {"portugal": "Portugal", "mundo": "mundo", "tecnologia": "tecnologia", "ciber": "cibersegurança", "f1": "Fórmula 1"}
KEV = os.environ.get("VIDA_KEV", "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json")
_cache, _lock = {}, threading.Lock()
VALIDADE = 15 * 60


def _buscar(url, maximo=2_000_000):
    with _lock:
        c = _cache.get(url)
        if c and time.time() - c[0] < VALIDADE:
            return c[1]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (central do quarto)"})
    with urllib.request.urlopen(req, timeout=8) as r:
        dados = r.read(maximo)
    with _lock:
        _cache[url] = (time.time(), dados)
    return dados


def _texto(el, *nomes):
    for n in nomes:
        x = el.find(n)
        if x is not None:
            return (x.text or x.get("href") or "").strip()
    return ""


def _ler_feed(nome, url):
    """RSS 2.0 e Atom. Devolve [{titulo, fonte, link, quando}]"""
    raiz = ET.fromstring(_buscar(url))
    atom = "{http://www.w3.org/2005/Atom}"
    itens = raiz.findall(".//item") or raiz.findall(f".//{atom}entry")
    out = []
    for it in itens[:15]:
        titulo = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", _texto(it, "title", f"{atom}title"))).strip()
        if not titulo:
            continue
        data = _texto(it, "pubDate", f"{atom}updated", f"{atom}published")
        try:
            quando = parsedate_to_datetime(data).timestamp() if "," in data else time.mktime(time.strptime(data[:19], "%Y-%m-%dT%H:%M:%S"))
        except Exception:
            quando = 0
        link = _texto(it, "link")
        if not link:
            l = it.find(f"{atom}link")
            link = l.get("href", "") if l is not None else ""
        out.append({"titulo": titulo, "fonte": nome, "link": link, "quando": quando})
    return out


def obter(categoria="portugal", n=6):
    fontes = FONTES.get(categoria) or FONTES["portugal"]
    todas, falhas = [], []
    for nome, url in fontes:
        try:
            todas += _ler_feed(nome, url)
        except Exception:
            falhas.append(nome)
    vistos, out = set(), []
    for x in sorted(todas, key=lambda x: -x["quando"]):  # as mais recentes primeiro, sem repetidas
        k = x["titulo"].lower()[:60]
        if k not in vistos:
            vistos.add(k); out.append(x)
    return {"categoria": categoria, "nome": NOMES.get(categoria, categoria), "noticias": out[:n], "falhas": falhas}


def vulnerabilidades(n=5):
    """as falhas que a CISA confirma estarem a ser usadas em ataques, as mais recentes primeiro"""
    d = json.loads(_buscar(KEV, 20_000_000))
    v = sorted(d.get("vulnerabilities", []), key=lambda x: x.get("dateAdded", ""), reverse=True)
    from datetime import date, timedelta
    semana = (date.today() - timedelta(days=7)).isoformat()
    return {"total": len(v), "esta_semana": sum(1 for x in v if x.get("dateAdded", "") >= semana),
            "recentes": [{"cve": x.get("cveID"), "produto": f"{x.get('vendorProject', '')} {x.get('product', '')}".strip(),
                          "nome": x.get("vulnerabilityName", ""), "data": x.get("dateAdded", ""),
                          "ransomware": x.get("knownRansomwareCampaignUse") == "Known"} for x in v[:n]]}


def categoria_da_frase(s):
    """s ja sem acentos e em minusculas"""
    if re.search(r"ciber|hacker|hackers|ataque|ataques|seguranca informatica|virus|ransomware|malware", s): return "ciber"
    if re.search(r"\bf1\b|formula 1|formula um|corrida|gp\b|grande premio|verstappen|hamilton", s): return "f1"
    if re.search(r"tecnologia|tech|gadgets|telemovel|apple|samsung|informatica", s): return "tecnologia"
    if re.search(r"mundo|internacional|estrangeiro|global", s): return "mundo"
    return "portugal"

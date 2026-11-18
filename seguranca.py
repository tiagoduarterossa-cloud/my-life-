"""
Centro de seguranca da central.

1. Regista que aparelhos acedem a central (IP + tipo de aparelho) e avisa quando aparece um NOVO.
   Nao "ataca" nem varre a rede de ninguem: so olha para quem bate a porta da tua central.
2. Analisa um link e diz se tem sinais de phishing (sem o abrir).

(A verificacao de palavras-passe roubadas e feita no proprio browser: a palavra-passe nunca sai do aparelho.)
"""

import ipaddress
import re
import threading
import time
from urllib.parse import urlparse

TABELAS = """
CREATE TABLE IF NOT EXISTS aparelhos (
    ip TEXT PRIMARY KEY,
    tipo TEXT,
    nome TEXT,
    confiavel INTEGER NOT NULL DEFAULT 0,
    primeiro TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    ultimo TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    pedidos INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS alertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quando TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    texto TEXT NOT NULL,
    visto INTEGER NOT NULL DEFAULT 0
);
"""

_vistos = {}            # ip -> ultima vez que escrevemos na base de dados (para nao escrever a cada pedido)
_lock = threading.Lock()


def tipo_de_aparelho(ua):
    ua = ua or ""
    for k, v in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "PC Windows"),
                 ("Macintosh", "Mac"), ("Linux", "Linux"), ("curl", "programa (curl)"), ("python", "programa (Python)")):
        if k.lower() in ua.lower():
            return v
    return "desconhecido"


def registar(db, ip, ua):
    """chamado em cada pedido a central. So mexe na base de dados no maximo 1 vez por minuto por IP."""
    if not ip:
        return
    agora = time.time()
    with _lock:
        if agora - _vistos.get(ip, 0) < 60:
            return
        _vistos[ip] = agora
    tipo = tipo_de_aparelho(ua)
    with db() as con:
        r = con.execute("SELECT * FROM aparelhos WHERE ip = ?", (ip,)).fetchone()
        if r:
            con.execute("UPDATE aparelhos SET ultimo = datetime('now','localtime'), pedidos = pedidos + 1 WHERE ip = ?", (ip,))
            return
        # o proprio tablet (127.0.0.1) e de confianca
        local = ip in ("127.0.0.1", "::1")
        con.execute("INSERT INTO aparelhos (ip, tipo, confiavel, nome, pedidos) VALUES (?,?,?,?,1)",
                    (ip, tipo, 1 if local else 0, "Este tablet" if local else None))
        if not local:
            con.execute("INSERT INTO alertas (texto) VALUES (?)", (f"Novo aparelho acedeu à central: {tipo} ({ip}).",))


def resumo(con):
    aps = [dict(a) for a in con.execute("SELECT * FROM aparelhos ORDER BY confiavel, ultimo DESC")]
    alertas = [dict(a) for a in con.execute("SELECT * FROM alertas ORDER BY id DESC LIMIT 20")]
    return {"aparelhos": aps, "alertas": alertas, "por_ver": sum(1 for a in alertas if not a["visto"]),
            "desconhecidos": sum(1 for a in aps if not a["confiavel"])}


# ---------- analisar links (phishing) ----------

MARCAS = ["google", "apple", "icloud", "microsoft", "outlook", "instagram", "facebook", "whatsapp", "tiktok", "snapchat",
          "paypal", "amazon", "netflix", "spotify", "discord", "steam", "roblox", "epicgames", "fortnite", "playstation",
          "xbox", "cgd", "millennium", "novobanco", "santander", "mbway", "ctt", "portaldasfinancas", "segsocial", "shopify"]
ENCURTADORES = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd", "cutt.ly", "rb.gy", "shorturl.at", "ow.ly", "tiny.cc"}
TLD_SUSPEITOS = {"zip", "mov", "xyz", "top", "click", "country", "gq", "tk", "ml", "cf", "ga", "work", "rest", "cam", "lol"}


def _distancia(a, b):
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        ant, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            ant, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, ant + (ca != cb))
    return d[-1]


def analisar_link(link):
    """devolve {nivel: 'ok'|'cuidado'|'perigo', sinais: [...], dominio}. Nao abre o link."""
    link = (link or "").strip()
    if not re.match(r"^[a-z]+://", link, re.I):
        link = "http://" + link
    u = urlparse(link)
    host = (u.hostname or "").lower()
    sinais, pontos = [], 0
    if not host:
        return {"nivel": "perigo", "sinais": ["Isto não parece um link válido."], "dominio": ""}
    if u.scheme != "https":
        sinais.append("Não usa https (a ligação não é encriptada)."); pontos += 1
    try:
        ipaddress.ip_address(host)
        sinais.append("Usa um número (IP) em vez de um nome de site. Os sites a sério quase nunca fazem isto."); pontos += 3
    except ValueError:
        pass
    if "@" in (u.netloc or ""):
        sinais.append("Tem um '@' no endereço: o que vem antes engana, o site verdadeiro é o que vem depois."); pontos += 3
    if "xn--" in host:
        sinais.append("Usa letras de outros alfabetos disfarçadas (punycode). Pode imitar um site conhecido."); pontos += 4
    partes = host.split(".")
    base = ".".join(partes[-2:]) if len(partes) >= 2 else host
    if host in ENCURTADORES or base in ENCURTADORES:
        sinais.append("É um link encurtado: esconde para onde vai mesmo."); pontos += 1
    if partes[-1] in TLD_SUSPEITOS:
        sinais.append(f"Termina em .{partes[-1]}, muito usado em burlas."); pontos += 2
    if len(partes) > 4:
        sinais.append("Tem muitos subdomínios seguidos, um truque comum para parecer outro site."); pontos += 1
    if re.search(r"(login|verify|verificar|confirm|secure|seguranca|conta|account|update|premio|gratis|free|bonus|wallet|password)", host):
        sinais.append("O nome do site tem palavras como 'login', 'verificar' ou 'grátis', típicas de phishing."); pontos += 2
    nome = partes[-2] if len(partes) >= 2 else host
    for m in MARCAS:
        if m in host and nome != m and not host.endswith(f"{m}.com") and not host.endswith(f"{m}.pt"):
            sinais.append(f"Fala em '{m}' mas o site verdadeiro é '{base}'. Pode estar a fingir ser a {m}."); pontos += 3; break
        if nome != m and len(m) > 4 and _distancia(nome, m) == 1:
            sinais.append(f"'{nome}' é quase igual a '{m}', mas com uma letra diferente. É um truque clássico."); pontos += 4; break
    if len(link) > 120:
        sinais.append("O link é enorme, para esconder o que interessa."); pontos += 1
    # os sinais mais graves primeiro (os de https/encurtado sao os mais fracos)
    fracos = ("Não usa https", "link encurtado", "O link é enorme", "muitos subdomínios")
    sinais.sort(key=lambda x: any(f in x for f in fracos))
    nivel = "perigo" if pontos >= 4 else "cuidado" if pontos >= 1 else "ok"
    if not sinais:
        sinais.append("Não encontrei sinais típicos de phishing. Mesmo assim, se veio de alguém que não conheces, não metas dados.")
    return {"nivel": nivel, "sinais": sinais, "dominio": base}

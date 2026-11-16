"""
Spotify na central: tocar playlists, pausar, passar a proxima, volume e "o que esta a tocar".

Como funciona:
- Crias uma "app" em developer.spotify.com (gratis) e copias o Client ID para a central.
- Entras na tua conta Spotify UMA vez, no proprio tablet (http://127.0.0.1:8080). Usamos o metodo PKCE,
  que nao precisa de segredo nenhum. O Spotify da-nos um "token" que fica guardado em spotify_token.json
  (fora do GitHub) e e renovado sozinho.
- Para controlar a musica e preciso Spotify Premium (regra do Spotify) e o Spotify aberto num aparelho.
"""

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PASTA = Path(__file__).resolve().parent
TOKEN = PASTA / "spotify_token.json"
CONTAS = os.environ.get("SPOTIFY_CONTAS", "https://accounts.spotify.com")   # trocavel nos testes
API = os.environ.get("SPOTIFY_API", "https://api.spotify.com/v1")
REDIRECT = "http://127.0.0.1:8080/api/spotify/callback"
ESCOPOS = "user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-read-private"

_lock = threading.Lock()
_pendente = {}   # state -> code_verifier, enquanto entras na conta


class ErroSpotify(Exception):
    pass


# ---------- entrar na conta (PKCE) ----------

def link_entrar(client_id, redirect=REDIRECT):
    verifier = secrets.token_urlsafe(64)[:100]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    _pendente[state] = (verifier, client_id, redirect, time.time())
    q = urllib.parse.urlencode({"client_id": client_id, "response_type": "code", "redirect_uri": redirect,
                                "code_challenge_method": "S256", "code_challenge": challenge, "state": state, "scope": ESCOPOS})
    return f"{CONTAS}/authorize?{q}"


def _post_token(dados):
    req = urllib.request.Request(f"{CONTAS}/api/token", data=urllib.parse.urlencode(dados).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise ErroSpotify(f"o Spotify recusou ({e.code}): {e.read()[:200].decode('utf-8', 'ignore')}")
    except urllib.error.URLError:
        raise ErroSpotify("sem ligação ao Spotify")


def terminar_entrada(state, code):
    verifier, client_id, redirect, quando = _pendente.pop(state, (None, None, None, 0))
    if not verifier or time.time() - quando > 600:
        raise ErroSpotify("o pedido expirou: carrega outra vez em Ligar ao Spotify")
    t = _post_token({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect,
                     "client_id": client_id, "code_verifier": verifier})
    _guardar({"client_id": client_id, "access_token": t["access_token"], "refresh_token": t.get("refresh_token"),
              "expira": time.time() + int(t.get("expires_in", 3600)) - 60})


def _guardar(t):
    TOKEN.write_text(json.dumps(t))
    try:
        os.chmod(TOKEN, 0o600)
    except OSError:
        pass


def ligado():
    return TOKEN.exists()


def desligar():
    TOKEN.unlink(missing_ok=True)


def _token():
    with _lock:
        if not TOKEN.exists():
            raise ErroSpotify("ainda não ligaste o Spotify (roda dentada > Spotify)")
        t = json.loads(TOKEN.read_text())
        if time.time() > t.get("expira", 0) and t.get("refresh_token"):
            n = _post_token({"grant_type": "refresh_token", "refresh_token": t["refresh_token"], "client_id": t["client_id"]})
            t["access_token"] = n["access_token"]
            t["refresh_token"] = n.get("refresh_token", t["refresh_token"])
            t["expira"] = time.time() + int(n.get("expires_in", 3600)) - 60
            _guardar(t)
        return t["access_token"]


# ---------- pedidos a API ----------

def _api(metodo, caminho, corpo=None, query=None):
    url = f"{API}{caminho}" + ("?" + urllib.parse.urlencode(query) if query else "")
    dados = json.dumps(corpo).encode() if corpo is not None else (b"" if metodo in ("PUT", "POST") else None)
    req = urllib.request.Request(url, data=dados, method=metodo,
                                 headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            txt = r.read()
            return json.loads(txt) if txt else None
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "ignore")
        if e.code == 404 and ("NO_ACTIVE_DEVICE" in txt or "No active device" in txt):
            raise ErroSpotify("não há nenhum Spotify aberto. Abre o Spotify no tablet ou no telemóvel e tenta outra vez")
        if e.code == 403 and ("PREMIUM" in txt.upper() or "premium" in txt):
            raise ErroSpotify("para controlar a música o Spotify exige conta Premium")
        if e.code == 401:
            raise ErroSpotify("a ligação ao Spotify expirou: liga-o outra vez nas definições")
        if e.code == 429:
            raise ErroSpotify("demasiados pedidos ao Spotify, espera um bocadinho")
        raise ErroSpotify(f"o Spotify deu erro {e.code}")
    except urllib.error.URLError:
        raise ErroSpotify("sem ligação ao Spotify")


def _aparelho():
    """o aparelho onde tocar: o ativo; senao o primeiro (preferindo este tablet)"""
    ds = (_api("GET", "/me/player/devices") or {}).get("devices", [])
    if not ds:
        raise ErroSpotify("não há nenhum Spotify aberto. Abre o Spotify no tablet ou no telemóvel e tenta outra vez")
    ativo = next((d for d in ds if d.get("is_active")), None)
    return ativo or next((d for d in ds if d.get("type") == "Tablet"), ds[0])


def a_tocar():
    r = _api("GET", "/me/player")
    if not r or not r.get("item"):
        return {"tocar": False}
    it = r["item"]
    capa = (it.get("album", {}).get("images") or [{}])[-1].get("url") if it.get("album") else None
    return {"tocar": bool(r.get("is_playing")), "musica": it.get("name"),
            "artista": ", ".join(a["name"] for a in it.get("artists", [])), "capa": capa,
            "aparelho": (r.get("device") or {}).get("name"), "volume": (r.get("device") or {}).get("volume_percent")}


def tocar(pedido=""):
    """pedido vazio: continua. Senao procura nas tuas playlists e depois no Spotify todo."""
    d = _aparelho()
    if not pedido:
        _api("PUT", "/me/player/play", {}, {"device_id": d["id"]})
        return "A tocar."
    uri, nome = None, None
    minhas = (_api("GET", "/me/playlists", query={"limit": 50}) or {}).get("items", [])
    p = pedido.lower()
    for pl in minhas:
        if pl and p in (pl.get("name") or "").lower():
            uri, nome = pl["uri"], pl["name"]; break
    if not uri:
        res = _api("GET", "/search", query={"q": pedido, "type": "playlist,track,artist", "limit": 5}) or {}
        for tipo in ("playlists", "artists", "tracks"):
            itens = [x for x in (res.get(tipo) or {}).get("items", []) if x]
            if itens:
                uri, nome = itens[0]["uri"], itens[0]["name"]; break
    if not uri:
        raise ErroSpotify(f"não encontrei '{pedido}' no Spotify")
    corpo = {"uris": [uri]} if uri.startswith("spotify:track:") else {"context_uri": uri}
    _api("PUT", "/me/player/play", corpo, {"device_id": d["id"]})
    return f"A tocar {nome}."


def pausar():
    _api("PUT", "/me/player/pause")
    return "Música em pausa."


def seguinte():
    _api("POST", "/me/player/next")
    return "Próxima."


def anterior():
    _api("POST", "/me/player/previous")
    return "Anterior."


def volume(v):
    v = max(0, min(100, int(v)))
    _api("PUT", "/me/player/volume", query={"volume_percent": v})
    return f"Volume a {v}."

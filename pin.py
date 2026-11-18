"""
PIN da central.

- O PIN nunca fica guardado: so o hash PBKDF2-SHA256 com sal aleatorio (pin.json, fora do GitHub).
- Quem acerta no PIN recebe uma sessao (um token aleatorio num cookie HttpOnly). Na base de dados so fica
  o hash SHA-256 do token, por isso quem copiar o vida.db nao consegue entrar.
- No proprio tablet (127.0.0.1) o ecra normal nao pede PIN; o modo Iron Man pede, e tranca-se ao fim de
  15 minutos sem uso ou quando o Iron Man fecha.
- Noutro aparelho (telemovel, PC) pede-se o PIN para tudo. A sessao dura 30 dias.
- Chaves para aparelhos (atalho da Siri, sensores Shelly): um token comprido que se manda no cabecalho
  X-Chave ou em ?chave=. Nao expira, mas pode ser apagado.
- Contra adivinhar: 5 erros seguidos bloqueiam esse aparelho 5 minutos (e o dobro a cada novo erro);
  20 erros numa hora bloqueiam toda a gente 15 minutos. Cada bloqueio fica nos alertas de seguranca.
- Esqueceste o PIN? No Termux: rm ~/my-life-/pin.json (so quem tem o tablet na mao consegue).
"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

FICHEIRO = Path(os.environ.get("VIDA_PIN", Path(__file__).resolve().parent / "pin.json"))
ITERACOES = 200_000
DURACAO = {"browser": 30 * 86400, "local": 15 * 60, "chave": None}

TABELAS = """
CREATE TABLE IF NOT EXISTS pin_sessoes (
    token_hash TEXT PRIMARY KEY,
    tipo TEXT NOT NULL,                  -- browser, local, chave
    aparelho TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT '',
    criado REAL NOT NULL,
    ultimo REAL NOT NULL
);
"""

_lock = threading.Lock()
_falhas = {}            # ip -> [erros seguidos, bloqueado_ate]
_falhas_globais = []    # instantes dos erros na ultima hora
_global_ate = [0.0]


class ErroPin(Exception):
    pass


def ativo():
    return FICHEIRO.exists()


def _hash(pin, sal, it=ITERACOES):
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(sal), it).hex()


def _validar_formato(pin):
    pin = str(pin or "").strip()
    if not pin.isdigit() or not 4 <= len(pin) <= 8:
        raise ErroPin("o PIN tem de ter entre 4 e 8 números")
    if len(set(pin)) == 1 or pin in "0123456789" or pin in "9876543210":
        raise ErroPin("esse PIN é fácil demais (1111, 1234...). Escolhe outro.")
    return pin


def definir(con, novo, atual=None):
    novo = _validar_formato(novo)
    if ativo() and not confere(atual):
        raise ErroPin("o PIN atual está errado")
    sal = secrets.token_hex(16)
    FICHEIRO.write_text(json.dumps({"sal": sal, "hash": _hash(novo, sal), "iteracoes": ITERACOES}))
    try:
        os.chmod(FICHEIRO, 0o600)
    except OSError:
        pass
    # mudar o PIN fecha todas as sessoes de browser (as chaves dos aparelhos ficam)
    con.execute("DELETE FROM pin_sessoes WHERE tipo != 'chave'")


def remover(con, atual):
    if not confere(atual):
        raise ErroPin("PIN errado")
    FICHEIRO.unlink(missing_ok=True)
    con.execute("DELETE FROM pin_sessoes")


def confere(pin):
    if not ativo() or pin is None:
        return False
    d = json.loads(FICHEIRO.read_text())
    return hmac.compare_digest(_hash(str(pin).strip(), d["sal"], d.get("iteracoes", ITERACOES)), d["hash"])


def _bloqueio(ip):
    agora = time.time()
    if _global_ate[0] > agora:
        return _global_ate[0] - agora
    f = _falhas.get(ip)
    return f[1] - agora if f and f[1] > agora else 0


def entrar(con, pin, ip, aparelho, local, alerta=None):
    """devolve o token (para o cookie) ou levanta ErroPin"""
    with _lock:
        espera = _bloqueio(ip)
        if espera:
            raise ErroPin(f"demasiadas tentativas: espera {int(espera // 60) + 1} min")
        if confere(pin):
            _falhas.pop(ip, None)
            tok = secrets.token_urlsafe(32)
            agora = time.time()
            con.execute("INSERT INTO pin_sessoes (token_hash, tipo, aparelho, ip, criado, ultimo) VALUES (?,?,?,?,?,?)",
                        (_h(tok), "local" if local else "browser", aparelho[:80], ip, agora, agora))
            return tok
        agora = time.time()
        f = _falhas.setdefault(ip, [0, 0])
        f[0] += 1
        _falhas_globais[:] = [t for t in _falhas_globais if agora - t < 3600] + [agora]
        msg = None
        if f[0] >= 5:
            f[1] = agora + 300 * 2 ** (f[0] - 5)
            msg = f"PIN errado {f[0]} vezes seguidas no aparelho {ip}: bloqueado {int((f[1] - agora) // 60)} min."
        if len(_falhas_globais) >= 20:
            _global_ate[0] = agora + 900; _falhas_globais.clear()
            msg = "Mais de 20 PINs errados numa hora: a central bloqueou as entradas durante 15 minutos."
        if msg and alerta:
            try: alerta(msg)
            except Exception: pass
        raise ErroPin("PIN errado" + (f". {msg}" if msg else ""))


def _h(tok):
    return hashlib.sha256(tok.encode()).hexdigest()


def sessao(con, tok):
    """a sessao valida deste token (e atualiza o 'ultimo'), ou None"""
    if not tok or len(tok) > 200:
        return None
    r = con.execute("SELECT * FROM pin_sessoes WHERE token_hash = ?", (_h(tok),)).fetchone()
    if not r:
        return None
    dur, agora = DURACAO.get(r["tipo"]), time.time()
    if dur and agora - r["ultimo"] > dur:
        con.execute("DELETE FROM pin_sessoes WHERE token_hash = ?", (r["token_hash"],))
        return None
    if agora - r["ultimo"] > 30:   # nao escreve na base de dados a cada pedido
        con.execute("UPDATE pin_sessoes SET ultimo = ? WHERE token_hash = ?", (agora, r["token_hash"]))
    return dict(r)


def sair(con, tok):
    if tok:
        con.execute("DELETE FROM pin_sessoes WHERE token_hash = ?", (_h(tok),))


def criar_chave(con, nome):
    tok = "ch_" + secrets.token_urlsafe(24)
    agora = time.time()
    con.execute("INSERT INTO pin_sessoes (token_hash, tipo, aparelho, ip, criado, ultimo) VALUES (?,?,?,?,?,?)",
                (_h(tok), "chave", (nome or "aparelho")[:40], "", agora, agora))
    return tok


def listar(con):
    agora = time.time()
    out = []
    for r in con.execute("SELECT * FROM pin_sessoes ORDER BY ultimo DESC"):
        dur = DURACAO.get(r["tipo"])
        if dur and agora - r["ultimo"] > dur:
            continue
        out.append({"id": r["token_hash"][:12], "tipo": r["tipo"], "aparelho": r["aparelho"], "ip": r["ip"],
                    "criado": time.strftime("%d/%m %H:%M", time.localtime(r["criado"])),
                    "ultimo": time.strftime("%d/%m %H:%M", time.localtime(r["ultimo"]))})
    return out


def apagar(con, id_curto):
    if not id_curto or len(id_curto) != 12:
        raise ErroPin("sessão inválida")
    con.execute("DELETE FROM pin_sessoes WHERE substr(token_hash, 1, 12) = ?", (id_curto,))

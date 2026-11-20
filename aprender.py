"""
Aprendizagem do Jarvis, passo 1: registar onde ele falha.

- Cada pedido fica registado: a frase, o que as regras perceberam, quem respondeu (regras, rotina, Claude) e a resposta.
- "Nao percebi" = as regras nao perceberam (foi para o Claude, ou ficou sem resposta). E daqui que saem as frases a ensinar.
- Tu das nota: botoes 👍/👎 no chat, ou por voz ("nao era isso", "boa", "nao, eu queria era ...").
- Fica so no vida.db (no tablet), e apagado ao fim de 90 dias. No modo amigos nao se regista nada.
- O que pediste e pessoal: ver o registo pede o PIN (/api/aprender esta nos PRIVADOS).

Passo 2: das correcoes ("nao, eu queria era X") nasce uma proposta "esta frase = X". So passa a valer depois de a aprovares,
e so para essa frase exata (sem acentos nem maiusculas), por isso nao estraga as outras. Nao se aprova uma frase que
esteja nos testes (testes/frases.json) com outro significado, nem um X que as regras nao percebam.
"""

import json
import threading
from pathlib import Path

from datetime import datetime, timedelta

TABELAS = """
CREATE TABLE IF NOT EXISTS jarvis_registo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quando TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    frase TEXT NOT NULL,
    intencao TEXT,                 -- o que as regras perceberam ('ajuda' = nao perceberam)
    origem TEXT NOT NULL,          -- regras, rotina, claude, sem_resposta, bloqueado
    resposta TEXT,
    nota INTEGER,                  -- 1 = boa, -1 = errada
    correcao TEXT,                 -- "nao, eu queria era ..."
    privado INTEGER NOT NULL DEFAULT 0
);
"""
DIAS_GUARDAR = 90
TABELAS += """
CREATE TABLE IF NOT EXISTS jarvis_aprendido (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frase TEXT NOT NULL,           -- a frase como a disseste (sem acentos, minusculas)
    original TEXT NOT NULL,        -- como a disseste, para mostrar
    significa TEXT NOT NULL,       -- o que querias dizer (uma frase que as regras percebem)
    estado TEXT NOT NULL DEFAULT 'proposta',   -- proposta, aprovada, recusada
    criada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""
TESTES = Path(__file__).resolve().parent / "testes" / "frases.json"
_lock = threading.Lock()
_aprendido = {}            # frase simplificada -> o que significa (so as aprovadas)


def _chave(frase):
    import re
    import assistente
    frase = re.sub(r"^\s*(?:(?:ei|hey|ok|ola)\s+)?jarvis\b[\s,!.:-]*", "", frase.strip(), flags=re.I) or frase
    return " ".join(assistente.simples(frase).strip(" .!?,").split())


def carregar(db):
    """le as frases aprovadas para memoria (o assistente usa-as sem ir a base de dados)"""
    with db() as con:
        rs = con.execute("SELECT frase, significa FROM jarvis_aprendido WHERE estado = 'aprovada'").fetchall()
    with _lock:
        _aprendido.clear()
        _aprendido.update({r[0]: r[1] for r in rs})


def traduzir(frase):
    """se ja aprendeste o que esta frase quer dizer, devolve o significado; senao None"""
    with _lock:
        return _aprendido.get(_chave(frase))


def propor(con, original, significa):
    """cria uma proposta a partir de uma correcao. Devolve o id, ou None se nao fizer sentido."""
    import assistente
    k = _chave(original)
    if not k or k == _chave(significa) or assistente.entender(significa)[0] in ("ajuda", "correcao", "nota_mau", "nota_bom"):
        return None
    if con.execute("SELECT 1 FROM jarvis_aprendido WHERE frase = ? AND estado IN ('proposta', 'aprovada')", (k,)).fetchone():
        return None
    return con.execute("INSERT INTO jarvis_aprendido (frase, original, significa) VALUES (?,?,?)", (k, original[:200], significa[:200])).lastrowid


def decidir(con, pid, acao, db=None):
    """acao: aprovar, recusar ou esquecer (tirar uma aprovada). Devolve (ok, mensagem)."""
    import assistente
    r = con.execute("SELECT * FROM jarvis_aprendido WHERE id = ?", (pid,)).fetchone()
    if not r:
        return False, "não encontrei essa proposta"
    if acao == "aprovar":
        sig = assistente.entender(r["significa"])[0]
        if sig in ("ajuda", "correcao", "nota_mau", "nota_bom"):
            return False, "as minhas regras já não percebem o que querias dizer, por isso não aprendo isto"
        try:
            testes = json.loads(TESTES.read_text(encoding="utf-8"))["frases"]
        except Exception:
            testes = []
        for t in testes:
            if _chave(t["frase"]) == r["frase"] and t["intencao"] != sig:
                return False, f"essa frase está nos testes com outro significado ({t['intencao']}): não a mudo"
        con.execute("UPDATE jarvis_aprendido SET estado = 'aprovada' WHERE id = ?", (pid,))
    elif acao in ("recusar", "esquecer"):
        con.execute("UPDATE jarvis_aprendido SET estado = 'recusada' WHERE id = ?", (pid,))
    else:
        return False, "ação desconhecida"
    with _lock:
        if acao == "aprovar":
            _aprendido[r["frase"]] = r["significa"]
        else:
            _aprendido.pop(r["frase"], None)
    return True, "ok"


def propostas(con):
    return [dict(r) for r in con.execute("SELECT * FROM jarvis_aprendido WHERE estado = 'proposta' ORDER BY id DESC")]


def aprendidas(con):
    return [dict(r) for r in con.execute("SELECT * FROM jarvis_aprendido WHERE estado = 'aprovada' ORDER BY id DESC")]


def registar(con, frase, intencao, origem, resposta="", privado=False):
    con.execute("DELETE FROM jarvis_registo WHERE quando < ?", ((datetime.now() - timedelta(days=DIAS_GUARDAR)).strftime("%Y-%m-%d %H:%M:%S"),))
    cur = con.execute("INSERT INTO jarvis_registo (frase, intencao, origem, resposta, privado) VALUES (?,?,?,?,?)",
                      (frase[:500], intencao, origem, (resposta or "")[:300], 1 if privado else 0))
    return cur.lastrowid


def ultimo(con, minutos=10):
    """o ultimo pedido dos ultimos minutos (para "nao era isso" saber a que se refere)"""
    r = con.execute("SELECT * FROM jarvis_registo WHERE quando >= ? AND origem != 'nota' ORDER BY id DESC LIMIT 1",
                    ((datetime.now() - timedelta(minutes=minutos)).strftime("%Y-%m-%d %H:%M:%S"),)).fetchone()
    return dict(r) if r else None


def dar_nota(con, rid, nota, correcao=None):
    if nota not in (1, -1, 0):
        raise ValueError("a nota e 1, -1 ou 0")
    if correcao:   # "nao, eu queria era X": propoe aprender que aquela frase quer dizer X
        r = con.execute("SELECT frase FROM jarvis_registo WHERE id = ?", (rid,)).fetchone()
        if r:
            propor(con, r[0], correcao)
    n = con.execute("UPDATE jarvis_registo SET nota = ?, correcao = COALESCE(?, correcao) WHERE id = ?",
                    (nota or None, correcao, rid)).rowcount
    return n > 0


def resumo(con, dias=7):
    desde = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
    rs = [dict(r) for r in con.execute("SELECT * FROM jarvis_registo WHERE quando >= ? ORDER BY id DESC", (desde,))]
    total = len(rs)
    regras = sum(1 for r in rs if r["origem"] in ("regras", "rotina"))
    nao = {}
    for r in rs:
        if r["intencao"] == "ajuda" and r["origem"] in ("claude", "sem_resposta"):
            k = r["frase"].strip().lower()
            e = nao.setdefault(k, {"frase": r["frase"], "vezes": 0, "ultima": r["quando"], "origem": r["origem"]})
            e["vezes"] += 1
    return {
        "dias": dias, "total": total, "regras": regras, "claude": sum(1 for r in rs if r["origem"] == "claude"),
        "sem_resposta": sum(1 for r in rs if r["origem"] == "sem_resposta"),
        "bons": sum(1 for r in rs if r["nota"] == 1), "maus": sum(1 for r in rs if r["nota"] == -1),
        "nao_percebi": sorted(nao.values(), key=lambda e: (-e["vezes"], e["ultima"]))[:30],
        "propostas": propostas(con), "aprendidas": aprendidas(con),
        "errados": [{k: r[k] for k in ("id", "quando", "frase", "intencao", "origem", "resposta", "correcao")} for r in rs if r["nota"] == -1][:30],
    }


def frase(r):
    if not r["total"]:
        return "Ainda não tenho pedidos registados."
    pl = lambda n, um, varios: f"{n} {um if n == 1 else varios}"
    f = (f"Nos últimos {r['dias']} dias fizeste {pl(r['total'], 'pedido', 'pedidos')}. As minhas regras perceberam {r['regras']}"
         f" e {pl(r['claude'], 'foi para o Claude', 'foram para o Claude')}.")
    if r["nao_percebi"]:
        f += " As que as minhas regras não conhecem e apareceram mais: " + ", ".join(f"\"{e['frase']}\"" for e in r["nao_percebi"][:3]) + "."
    if r["maus"]:
        f += f" Marcaste {pl(r['maus'], 'resposta como errada', 'respostas como erradas')}."
    if r.get("propostas"):
        f += f" Tenho {pl(len(r['propostas']), 'coisa nova', 'coisas novas')} para aprender contigo: vê no Iron Man, Sistemas, Aprendizagem."
    if r.get("aprendidas"):
        f += f" Já aprendi {pl(len(r['aprendidas']), 'frase tua', 'frases tuas')}."
    return f


def apagar_tudo(con):
    con.execute("DELETE FROM jarvis_registo")

"""
Aprendizagem do Jarvis, passo 1: registar onde ele falha.

- Cada pedido fica registado: a frase, o que as regras perceberam, quem respondeu (regras, rotina, Claude) e a resposta.
- "Nao percebi" = as regras nao perceberam (foi para o Claude, ou ficou sem resposta). E daqui que saem as frases a ensinar.
- Tu das nota: botoes 👍/👎 no chat, ou por voz ("nao era isso", "boa", "nao, eu queria era ...").
- Fica so no vida.db (no tablet), e apagado ao fim de 90 dias. No modo amigos nao se regista nada.
- O que pediste e pessoal: ver o registo pede o PIN (/api/aprender esta nos PRIVADOS).

Passo 2 (ainda nao feito): a noite, propor regras novas a partir disto; tu aprovas de manha e os testes confirmam.
"""

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
    return f


def apagar_tudo(con):
    con.execute("DELETE FROM jarvis_registo")

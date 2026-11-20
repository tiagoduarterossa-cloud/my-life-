"""
Modos do Jarvis (alem do Iron Man): estudo, revisao, amigos e treino.

- Estudo: e a rotina "Modo estudo" (cronometro, nao incomodar...), com um ecra proprio. No fim regista no diario.
- Revisao: o Claude faz perguntas de escolha multipla sobre a materia que tens registada para um teste
  (no teste e no diario de estudo). As perguntas sao geradas por IA: podem ter erros, e o ecra diz isso.
- Amigos: esconde o que e pessoal. Enquanto esta ligado, a central nao responde a perguntas sobre a tua vida
  (agenda, testes, tarefas, notas, alarmes...) nem por regras nem pelo Claude. Para sair, se houver PIN, pede o PIN.
- Treino: temporizador de intervalos falado. No fim regista o tempo na area desporto.
"""

import re
import threading
from datetime import date, timedelta

import assistente

_lock = threading.Lock()
_estado = {"amigos": False}
_db = None                 # o servidor liga aqui a base de dados (modos.ligar(db))


def ligar(db):
    """guarda a ligacao e volta a ler o modo amigos (se o servidor reiniciar a meio, continua ligado)"""
    global _db
    _db = db
    try:
        with db() as con:
            r = con.execute("SELECT valor FROM config WHERE chave = 'modo_amigos'").fetchone()
        _estado["amigos"] = bool(r and r[0] == "1")
    except Exception as e:
        print("modos:", e)

# o que fica escondido no modo amigos (alem do que ja e privado com PIN)
PESSOAIS = {"hoje", "dia", "testes", "novo_teste", "tarefa", "evento", "nota", "ver_notas", "alarme", "alarme_sem",
            "alarme_ver", "acordaste", "mala", "custo_ia", "backup", "modo_revisao", "sugestoes", "aprender_ver", "memoria_add", "memoria_ver", "memoria_apagar", "plano_estudo"} | set(assistente.PRIVADAS)
FRASE_AMIGOS = "Estou em modo amigos: as tuas coisas ficam para depois."


def amigos():
    with _lock:
        return _estado["amigos"]


def por_amigos(ligado):
    with _lock:
        _estado["amigos"] = bool(ligado)
    if _db:
        try:
            with _db() as con:
                con.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('modo_amigos', ?)", ("1" if ligado else "0",))
        except Exception as e:
            print("modos:", e)


def bloqueado(frase):
    """True se a frase pede algo pessoal e o modo amigos esta ligado"""
    return amigos() and assistente.entender(frase)[0] in PESSOAIS


# ---------- revisao ----------

def disciplinas(con):
    nomes = {r[0] for r in con.execute("SELECT disciplina FROM testes")} | {r[0] for r in con.execute("SELECT disciplina FROM diario")}
    return sorted(n for n in nomes if n)


def achar_disciplina(con, texto):
    """a disciplina que aparece na frase (pelos nomes que ja usaste), ou None"""
    s = assistente.simples(texto)
    for n in sorted(disciplinas(con), key=len, reverse=True):
        if re.search(r"\b" + re.escape(assistente.simples(n)) + r"\b", s):
            return n
    return None


def contexto(con, disciplina, materia="", hoje=None):
    """o que a central sabe da materia: o proximo teste e o que estudaste nos ultimos 60 dias. Devolve (texto, teste)"""
    hoje = hoje or date.today()
    d = assistente.simples(disciplina)
    teste = next((dict(t) for t in con.execute("SELECT * FROM testes WHERE data >= ? ORDER BY data", (hoje.isoformat(),))
                  if assistente.simples(t["disciplina"]) == d), None)
    partes = []
    if materia:
        partes.append(f"Matéria pedida agora: {materia}")
    if teste and teste.get("materia"):
        partes.append(f"Matéria do teste de {teste['data']}: {teste['materia']}")
    for r in con.execute("SELECT * FROM diario WHERE data >= ? ORDER BY data DESC LIMIT 15", ((hoje - timedelta(days=60)).isoformat(),)):
        if assistente.simples(r["disciplina"]) == d:
            partes.append(f"Estudou ({r['data']}): {r['materia']}" + (f" | dúvidas: {r['duvidas']}" if r["duvidas"] else ""))
    return "\n".join(partes), teste

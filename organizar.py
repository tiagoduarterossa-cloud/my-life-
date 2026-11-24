"""
"Jarvis, organiza o meu dia": propoe blocos de tempo para o resto de hoje e SO os poe na agenda se disseres que sim.

- Usa o que ja la esta: aulas do horario e eventos ficam fixos; os blocos vao para os buracos livres,
  de agora (arredondado a meia hora seguinte) ate as 21h30, com 10 minutos de pausa entre blocos.
- O que entra, por ordem: estudar para testes em 1 a 3 dias (45 min, se hoje ainda nao houver estudo dessa
  disciplina na agenda), tarefas atrasadas, tarefas para hoje e para amanha (30 min cada, ate 4 tarefas)
  e, se sobrar 1 hora, um bloco livre para os projetos.
- E uma PROPOSTA: fica guardada 15 minutos. "Sim" / "poe na agenda" cria os eventos; "nao" descarta.
  "Desfaz o plano do dia" apaga os eventos que esta proposta criou (so os de hoje).
- Nada e inventado: os titulos vem dos teus testes e tarefas.
"""

import json
import re
import time
from datetime import date, datetime, timedelta

import assistente
from briefing import _curto
from assistente import hora_falada, lista_falada

FIM = 21 * 60 + 30
PAUSA = 10
VALIDADE = 15 * 60
SIM = re.compile(r"^(sim|s|pode ser|bora|ok|okay|confirma|confirmo|aceito|esta bem|ta bem|perfeito|poe|poe na agenda|mete na agenda|poe isso na agenda|sim poe|sim por favor|faz isso)$")
NAO = re.compile(r"^(nao|nao obrigado|deixa|deixa estar|esquece|cancela|nao quero)$")


def pedido(s):
    return bool(re.search(r"\b(organiza|organizar|planeia|planear|arruma)(-me| me)? (o meu dia|o dia|a minha agenda|o meu calendario|o resto do dia|a minha tarde|a tarde|hoje)\b", s)
                or re.search(r"\b(faz-me|faz me|faz) (um )?plano (para|do) (hoje|dia|resto do dia)\b", s))


def desfazer_pedido(s):
    return bool(re.search(r"\b(desfaz|desfazer|apaga|anula|tira)\b.*\b(plano do dia|organizacao do dia|dia organizado|o que organizaste)\b", s))


def _m(h):
    return int(h[:2]) * 60 + int(h[3:5])


def _h(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def _ocupado(con, hoje):
    """intervalos [ini, fim) em minutos: aulas e eventos (um evento sem fim conta como 1 hora)"""
    occ = [(_m(r["inicio"]), _m(r["fim"])) for r in con.execute("SELECT inicio, fim FROM horario WHERE dia = ?", (hoje.weekday(),))]
    occ += [(_m(r["hora"]), _m(r["hora"]) + 60) for r in con.execute(
        "SELECT hora FROM eventos WHERE data = ? AND hora IS NOT NULL AND hora != ''", (hoje.isoformat(),))]
    return sorted(occ)


def _blocos_desejados(con, hoje):
    iso = hoje.isoformat()
    eventos_hoje = " ".join(r["titulo"].lower() for r in con.execute("SELECT titulo FROM eventos WHERE data = ?", (iso,)))
    out = []
    for t in con.execute("SELECT * FROM testes WHERE data > ? AND data <= ? ORDER BY data", (iso, (hoje + timedelta(days=3)).isoformat())):
        if t["disciplina"].lower() not in eventos_hoje:
            out.append((f"Estudar {t['disciplina']}", 45, f"estudar {_curto(t['disciplina'])}"))
    tar = con.execute("SELECT * FROM tarefas WHERE feita = 0 AND prazo IS NOT NULL AND prazo <= ? ORDER BY prazo, prioridade",
                      ((hoje + timedelta(days=1)).isoformat(),)).fetchall()
    for t in tar[:4]:
        out.append((t["titulo"], 30, t["titulo"].lower()))
    return out


def propor(con, agora=None):
    agora = agora or datetime.now()
    hoje = agora.date()
    inicio = ((agora.hour * 60 + agora.minute) // 30 + 1) * 30
    occ = _ocupado(con, hoje)
    desejados = _blocos_desejados(con, hoje)
    blocos, m = [], inicio

    def encaixar(dur):
        nonlocal m
        x = m
        while x + dur <= FIM:
            choca = next((b for a, b in occ if x < b and a < x + dur), None)
            if choca is None:
                return x
            x = ((choca + 9) // 10) * 10          # depois do que esta marcado
        return None

    for titulo, dur, falado in desejados:
        x = encaixar(dur)
        if x is None:
            break
        blocos.append({"hora": _h(x), "fim": _h(x + dur), "titulo": titulo, "falado": falado})
        m = x + dur + PAUSA
    if desejados or blocos:
        x = encaixar(60)
        if x is not None and len(blocos) < 6:
            blocos.append({"hora": _h(x), "fim": _h(x + 60), "titulo": "Bloco livre: projetos", "falado": "um bloco livre para os teus projetos"})
    if not blocos:
        f = ("Não tens testes nem prazos para hoje e amanhã. O resto do dia é teu." if not desejados
             else "Não há tempo livre suficiente até às 21 e meia para encaixar mais nada hoje.")
        return {"resposta": f, "falado": f}
    con.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('proposta_dia', ?)",
                (json.dumps({"quando": time.time(), "dia": hoje.isoformat(), "blocos": blocos}),))
    linhas = [f"{b['hora']}–{b['fim']} · {b['titulo']}" for b in blocos]
    falado = "Proponho isto: " + lista_falada(f"às {hora_falada(b['hora'])}, {b['falado']}" for b in blocos[:4]) + \
             (f", e mais {len(blocos) - 4}" if len(blocos) > 4 else "") + ". Ponho na agenda?"
    return {"resposta": "Proposta para o resto de hoje (diz sim para pôr na agenda):", "itens": linhas, "falado": falado,
            "briefing": [{"aba": "Plano", "titulo": "Proposta para hoje · diz sim", "linhas": linhas, "falado": falado}]}


def _pendente(con):
    r = con.execute("SELECT valor FROM config WHERE chave = 'proposta_dia'").fetchone()
    if not r:
        return None
    p = json.loads(r[0])
    if time.time() - p["quando"] > VALIDADE or p["dia"] != date.today().isoformat():
        return None
    return p


def responder_proposta(con, frase):
    """se houver uma proposta a espera e a frase for sim/nao, trata dela; senao devolve None"""
    s = assistente.simples(re.sub(r"^\s*jarvis\b[\s,!.:-]*", "", frase.strip(), flags=re.I)).strip(" .!?,")
    if not (SIM.match(s) or NAO.match(s)):
        return None
    p = _pendente(con)
    if not p:
        return None
    con.execute("DELETE FROM config WHERE chave = 'proposta_dia'")
    if NAO.match(s):
        return {"resposta": "Está bem, não mexi na agenda.", "falado": "Está bem, não mexi na agenda."}
    ids = [con.execute("INSERT INTO eventos (titulo, data, hora) VALUES (?,?,?)", (b["titulo"][:120], p["dia"], b["hora"])).lastrowid
           for b in p["blocos"]]
    con.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('dia_organizado', ?)", (json.dumps({"dia": p["dia"], "ids": ids}),))
    f = f"Feito. Pus {len(ids)} bloco{'s' if len(ids) > 1 else ''} na agenda de hoje." + \
        " Se mudares de ideias, diz: desfaz o plano do dia."
    return {"resposta": f, "falado": f, "mudou": True}


def desfazer(con):
    r = con.execute("SELECT valor FROM config WHERE chave = 'dia_organizado'").fetchone()
    d = json.loads(r[0]) if r else None
    if not d or d["dia"] != date.today().isoformat():
        return {"resposta": "Hoje não organizei nada na tua agenda.", "falado": "Hoje não organizei nada na tua agenda."}
    for i in d["ids"]:
        con.execute("DELETE FROM eventos WHERE id = ?", (i,))
    con.execute("DELETE FROM config WHERE chave = 'dia_organizado'")
    return {"resposta": "Tirei os blocos que tinha posto na agenda.", "falado": "Tirei os blocos que tinha posto na agenda.", "mudou": True}

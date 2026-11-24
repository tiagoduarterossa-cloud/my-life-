"""
O briefing da manha: "Jarvis, bom dia" (ou "briefing", "resumo do dia").

Monta uma sequencia de cartoes, cada um com o que aparece no ecra e o que o Jarvis diz:
  agenda (aulas, eventos e testes de hoje), escola (trabalhos novos desde ontem e testes da semana),
  tempo (Open-Meteo, so com a cidade escolhida), noticias (titulos dos feeds, com a fonte)
  e prioridades (as 3 coisas mais urgentes, por regras fixas: nada inventado).
Um cartao sem dados nao aparece. No modo amigos so ha tempo e noticias.
Nao usa o Claude (custo zero). O tempo e as noticias vem em paralelo, com limite de tempo.
"""

import re
import threading
from datetime import date, datetime, timedelta

import assistente
from assistente import CURTOS, dia_falado, fmt_data, hora_falada, lista_falada

FRASES = ("briefing", "resumo do dia", "resumo da manha", "ponto da situacao", "ponto de situacao")


def pedido(frase):
    """'bom dia' sozinho (com ou sem o nome) ou um dos pedidos de briefing"""
    t = re.sub(r"^\s*(?:(?:ei|hey|ok|ola)\s+)?jarvis\b[\s,!.:-]*", "", frase.strip(), flags=re.I)
    s = assistente.simples(t).strip(" !.?")
    s = re.sub(r"[\s,!.]+jarvis$", "", s).strip(" ,!.?")
    return s == "bom dia" or any(f in s for f in FRASES)


def _curto(d):
    """o nome curto para dizer em voz alta ("Ciências"), mas nunca abreviaturas ("Mat")"""
    c = CURTOS.get(d, d)
    return d if len(c) <= 4 else c


def _agenda(con, hoje):
    iso, linhas, fala = hoje.isoformat(), [], []
    aulas = con.execute("SELECT * FROM horario WHERE dia = ? ORDER BY inicio", (hoje.weekday(),)).fetchall()
    escola = [a for a in aulas if a["area"] == "escola"]
    if escola:
        linhas.append(f"{escola[0]['inicio']}–{escola[-1]['fim']} · Aulas: " + ", ".join(dict.fromkeys(a["titulo"] for a in escola)))
        fala.append(f"Tens aulas das {hora_falada(escola[0]['inicio'])} às {hora_falada(escola[-1]['fim'])}.")
    outros = [a for a in aulas if a["area"] != "escola"]
    for a in outros:
        linhas.append(f"{a['inicio']} · {a['titulo']}")
    evs = con.execute("SELECT * FROM eventos WHERE data = ? ORDER BY hora", (iso,)).fetchall()
    for e in evs:
        linhas.append(f"{e['hora'] or 'Dia todo'} · {e['titulo']}")
    marcados = [f"{a['titulo'].lower()} às {hora_falada(a['inicio'])}" for a in outros] + \
               [e["titulo"] + (f" às {hora_falada(e['hora'])}" if e["hora"] else "") for e in evs]
    if marcados:
        fala.append(("Tens também " if escola else "Tens ") + lista_falada(marcados) + ".")
    ts = con.execute("SELECT * FROM testes WHERE data = ?", (iso,)).fetchall()
    for t in ts:
        linhas.insert(0, f"TESTE · {t['disciplina']}" + (f" ({t['materia']})" if t["materia"] else ""))
    if ts:
        fala.insert(0, f"Hoje tens teste de {lista_falada(_curto(t['disciplina']) for t in ts)}. Força nisso.")
    if not linhas:
        return {"aba": "Agenda", "titulo": "Agenda de hoje", "linhas": ["Nada marcado"], "falado": "Hoje não tens nada marcado."}
    return {"aba": "Agenda", "titulo": "Agenda de hoje", "linhas": linhas, "falado": " ".join(fala)}


def _escola(con, hoje):
    linhas, fala = [], []
    ontem = (hoje - timedelta(days=1)).isoformat()
    novas = con.execute("SELECT * FROM tarefas WHERE feita = 0 AND area = 'escola' AND criada >= ? ORDER BY id", (ontem,)).fetchall()
    for t in novas:
        linhas.append("Novo: " + t["titulo"] + (f" · até {date.fromisoformat(t['prazo']).strftime('%d/%m')}" if t["prazo"] else ""))
    if novas:
        fala.append(("Desde ontem entrou um trabalho novo: " if len(novas) == 1 else f"Desde ontem entraram {len(novas)} trabalhos novos: ")
                    + lista_falada(t["titulo"] for t in novas[:3]) + ".")
    prox = con.execute("SELECT * FROM testes WHERE data > ? AND data <= ? ORDER BY data",
                       (hoje.isoformat(), (hoje + timedelta(days=7)).isoformat())).fetchall()
    for t in prox:
        linhas.append(f"Teste de {t['disciplina']} · {fmt_data(date.fromisoformat(t['data']), hoje)}")
    if prox:
        fala.append("Esta semana tens teste de " + lista_falada(
            f"{_curto(t['disciplina'])} {dia_falado(date.fromisoformat(t['data']), hoje)}" for t in prox[:3]) + ".")
    if not linhas:
        return None
    return {"aba": "Escola", "titulo": "Escola · desde ontem", "linhas": linhas, "falado": " ".join(fala)}


def _prioridades(con, hoje):
    """as 3 mais urgentes, por pontos fixos: teste hoje > atrasadas > teste em 1-3 dias > prazo hoje > prazo amanha > alta prioridade"""
    cands = []
    iso = hoje.isoformat()
    for t in con.execute("SELECT * FROM testes WHERE data >= ? AND data <= ?", (iso, (hoje + timedelta(days=3)).isoformat())):
        dias = (date.fromisoformat(t["data"]) - hoje).days
        if dias == 0:
            cands.append((100, f"Teste de {t['disciplina']} hoje", f"o teste de {_curto(t['disciplina'])}"))
        else:
            cands.append((80 - dias, f"Estudar {t['disciplina']} (teste {dia_falado(date.fromisoformat(t['data']), hoje)})",
                          f"estudar {_curto(t['disciplina'])}"))
    for t in con.execute("SELECT * FROM tarefas WHERE feita = 0"):
        p = t["prazo"]
        if p and p < iso:
            cands.append((90 - t["prioridade"], f"{t['titulo']} (atrasada)", f"{t['titulo'].lower()}, que está atrasada"))
        elif p == iso:
            cands.append((70 - t["prioridade"], f"{t['titulo']} (hoje)", t["titulo"].lower()))
        elif p == (hoje + timedelta(days=1)).isoformat():
            cands.append((60 - t["prioridade"], f"{t['titulo']} (amanhã)", t["titulo"].lower()))
        elif t["prioridade"] == 1:
            cands.append((40, t["titulo"], t["titulo"].lower()))
    cands.sort(key=lambda c: -c[0])
    top = cands[:3]
    if not top:
        return None
    return {"aba": "Prioridades", "titulo": "As 3 prioridades de hoje", "linhas": [f"{i}. {c[1]}" for i, c in enumerate(top, 1)],
            "falado": ("A prioridade de hoje é " if len(top) == 1 else "As prioridades de hoje são: ") + lista_falada(c[2] for c in top) + "."}


def _tempo(cfg):
    if not cfg.get("lat"):
        return None
    m = assistente._json(f"https://api.open-meteo.com/v1/forecast?latitude={cfg['lat']}&longitude={cfg['lon']}"
                         "&current=temperature_2m&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
                         "&timezone=auto&forecast_days=1")
    agora = round(m["current"]["temperature_2m"])
    mx, mn = round(m["daily"]["temperature_2m_max"][0]), round(m["daily"]["temperature_2m_min"][0])
    chuva = m["daily"]["precipitation_probability_max"][0] or 0
    cidade = (cfg.get("cidade") or "").split(",")[0]
    return {"aba": "Tempo", "titulo": f"Tempo · {cidade}" if cidade else "Tempo",
            "tempo": {"agora": agora, "max": mx, "min": mn, "chuva": chuva},
            "linhas": [f"Agora {agora}° · mínima {mn}° · máxima {mx}°", f"Chuva: {chuva}%", "Fonte: Open-Meteo"],
            "falado": f"Lá fora estão {agora} graus, a máxima é de {mx} e a mínima de {mn}, com {chuva} por cento de probabilidade de chuva."
                      + (" Leva casaco." if chuva >= 50 else "")}


def _noticias():
    import noticias
    r = noticias.obter("portugal", 3)
    ns = r.get("noticias") or []
    if not ns:
        return None
    return {"aba": "Notícias", "titulo": "Notícias", "linhas": [f"{n['titulo']} ({n['fonte']})" for n in ns],
            "falado": "Nas notícias: " + " ".join(n["titulo"].rstrip(".") + "." for n in ns[:2])}


def _em_paralelo(fns, limite=7):
    """corre as funcoes de rede ao mesmo tempo; o que nao chegar a tempo (ou falhar) fica de fora"""
    res = [None] * len(fns)

    def correr(i, f):
        try:
            res[i] = f()
        except Exception as e:
            print("briefing:", e)
    ts = [threading.Thread(target=correr, args=(i, f), daemon=True) for i, f in enumerate(fns)]
    for t in ts:
        t.start()
    fim = datetime.now().timestamp() + limite
    for t in ts:
        t.join(max(0, fim - datetime.now().timestamp()))
    return res


def rede(cfg):
    """a parte que precisa de internet (tempo e noticias), feita antes de abrir a base de dados"""
    return _em_paralelo([lambda: _tempo(cfg), _noticias])


def montar(con, cfg, amigos=False, hoje=None, da_rede=None):
    hoje = hoje or date.today()
    nome = (cfg.get("nome") or "").strip()
    tempo, nots = da_rede if da_rede is not None else rede(cfg)
    if amigos:
        cartoes = [tempo, nots]
    else:
        cartoes = [_agenda(con, hoje), _escola(con, hoje), tempo, nots, _prioridades(con, hoje)]
    cartoes = [c for c in cartoes if c]
    h = datetime.now().hour
    ola = "Bom dia" if 5 <= h < 13 else "Boa tarde" if 13 <= h < 20 else "Boa noite"
    abertura = f"{ola}{', ' + nome if nome and not amigos else ''}. São {hora_falada(datetime.now().strftime('%H:%M'))}."
    if cartoes:
        cartoes[0] = dict(cartoes[0], falado=abertura + " " + cartoes[0]["falado"])
    resumo = " · ".join(c["aba"] for c in cartoes)
    return {"resposta": f"{ola}! Briefing: {resumo}." if cartoes else f"{ola}!",
            "itens": [l for c in cartoes for l in [f"— {c['titulo']}"] + c["linhas"]],
            "falado": " ".join(c["falado"] for c in cartoes) or abertura,
            "briefing": cartoes}

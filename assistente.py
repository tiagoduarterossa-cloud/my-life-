"""
O assistente da central: percebe frases em portugues e faz coisas com os teus dados.

Funciona so com regras (sem IA paga, sem internet, exceto a previsao do tempo para a mala).
Esta dividido em duas partes, de proposito:

  entender(texto)  ->  (intencao, dados)     "o que e que ele quer?"
  responder(...)   ->  resposta              "fazer e responder"

Se um dia treinares um modelo teu (ou ligares o Claude), so tens de trocar a funcao entender().
"""

import json
import math
import re
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, timedelta

DIAS_SEMANA = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
NOMES_DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]


def simples(t):
    """minusculas e sem acentos, para comparar palavras"""
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# ---------- datas e horas ----------

def proximo_dia_semana(hoje, i, incluir_hoje=False):
    dif = (i - hoje.weekday()) % 7
    if dif == 0 and not incluir_hoje:
        dif = 7
    return hoje + timedelta(days=dif)


def achar_datas(t, hoje):
    """devolve a lista de datas mencionadas, pela ordem em que aparecem"""
    s = simples(t)
    achados = []  # (posicao, data)
    for m in re.finditer(r"\bdepois de amanha\b", s):
        achados.append((m.start(), hoje + timedelta(days=2)))
    s2 = s.replace("depois de amanha", "#" * len("depois de amanha"))
    for m in re.finditer(r"\bhoje\b", s2):
        achados.append((m.start(), hoje))
    for m in re.finditer(r"\bamanha\b", s2):
        achados.append((m.start(), hoje + timedelta(days=1)))
    for i, d in enumerate(DIAS_SEMANA):
        for m in re.finditer(rf"\b{d}(?:-feira| feira)?\b", s2):
            achados.append((m.start(), proximo_dia_semana(hoje, i)))
    # 20/11 ou 20-11
    for m in re.finditer(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", s2):
        try:
            ano = int(m[3]) if m[3] else hoje.year
            if ano < 100: ano += 2000
            d = date(ano, int(m[2]), int(m[1]))
            if not m[3] and d < hoje: d = d.replace(year=d.year + 1)
            achados.append((m.start(), d))
        except ValueError:
            pass
    # "dia 20", "dia 20 de dezembro", "20 de dezembro"
    for m in re.finditer(r"\b(?:dia )?(\d{1,2}) de (" + "|".join(MESES) + r")\b", s2):
        try:
            d = date(hoje.year, MESES.index(m[2]) + 1, int(m[1]))
            if d < hoje: d = d.replace(year=d.year + 1)
            achados.append((m.start(), d))
        except ValueError:
            pass
    for m in re.finditer(r"\bdia (\d{1,2})\b(?! de)(?! (?:a|e|ate) \d)", s2):
        try:
            d = hoje.replace(day=int(m[1]))
            if d < hoje:
                d = (d.replace(day=1) + timedelta(days=32)).replace(day=int(m[1]))
            achados.append((m.start(), d))
        except ValueError:
            pass
    # "de 20 a 22" ou "dia 20 a 23"
    m = re.search(r"\b(?:de|dia|dias|entre) (\d{1,2}) (?:a|e|ate) (\d{1,2})\b", s2)
    if m:
        try:
            a = hoje.replace(day=int(m[1]))
            if a < hoje: a = (a.replace(day=1) + timedelta(days=32)).replace(day=int(m[1]))
            b = a.replace(day=int(m[2])) if int(m[2]) >= int(m[1]) else (a.replace(day=1) + timedelta(days=32)).replace(day=int(m[2]))
            achados += [(m.start(), a), (m.start() + 1, b)]
        except ValueError:
            pass
    vistos, res = set(), []
    for _, d in sorted(achados, key=lambda x: x[0]):
        if d not in vistos:
            vistos.add(d); res.append(d)
    return res


def achar_intervalo(t, hoje):
    """para viagens: (inicio, fim). Percebe 'de sexta a domingo', 'fim de semana', '3 dias'..."""
    s = simples(t)
    if "fim de semana" in s or "fim-de-semana" in s:
        sab = proximo_dia_semana(hoje, 5, incluir_hoje=True)
        return sab, sab + timedelta(days=1)
    datas = achar_datas(t, hoje)
    m = re.search(r"\b(\d{1,2}|uma|um|dois|duas|tres|quatro|cinco|seis|sete) (dias|noites|semana)", s)
    n = None
    if m:
        palavras = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7}
        n = int(m[1]) if m[1].isdigit() else palavras[m[1]]
        if m[2] == "semana": n *= 7
        elif m[2] == "noites": n += 1
    if len(datas) >= 2:
        ini, fim = datas[0], datas[1]
        if fim < ini: fim += timedelta(days=7)
        return ini, fim
    ini = datas[0] if datas else hoje + timedelta(days=1)
    return ini, ini + timedelta(days=(n or 1) - 1)


def achar_hora(t):
    s = simples(t)
    m = re.search(r"\b(?:as |a )?(\d{1,2})(?:[:h](\d{2})|h| horas)\b(?: da (manha|tarde|noite))?", s)
    if not m:
        m = re.search(r"\bas (\d{1,2})()(?: da (manha|tarde|noite))?\b", s)
    if not m:
        return None
    h, mi = int(m[1]), int(m[2] or 0)
    if m[3] in ("tarde", "noite") and h < 12: h += 12
    if h > 23 or mi > 59: return None
    return f"{h:02d}:{mi:02d}"


def limpar_titulo(t, gatilhos):
    """tira do texto as palavras de comando, as datas e as horas, para sobrar o titulo"""
    r = t.strip()
    padroes = gatilhos + [
        r"\bdepois de amanh[aã]\b", r"\bamanh[aã]\b", r"\bhoje\b",
        r"\b(?:na |no |esta |este |pr[oó]xima |pr[oó]ximo )?(?:segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo)(?:-feira| feira)?\b",
        r"\b(?:no |o )?dia \d{1,2}(?: de \w+)?\b", r"\b\d{1,2} de (?:" + "|".join(MESES).replace("marco", "mar[cç]o") + r")\b",
        r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
        r"\b(?:[aà]s |a )?\d{1,2}(?:[:h]\d{2}|h| horas)\b(?: da (?:manh[aã]|tarde|noite))?", r"\b[aà]s \d{1,2}\b(?: da (?:manh[aã]|tarde|noite))?",
        r"\bat[eé]\b(?=\s*$)", r"\b(?:urgente|importante|sem falta)\b",
    ]
    for p in padroes:
        r = re.sub(p, " ", r, flags=re.I)
    r = re.sub(r"\s+", " ", r).strip(" :,.-")
    r = re.sub(r"^(?:o |a |um |uma |que )", "", r, flags=re.I)
    r = re.sub(r"\s+(?:para|no|na|ate|até|de|do|da|e|o|a)$", "", r, flags=re.I).strip(" :,.-")
    return r[:1].upper() + r[1:] if r else r


def adivinhar_area(t):
    s = simples(t)
    regras = [
        ("escola", r"\b(teste|tpc|trabalho|estudar|estudo|ficha|exame|professor|stora|stor|aula|mat|port|ing|cn|cfq|hist|geo|resumo)"),
        ("dropshipping", r"\b(loja|encomenda|cliente|shopify|produto|fornecedor|anuncio|venda|dropshipping)"),
        ("desporto", r"\b(treino|jogo|ginasio|correr|futebol|basquet|natacao|desporto)"),
        ("musica", r"\b(musica|guitarra|piano|beat|cancao|ensaio)"),
        ("encriptar", r"\b(encript|cifra|hash|cripto)"),
        ("programar", r"\b(programar|codigo|servidor|python|site|app|bug|github)"),
    ]
    for area, p in regras:
        if re.search(p, s):
            return area
    return "outro"


# ---------- perceber a intencao ----------

def entender(texto, hoje=None):
    hoje = hoje or date.today()
    t = texto.strip()
    s = simples(t)
    if not s:
        return "ajuda", {}

    if re.search(r"\b(mala|malas|bagagem|o que (?:e que )?levo|o que devo levar|vou viajar|viagem)\b|^vou (?:a|ao|a|para|pra) ", s):
        ini, fim = achar_intervalo(t, hoje)
        return "mala", {"destino": achar_destino(t), "inicio": ini, "fim": fim}

    if re.search(r"^(?:toma nota|tomar nota|anota|apontar|aponta|nota|guarda (?:isto|esta nota))\b", s):
        txt = re.sub(r"^(?:toma nota|tomar nota|anota|apontar|aponta|nota|guarda (?:isto|esta nota))(?:\s+(?:que|de|disto))?\s*[:,-]?\s*", "", t, flags=re.I)
        return "nota", {"texto": txt.strip()}

    if re.search(r"\b(mostra|ver|quais|le|lê|lista)\b.*\bnotas\b|^notas$|^as minhas notas", s):
        return "ver_notas", {}

    if re.search(r"^(?:marca|marcar|agenda|agendar|mete no calendario|adiciona (?:o |um )?evento|evento)\b", s):
        datas = achar_datas(t, hoje)
        titulo = limpar_titulo(t, [r"^(?:marca|marcar|agenda|agendar|mete no calend[aá]rio|adiciona (?:o |um )?evento|evento)\b(?: (?:o|a|um|uma))?"])
        return "evento", {"titulo": titulo, "data": datas[0] if datas else None, "hora": achar_hora(t)}

    if re.search(r"^(?:tenho de|tenho que|preciso de|tarefa|lembra-me de|lembra me de|nao me deixes esquecer de)\b", s):
        datas = achar_datas(t, hoje)
        titulo = limpar_titulo(t, [r"^(?:tenho de|tenho que|preciso de|tarefa|lembra-me de|lembra me de|n[aã]o me deixes esquecer de)\b\s*:?"])
        return "tarefa", {"titulo": titulo, "prazo": datas[0] if datas else None, "area": adivinhar_area(t),
                          "prioridade": 1 if re.search(r"\b(urgente|importante|ja|sem falta)\b", s) else 2}

    if re.fullmatch(r"(bom dia|boa tarde|boa noite|ola|oi|hey|hello|eai|e ai)[!. ]*", s):
        return "dia", {"data": hoje, "saudacao": s.split("!")[0].strip()}

    if re.search(r"\b(o que tenho|que tenho|como e o meu dia|como esta o meu dia|o meu dia|planos|agenda de|horario de)\b", s) \
            or s in ("hoje", "amanha", "hoje?", "amanha?"):
        datas = achar_datas(t, hoje)
        return "dia", {"data": datas[0] if datas else hoje}

    if re.search(r"\b(proximo teste|proximos testes|testes|quando e o teste)\b", s):
        return "testes", {}

    return "ajuda", {}


def achar_destino(t):
    """o sitio depois de 'para', 'ao', 'em'... ('a' so se nao houver outra). Pode ter 'de': Rio de Janeiro."""
    pare = set(DIAS_SEMANA) | {"amanha", "hoje", "dia", "dias", "fim", "semana", "este", "esta", "proximo", "proxima",
                               "uns", "umas", "dois", "tres", "e", "com", "ate", "durante", "a", "partir", "para",
                               "mala", "viagem", "levar", "noites", "no", "na"}
    artigos = {"o", "a", "os", "as"}
    ligacoes = {"de", "do", "da", "dos", "das"}
    palavras = re.findall(r"[\wÀ-ÿ'-]+", t)
    for preps in (("para", "pra", "pro", "ao", "aos", "à", "em", "no", "na"), ("a",)):
        for i, p in enumerate(palavras):
            if simples(p) not in preps:
                continue
            resto = palavras[i + 1:]
            while resto and simples(resto[0]) in artigos:
                resto = resto[1:]
            nome = []
            for q in resto[:4]:
                sq = simples(q)
                if q.isdigit() or (sq in pare and not (nome and sq in ligacoes)):
                    break
                if sq in ligacoes and not nome:
                    break
                if sq in ligacoes:  # "de" so conta se vier mais nome a seguir
                    nome.append(q); continue
                nome.append(q)
            while nome and simples(nome[-1]) in ligacoes:
                nome.pop()
            if nome and simples(nome[0]) not in pare:
                return " ".join(nome)
    return None


# ---------- previsao do tempo (Open-Meteo, sem chave) ----------

def _json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "central"}), timeout=8) as r:
        return json.loads(r.read())


def previsao(destino, ini, fim):
    """devolve {nome, dias: [(data, max, min, chuva%)]} ou None se nao der"""
    try:
        palavras = destino.split()
        local = None
        for n in range(len(palavras), 0, -1):  # tenta "rio de janeiro", depois "rio de", depois "rio"
            q = urllib.parse.quote(" ".join(palavras[:n]))
            r = _json(f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=pt&format=json")
            if r.get("results"):
                local = r["results"][0]; break
        if not local:
            return None
        m = _json(f"https://api.open-meteo.com/v1/forecast?latitude={local['latitude']}&longitude={local['longitude']}"
                  f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto&forecast_days=16")
        d = m["daily"]
        dias = [(date.fromisoformat(x), d["temperature_2m_max"][i], d["temperature_2m_min"][i],
                 d["precipitation_probability_max"][i] or 0)
                for i, x in enumerate(d["time"]) if ini <= date.fromisoformat(x) <= fim]
        return {"nome": f"{local['name']}, {local.get('country', '')}".strip(", "), "dias": dias}
    except Exception:
        return None


# ---------- fazer a mala ----------

def fazer_mala(roupa, n_dias, tmax, tmin, chuva):
    """regras simples. roupa = lista de dicts da tabela roupa. Devolve (linhas, avisos)."""
    arrumada = [p for p in roupa if p["estado"] == "arrumada"]
    por_tipo = lambda tipos: [p for p in arrumada if p["tipo"] in tipos]
    sujas = lambda tipos: [p for p in roupa if p["tipo"] in tipos and p["estado"] != "arrumada"]
    linhas, avisos = [], []

    def escolher(rotulo, tipos, quantos):
        if quantos <= 0:
            return
        ha = por_tipo(tipos)
        escolhidas = ha[:quantos]
        nomes = ", ".join(p["nome"] + (f" ({p['local']})" if p.get("local") else "") for p in escolhidas)
        linhas.append(f"{quantos}× {rotulo}" + (f": {nomes}" if nomes else ""))
        if len(ha) < quantos:
            falta = sujas(tipos)
            avisos.append(f"Só tens {len(ha)} {rotulo.lower()} arrumadas" +
                          (f" ({', '.join(p['nome'] + ' está ' + p['estado'] for p in falta[:3])})" if falta else "") + ".")

    calor = tmax is not None and tmax >= 24
    frio = tmin is not None and tmin < 12
    escolher("T-shirts", ["t-shirt"], n_dias + (1 if n_dias > 2 else 0))
    if calor:
        escolher("Calções", ["calcoes"], max(1, math.ceil(n_dias / 2)))
        escolher("Calças", ["calcas"], 1)
    else:
        escolher("Calças", ["calcas"], max(1, math.ceil(n_dias / 3)))
    if tmin is None or tmin < 17:
        escolher("Sweats ou camisolas", ["sweat", "camisola"], 1 if n_dias <= 4 else 2)
    if frio or chuva >= 40:
        escolher("Casaco" + (" (de chuva, se tiveres)" if chuva >= 40 else ""), ["casaco"], 1)
    escolher("Calçado", ["calcado"], 2 if chuva >= 60 or n_dias > 4 else 1)
    linhas.append(f"{n_dias + 1}× roupa interior e meias")
    linhas.append("Pijama, escova e pasta de dentes, gel de banho, desodorizante")
    linhas.append("Carregador do telemóvel" + (" e guarda-chuva" if chuva >= 40 else ""))
    return linhas, avisos


# ---------- responder ----------

def fmt_data(d, hoje):
    if d == hoje: return "hoje"
    if d == hoje + timedelta(days=1): return "amanhã"
    dif = (d - hoje).days
    if 0 < dif < 7: return f"{NOMES_DIAS[d.weekday()]} ({d.day}/{d.month})"
    return f"{d.day}/{d.month}"


AJUDA = {
    "resposta": "Ainda não percebi. Experimenta uma destas:",
    "sugestoes": ["O que tenho amanhã?", "Faz-me a mala para Madrid de sexta a domingo",
                  "Marca jantar com a avó sábado às 20h", "Toma nota: levar a calculadora",
                  "Tenho de acabar o trabalho de CN até quinta", "Quando é o próximo teste?"],
}


def responder(texto, con, hoje=None):
    """con = ligacao sqlite (row_factory = Row). Devolve {resposta, itens?, sugestoes?, mudou?}"""
    hoje = hoje or date.today()
    intencao, d = entender(texto, hoje)

    if intencao == "nota":
        if not d["texto"]:
            return {"resposta": "O que queres que eu anote? Por exemplo: toma nota: levar a calculadora."}
        con.execute("INSERT INTO notas (texto) VALUES (?)", (d["texto"][:500],))
        return {"resposta": "Anotado.", "itens": [d["texto"]], "mudou": True}

    if intencao == "ver_notas":
        notas = con.execute("SELECT * FROM notas ORDER BY id DESC LIMIT 15").fetchall()
        if not notas:
            return {"resposta": "Ainda não tens notas. Diz 'toma nota: ...' para criar uma."}
        return {"resposta": f"As tuas últimas {len(notas)} notas:", "itens": [n["texto"] for n in notas]}

    if intencao == "evento":
        if not d["titulo"]:
            return {"resposta": "O que queres marcar? Por exemplo: marca jantar com a avó sábado às 20h."}
        if not d["data"]:
            return {"resposta": f"Para quando é '{d['titulo']}'? Diz-me o dia, por exemplo: marca {d['titulo'].lower()} sexta às 18h."}
        con.execute("INSERT INTO eventos (titulo, data, hora) VALUES (?,?,?)", (d["titulo"][:200], d["data"].isoformat(), d["hora"]))
        quando = fmt_data(d["data"], hoje) + (f" às {d['hora']}" if d["hora"] else "")
        return {"resposta": f"Marquei {d['titulo']} para {quando}. Já aparece no calendário.", "mudou": True}

    if intencao == "tarefa":
        if not d["titulo"]:
            return {"resposta": "Qual é a tarefa? Por exemplo: tenho de acabar o trabalho de CN até quinta."}
        con.execute("INSERT INTO tarefas (titulo, area, prioridade, prazo) VALUES (?,?,?,?)",
                    (d["titulo"][:200], d["area"], d["prioridade"], d["prazo"].isoformat() if d["prazo"] else None))
        extra = f", para {fmt_data(d['prazo'], hoje)}" if d["prazo"] else ""
        return {"resposta": f"Nova tarefa de {d['area']}: {d['titulo']}{extra}.", "mudou": True}

    if intencao == "testes":
        ts = con.execute("SELECT * FROM testes WHERE data >= ? ORDER BY data LIMIT 6", (hoje.isoformat(),)).fetchall()
        if not ts:
            return {"resposta": "Não tens testes marcados. Mete-os no separador Estudo."}
        return {"resposta": "Os teus próximos testes:",
                "itens": [f"{t['disciplina']}: {fmt_data(date.fromisoformat(t['data']), hoje)}" +
                          (f" · {t['materia']}" if t["materia"] else "") for t in ts]}

    if intencao == "dia":
        dia = d["data"]; iso = dia.isoformat()
        itens = []
        aulas = con.execute("SELECT * FROM horario WHERE dia = ? ORDER BY inicio", (dia.weekday(),)).fetchall()
        escola = [a for a in aulas if a["area"] == "escola"]
        if escola:
            itens.append(f"Aulas das {escola[0]['inicio']} às {escola[-1]['fim']}: " + ", ".join(dict.fromkeys(a["titulo"] for a in escola)))
        for a in aulas:
            if a["area"] != "escola":
                itens.append(f"{a['inicio']} {a['titulo']}")
        for e in con.execute("SELECT * FROM eventos WHERE data = ? ORDER BY hora", (iso,)):
            itens.append(f"{e['hora'] or 'Durante o dia'} · {e['titulo']}")
        for t in con.execute("SELECT * FROM testes WHERE data = ?", (iso,)):
            itens.append(f"TESTE de {t['disciplina']}" + (f" ({t['materia']})" if t["materia"] else ""))
        for t in con.execute("SELECT * FROM testes WHERE data > ? AND data <= ? ORDER BY data", (iso, (dia + timedelta(days=3)).isoformat())):
            itens.append(f"Estudar para o teste de {t['disciplina']} ({fmt_data(date.fromisoformat(t['data']), hoje)})")
        for t in con.execute("SELECT * FROM tarefas WHERE feita = 0 AND prazo IS NOT NULL AND prazo <= ? ORDER BY prazo", (iso,)):
            atrasada = t["prazo"] < hoje.isoformat()
            itens.append(f"Tarefa: {t['titulo']}" + (" (atrasada!)" if atrasada else ""))
        ola = ""
        if d.get("saudacao"):
            ola = {"bom dia": "Bom dia!", "boa tarde": "Boa tarde!", "boa noite": "Boa noite!"}.get(d["saudacao"], "Olá!") + " "
        if not itens:
            return {"resposta": f"{ola}Não tens nada marcado para {fmt_data(dia, hoje)}. Dia livre."}
        return {"resposta": f"{ola}Para {fmt_data(dia, hoje)}:", "itens": itens}

    if intencao == "mala":
        ini, fim = d["inicio"], d["fim"]
        n = (fim - ini).days + 1
        roupa = [dict(r) for r in con.execute("SELECT * FROM roupa")]
        if d["destino"]:
            d["destino"] = " ".join(w if w in ("de", "do", "da", "dos", "das") else w[:1].upper() + w[1:] for w in d["destino"].split())
        prev = previsao(d["destino"], ini, fim) if d["destino"] else None
        if prev and prev["dias"]:
            tmax = max(x[1] for x in prev["dias"]); tmin = min(x[2] for x in prev["dias"]); chuva = max(x[3] for x in prev["dias"])
            tempo = f"Em {prev['nome']}: entre {round(tmin)}° e {round(tmax)}°, chuva até {round(chuva)}%."
        else:
            tmax = tmin = None; chuva = 30
            tempo = ("Não sei para onde vais, por isso fiz uma mala genérica. Diz por exemplo: mala para Madrid de sexta a domingo."
                     if not d["destino"] else
                     f"Não consegui ver a previsão para {d['destino']} (fora dos próximos 16 dias, ou sem internet). Mala genérica.")
        linhas, avisos = fazer_mala(roupa, n, tmax, tmin, chuva)
        if not roupa:
            avisos.append("Ainda não tens roupa na central. Adiciona-a no separador Roupa para eu escolher as peças.")
        periodo = f"{fmt_data(ini, hoje)} a {fmt_data(fim, hoje)}" if n > 1 else fmt_data(ini, hoje)
        return {"resposta": f"Mala para {n} dia{'s' if n > 1 else ''} ({periodo}). {tempo}", "itens": linhas + avisos}

    return AJUDA

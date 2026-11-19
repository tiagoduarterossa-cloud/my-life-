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
import random
import re
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, timedelta
from datetime import datetime as _agora_dt

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
    m = re.search(r"\b(?:de|dia|dias|entre) (\d{1,2}) (?:a|e|ate) (\d{1,2})\b(?: de (" + "|".join(MESES) + r")\b)?", s2)
    if m and m[3]:   # "de 3 a 7 de marco": o mes vale para os dois dias
        try:
            b = date(hoje.year, MESES.index(m[3]) + 1, int(m[2]))
            if b < hoje: b = b.replace(year=b.year + 1)
            a = b.replace(day=int(m[1])) if int(m[1]) <= int(m[2]) else (b.replace(day=1) - timedelta(days=1)).replace(day=int(m[1]))
            achados += [(m.start(), a), (m.start() + 1, b)]
        except ValueError:
            pass
    elif m:
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
    m = re.search(r"\b(?:as |a |para as )?(\d{1,2}) e (meia|um quarto|quarto|\d{1,2})\b(?: da (manha|tarde|noite))?", s)
    if m and not re.search(r"\b(?:dia|de|entre) " + m[1] + r" e ", s):
        mi = {"meia": 30, "um quarto": 15, "quarto": 15}.get(m[2])
        mi = mi if mi is not None else int(m[2])
        h = int(m[1])
        if m[3] in ("tarde", "noite") and h < 12: h += 12
        if h <= 23 and mi <= 59:
            return f"{h:02d}:{mi:02d}"
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
        r"\b(?:[aà]s |a |para as )?\d{1,2} e (?:meia|um quarto|quarto|\d{1,2})\b(?: da (?:manh[aã]|tarde|noite))?",
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

    if re.search(r"\b(pausa|para|parar|pausar|stop)\b.*\b(musica|spotify|som)\b|^(pausa|stop)$", s):
        return "musica", {"o": "pausar"}
    if re.search(r"\b(proxima|seguinte|passa a frente|salta|skip)\b.*\b(musica|cancao|faixa)?|^(proxima|skip)$", s) and re.search(r"musica|cancao|faixa|^proxima$|^skip$|passa a frente|salta", s):
        return "musica", {"o": "seguinte"}
    if re.search(r"\b(musica anterior|volta a anterior|cancao anterior)\b", s):
        return "musica", {"o": "anterior"}
    m = re.search(r"\bvolume (?:a |para |no |nos )?(\d{1,3})\b", s)
    if m:
        return "musica", {"o": "volume", "valor": int(m[1])}
    if re.search(r"\b(aumenta|sobe|mais alto)\b.*\b(volume|musica|som)\b|\bmais alto\b", s):
        return "musica", {"o": "volume_mais"}
    if re.search(r"\b(baixa|diminui|mais baixo)\b.*\b(volume|musica|som)\b|\bmais baixo\b", s):
        return "musica", {"o": "volume_menos"}
    if re.search(r"\b(o que esta a tocar|que musica e esta|que musica e essa|como se chama esta musica)\b", s):
        return "musica", {"o": "agora"}
    if re.search(r"^(poe|pões|poes|mete|toca|tocar|quero ouvir|play|continua a musica|retoma)\b", s) and \
            re.search(r"\b(musica|spotify|playlist|ouvir|tocar|toca|play|album|retoma|continua)\b", s):
        pedido = re.sub(r"^(poe|pões|poes|mete|toca|tocar|quero ouvir|play|continua a|retoma)\s*", "", s)
        pedido = re.sub(r"\b(a |uma |um |alguma |me )?\b(musica|musicas|playlist|no spotify|do spotify|spotify|a tocar|para mim)\b", " ", pedido)
        pedido = re.sub(r"^\s*(de|do|da|dos|das|para)\s+", "", " ".join(pedido.split())).strip()
        temas = {"estudo": "lofi study", "estudar": "lofi study", "dormir": "sleep", "calma": "chill", "festa": "party hits",
                 "treino": "workout", "concentrar": "deep focus", "relaxar": "chill vibes"}
        pedido = temas.get(pedido, pedido)
        return "musica", {"o": "tocar", "pedido": pedido}

    if re.search(r"https?://|www\.|\b[\w-]+\.(com|pt|net|org|xyz|io|me|ly|gg|app)\b", s) and \
            re.search(r"\b(seguro|confiavel|phishing|burla|perigoso|abrir|clicar|verifica|analisa|legit)\b", s):
        m = re.search(r"(https?://\S+|www\.\S+|[\w.-]+\.(?:com|pt|net|org|xyz|io|me|ly|gg|app)\S*)", t)
        return "link", {"link": m[1] if m else ""}
    if re.fullmatch(r"(diz-me |sabes )?(que|q) horas (sao|e|sao agora)( agora)?|horas|que horas", s.strip(" ?!.,")):
        return "horas", {}
    if re.fullmatch(r"(que|q) dia (e|e hoje|e que e hoje|estamos)( hoje)?|em que dia estamos|que data e hoje|a quantos estamos", s.strip(" ?!.,")):
        return "data_hoje", {}
    # ----- familia -----
    m = re.match(r"^(liguei|falei|telefonei|estive|fui visitar|visitei)\b(?: (?:a|ao|aos|as|com|para))?\s*(.+)", s)
    if m and re.search(r"\b(av[oó]s?|tias?|tios?|prim[oa]s?|madrinha|padrinho|familia|bisav[oó]s?)\b", m[2]):
        return "familia_contacto", {"quem": m[2]}
    if re.search(r"\b(ha quanto tempo|quando foi a ultima vez)\b.*\b(ligo|ligar|falo|falar|liguei|falei|vejo|visito|visitei)\b", s):
        return "familia_tempo", {}
    if re.search(r"\b(quando faz anos|quando e o aniversario|aniversarios?|faz anos)\b", s):
        return "familia_anos", {}
    if re.search(r"\b(mostra o mapa|abre o mapa|mapa|ver o mapa)\b", s):
        return "mapa", {}
    if re.search(r"\b(como esta|como estao|ha algum aviso|algum aviso|algum perigo|esta tudo bem|esta tudo ok|que tempo|tempo)\b.*\b(av[oó]s?|av[oô]|tia|tio|tias|tios|prim[oa]s?|madrinha|padrinho|familia|bisav[oó])\b|\bcasa d[aeo]s? (?:avos?|tia|tio|familia|prim)", s) and \
            not re.search(r"^(marca|tenho de|toma nota)", s):
        return "familia_estado", {}

    if re.search(r"\b(claude|ia|api|inteligencia artificial)\b", s) and re.search(r"\b(custo|custos|custa|custou|gastei|gasto|gastos|gastou|quanto|fatura|dinheiro)\b", s):
        return "custo_ia", {}

    m = re.search(r"\bgastei (\d+(?:[.,]\d{1,2})?)\s*(?:euros?|€)?\s*(?:(?:em|no|na|nos|nas|com|de|para)\s+(.+))?", s)
    if m:
        desc = (m[2] or "").strip()
        loja_ctx = re.search(r"loja|anuncio|ads|tiktok|facebook|meta|instagram|google ads|shopify|app|fornecedor|amostra|dominio|tema", desc + " " + s)
        tipo = "anuncios" if re.search(r"anuncio|ads|tiktok|facebook|meta|instagram|publicidade", desc) else "apps" if re.search(r"\bapp|aplicacao|shopify|tema|dominio", desc) else "outro"
        return "despesa", {"valor": float(m[1].replace(",", ".")), "descricao": desc or "despesa", "tipo": tipo, "da_loja": bool(loja_ctx)}
    if re.search(r"\b(loja|vendas|vendi|lucro|lucrei|encomendas?|shopify|faturei|faturacao)\b", s) and not re.search(r"\b(marca|tarefa|tenho de)\b", s):
        p = "ontem" if "ontem" in s else "semana" if "semana" in s else "mes" if re.search(r"\bmes\b", s) else "hoje"
        if re.search(r"por enviar|enviar|pendentes|preparar", s):
            p = "mes"
        return "loja", {"periodo": p, "enviar": bool(re.search(r"por enviar|enviar|pendentes|preparar", s))}

    # modos do Jarvis: amigos, treino, revisao (o modo estudo e a rotina "Modo estudo")
    sair_modo = re.search(r"(?:\b(?:sai|sair|saimos|acabou|acaba|termina|terminar|desliga|fecha)\b.*|^para (?:o )?)\bmodo (de )?(estudo|amigos|treino|revisao)\b", s)
    if sair_modo:
        return "modo_sair", {"tipo": sair_modo[2]}
    if re.search(r"\b(os amigos (ja )?(foram|sairam)|ja foram embora)\b", s):
        return "modo_sair", {"tipo": "amigos"}
    if re.search(r"\bmodo (de )?amigos\b|^(?:chegaram|vieram|estao ca) (?:uns |os |os meus )?amigos$", s):
        return "modo_amigos", {}
    if (re.search(r"\bmodo (de )?treino\b|^(?:bora|vamos) treinar\b|^comeca o treino\b", s)
            and not re.search(r"\b(marca|lembra|agenda|tenho de|tarefa|evento)\b", s)):
        num = lambda rx: (lambda m: int(m[1]) if m else None)(re.search(rx, s))
        rondas = num(r"(\d+) (?:rondas|series|vezes)")
        trabalho = num(r"(\d+) segundos(?! de (?:descanso|pausa))")    # o primeiro tempo que nao e o descanso
        descanso = num(r"(\d+) (?:segundos )?de (?:descanso|pausa)")
        minutos = num(r"(\d+) minutos")
        trabalho, descanso = min(max(trabalho or 40, 5), 600), min(max(descanso if descanso is not None else 20, 0), 600)
        if not rondas and minutos:
            rondas = max(1, round(minutos * 60 / (trabalho + descanso)))
        return "modo_treino", {"rondas": min(max(rondas or 8, 1), 50), "trabalho": trabalho, "descanso": descanso}
    if re.search(r"\bmodo (de )?revisao\b|\b(faz|fazes)(-me| me)? perguntas\b|\btesta-?me\b|\bquiz\b|\b(ajuda-?me a )?rever (a materia|para o teste)\b", s):
        return "modo_revisao", {"texto": t}

    # copias de seguranca do vida.db (antes da "seguranca" da rede e da central)
    if re.search(r"\b(copias? de seguranca|backups?)\b", s):
        return "backup", {"fazer": bool(re.search(r"\b(faz|fazer|faca|cria|criar|guarda|agora)\b", s))}

    # modo viagem (antes da "mala" rapida, que continua a existir para escapadinhas)
    if re.search(r"\b(nova viagem|marca (?:uma |a )?viagem|cria (?:uma )?viagem|regista (?:uma )?viagem)\b", s):
        ini, fim = achar_intervalo(t, hoje)
        return "viagem_criar", {"destino": achar_destino(t), "inicio": ini, "fim": fim, "datas": len(achar_datas(t, hoje)) >= 2}
    if re.search(r"\bmodo (de )?viagem\b", s) or \
            (re.search(r"\bviagem\b", s) and re.search(r"\b(falta|faltam|quando|como esta|como vai|estado|quanto tempo)\b", s)) or \
            re.search(r"\b(o que falta|que falta|ja fiz|como esta|como vai|falta por)\b.*\bmala\b|\bmala\b.*\b(esta feita|falta)\b", s):
        return "viagem", {}

    # o que esta a funcionar (wi-fi, internet, whatsapp...)
    import servicos as _sv
    nomes_sv = {simples(_sv_n): _sv_n for _sv_n, _, _ in _sv.SERVICOS}
    nomes_sv.update({"teams": "Microsoft Teams", "whats": "WhatsApp", "zap": "WhatsApp", "insta": "Instagram", "sns": "SNS 24",
                     "comboios": "CP Comboios", "comboio": "CP Comboios", "metro": "Metro de Lisboa", "youtube": "YouTube", "tiktok": "TikTok"})
    alvo = next((v for k, v in nomes_sv.items() if re.search(r"\b" + re.escape(k), s)), None)
    if re.search(r"\b(esta tudo a funcionar|o que esta a funcionar|o que nao esta a funcionar|estado dos servicos|servicos|esta em baixo|estao em baixo|foi abaixo|caiu|nao funciona|nao esta a funcionar|esta a funcionar|funciona|ha internet|tenho internet|ha net|tenho net)\b", s) and \
            (alvo or re.search(r"\b(internet|wi-?fi|wifi|net|router|tudo|servicos)\b", s)):
        return "servicos", {"alvo": alvo}
    if re.search(r"\b(rede|wi-?fi|wifi|router|internet)\b.*\b(segura|seguro|segurança|seguranca|protegida|protegido)\b|\b(verifica|analisa|testa)\b.*\b(rede|wifi|wi-fi|router)\b", s):
        return "rede", {}
    if re.search(r"\b(janela|janelas|porta|portas|esta tudo fechado|ficou alguma coisa aberta|deixei .* aberta|luzes .*(ligadas|desligadas|acesas|apagadas)|ha luzes ligadas|estado da casa)\b", s):
        return "casa", {}
    if re.search(r"\b(modo (de )?apagao|modo (de )?emergencia)\b", s):
        sair = bool(re.search(r"\b(sai|sair|desliga|desativa|acabou|termina|voltou)\b", s))
        return "apagao", {"ligado": not sair}
    if re.search(r"\b(apagao|apagoes|faltou a luz|falta de luz|ha luz|corte de luz|sem luz|caiu a internet|ha internet)\b", s):
        return "energia", {}
    if re.search(r"\b(avisos?|alerta|alertas|desastres?|catastrofe|sismos?|terramotos?|tremor de terra|incendios?|fogos?|tsunami|tempestade|esta tudo bem la fora|protecao civil|ipma)\b", s):
        return "desastres", {}
    if re.search(r"\b(alguma coisa suspeita|algo suspeito|tudo seguro|esta tudo seguro|relatorio de seguranca|quem esta ligado|quem acedeu|seguranca da central|ha intrusos|alguem entrou)\b", s):
        return "seguranca", {}
    if re.search(r"\b(noticias|noticia|novidades|o que se passa no mundo|ultima hora|headlines)\b", s):
        import noticias
        return "noticias", {"categoria": noticias.categoria_da_frase(s)}
    if re.search(r"\b(ciberataques|ciber ataques|ataques informaticos|vulnerabilidades|falhas de seguranca|ameacas|ransomware|hackers)\b", s):
        return "ciber", {}

    # primeiro o que DESLIGA, para "desativa o modo jarvis" nao ser lido como "modo jarvis"
    if re.search(r"\b(para de ouvir|pára de ouvir|deixa de ouvir|nao oucas|modo silencio|silencio total|desliga a escuta|desliga o microfone|nao me oucas)\b", s):
        return "escuta", {"ligar": False}
    if re.search(r"\b(fecha-te|fecha te|fechate|fecha-se|podes fechar|fecha o ecra|fecha o jarvis|close yourself|sai do ecra|fecha isso|podes ir|modo normal|"
                 r"(desativa|desativar|desliga|desligar|sai|sair|fecha|fechar|termina|terminar|encerra|encerrar|cancela)\w*\b.*\b(modo|jarvis|iron ?man|ecra|protocolo|homem de ferro))\b", s):
        return "hud", {"abrir": False}
    if re.search(r"\b(iron ?man|ironmen|airon ?man|modo homem de ferro|homem de ferro|protocolo stark|modo stark)\b", s):
        return "hud", {"abrir": True, "modo": "ironman"}
    if re.search(r"\b(modo jarvis|abre o jarvis|mostra o jarvis|acorda o jarvis|ecra jarvis|abre-te)\b", s):
        return "hud", {"abrir": True}
    if re.search(r"\b(o que e isto|o que e isso|o que estou a segurar|o que tenho na mao|olha para isto|olha isto|o que ves|ve isto|reconheces isto|em que estou a trabalhar|que objeto e este|o que e que eu tenho aqui)\b", s):
        return "ver", {"pergunta": t}
    import dispositivos
    m = re.search(r"\b(?:luz|luzes|led|leds|fita|quarto)\b(?: (?:em|a|para|de|cor))?(?: cor)? (" + "|".join(dispositivos.CORES) + r")\b", s) or \
        re.search(r"\b(?:poe|mete|muda)\b.*\b(" + "|".join(dispositivos.CORES) + r")\b.*\b(?:luz|luzes|led|fita)\b", s)
    if m:
        return "luz_cor", {"cor": m[1]}
    m = re.search(r"\b(?:luz|luzes|led|fita|brilho)\b.*?\b(\d{1,3}) ?(?:%|por cento)", s) or re.search(r"\bbrilho (?:a|para|em|no) (\d{1,3})\b", s)
    if m:
        return "luz_brilho", {"valor": int(m[1])}

    m = re.search(r"\b(liga|acende|ligar|acender|desliga|apaga|desligar|apagar)\b.*\b(luz|luzes|led|leds|fita|tomada|candeeiro)\b", s)
    if m:
        return "tomada", {"estado": "ligar" if m[1] in ("liga", "acende", "ligar", "acender") else "desligar"}

    if re.search(r"\b(alarme|alarmes|despertador|acorda-me|acordar-me|acorda me|me acordes|acordes|acordar)\b", s):
        datas = achar_datas(t, hoje)
        if re.search(r"\b(desliga|desligar|tira|tirar|cancela|cancelar|sem alarme|nao quero|nao ponhas|nao me acordes|nao acordes|nao preciso)\b", s):
            return "alarme_sem", {"data": datas[0] if datas else hoje + timedelta(days=1)}
        if re.search(r"\b(que alarmes|quais|a que horas|proximo alarme|tenho alarme|mostra)\b", s) or not achar_hora(t):
            return "alarme_ver", {}
        dias = ""
        if re.search(r"\btodos os dias\b", s): dias = "0123456"
        elif re.search(r"\b(dias de semana|dias uteis|dias de escola|de segunda a sexta|semana toda)\b", s): dias = "01234"
        elif re.search(r"\b(fins de semana|fim de semana)\b", s): dias = "56"
        nome = "Viagem" if re.search(r"\b(viagem|voo|aviao|aeroporto|comboio)\b", s) else ("Escola" if dias == "01234" else None)
        return "alarme", {"hora": achar_hora(t), "dias": dias, "data": None if dias else (datas[0] if datas else None), "nome": nome}

    if re.search(r"\b(mala|malas|bagagem|o que (?:e que )?levo|o que devo levar|vou viajar|viagem)\b|^vou (?:a|ao|a|para|pra) ", s):
        ini, fim = achar_intervalo(t, hoje)
        return "mala", {"destino": achar_destino(t), "inicio": ini, "fim": fim}

    if re.search(r"^(?:toma nota|tomar nota|anota|apontar|aponta|nota|guarda (?:isto|esta nota))\b", s):
        txt = re.sub(r"^(?:toma nota|tomar nota|anota|apontar|aponta|nota|guarda (?:isto|esta nota))(?:\s+(?:que|de|disto))?\s*[:,-]?\s*", "", t, flags=re.I)
        return "nota", {"texto": txt.strip()}

    if re.search(r"\b(mostra|ver|quais|le|lê|lista)\b.*\bnotas\b|^notas$|^as minhas notas", s):
        return "ver_notas", {}

    m = re.match(r"^(?:tenho|vou ter|marca|mete|ha|temos)(?: um| o)? (?:teste|exame|ficha de avaliacao) d[eao]s? (.+)", s)
    if m:
        resto = re.split(r"\s+(?:na|no|para|dia|a|amanha|depois|hoje|segunda|terca|quarta|quinta|sexta|sabado|domingo|\d)\b", " " + m[1])[0].strip() or m[1]
        datas = achar_datas(t, hoje)
        return "novo_teste", {"disciplina": resto, "data": datas[0] if datas else None}
    if re.search(r"^(?:marca|marcar|agenda|agendar|mete no calendario|adiciona (?:o |um )?evento|evento)\b", s):
        datas = achar_datas(t, hoje)
        titulo = limpar_titulo(t, [r"^(?:marca|marcar|agenda|agendar|mete no calend[aá]rio|adiciona (?:o |um )?evento|evento)\b(?: (?:o|a|um|uma))?"])
        return "evento", {"titulo": titulo, "data": datas[0] if datas else None, "hora": achar_hora(t)}

    if re.search(r"^(?:tenho de|tenho que|preciso de|tarefa|lembra-me de|lembra me de|nao me deixes esquecer de)\b", s):
        datas = achar_datas(t, hoje)
        titulo = limpar_titulo(t, [r"^(?:tenho de|tenho que|preciso de|tarefa|lembra-me de|lembra me de|n[aã]o me deixes esquecer de)\b\s*:?"])
        return "tarefa", {"titulo": titulo, "prazo": datas[0] if datas else None, "area": adivinhar_area(t),
                          "prioridade": 1 if re.search(r"\b(urgente|importante|ja|sem falta)\b", s) else 2}

    if re.search(r"\b(porque (e que )?me (acordaste|acordas|acordou)|para que me acordaste|o que se passa|que se passa)\b", s):
        return "acordaste", {}
    if re.fullmatch(r"(obrigad[oa]|obg|valeu|thanks|thank you|fixe obrigado|brigado)( \w+)?[!. ]*", s):
        return "obrigado", {}

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


# ---------- a maneira de falar (para a voz) ----------

def hora_falada(h):
    """'08:50' -> '8 e 50', '16:00' -> '4 da tarde', '20:30' -> '8 e meia da noite'"""
    if not h:
        return ""
    hh, mm = int(h[:2]), int(h[3:])
    parte = ""
    if hh >= 20: parte = " da noite"
    elif hh >= 13: parte = " da tarde"
    if hh > 12: hh -= 12
    if mm == 0: return f"{hh}{parte}" if parte else f"{hh} horas"
    if mm == 30: return f"{hh} e meia{parte}"
    return f"{hh} e {mm}{parte}"


def dia_falado(d, hoje):
    if d == hoje: return "hoje"
    if d == hoje + timedelta(days=1): return "amanhã"
    if d == hoje + timedelta(days=2): return "depois de amanhã"
    if 0 < (d - hoje).days < 7: return f"na {NOMES_DIAS[d.weekday()]}" if d.weekday() < 5 else f"no {NOMES_DIAS[d.weekday()]}"
    return f"no dia {d.day}"


def lista_falada(xs):
    xs = list(xs)
    if len(xs) <= 1: return "".join(xs)
    return ", ".join(xs[:-1]) + " e " + xs[-1]


CURTOS = {"Matemática": "Mat", "Educação Física": "Educação Física", "Ciências Naturais": "Ciências",
          "Físico-Química": "Físico-Química", "Cidadania e Desenvolvimento": "Cidadania"}


AJUDA = {
    "resposta": "Ainda não percebi. Experimenta uma destas:",
    "falado": "Hmm, não apanhei essa. Experimenta perguntar o que tens amanhã.",
    "sugestoes": ["O que tenho amanhã?", "Faz-me a mala para Madrid de sexta a domingo",
                  "Marca jantar com a avó sábado às 20h", "Toma nota: levar a calculadora",
                  "Tenho de acabar o trabalho de CN até quinta", "Quando é o próximo teste?"],
}


PRIVADAS = {"viagem", "viagem_criar", "loja", "despesa", "seguranca", "rede", "mapa", "familia_estado", "familia_anos", "familia_tempo", "familia_contacto"}


def responder(texto, con, hoje=None, nome=""):
    """as respostas privadas (loja, seguranca, familia) levam privado=True: o ecra so as mostra no modo Iron Man"""
    r = _responder(texto, con, hoje, nome)
    if isinstance(r, dict) and entender(texto, hoje or date.today())[0] in PRIVADAS:
        r["privado"] = True
    return r


def _responder(texto, con, hoje=None, nome=""):
    """con = ligacao sqlite (row_factory = Row).
    Devolve {resposta, falado, itens?, sugestoes?, mudou?}. 'falado' e a versao descontraida para a voz."""
    hoje = hoje or date.today()
    intencao, d = entender(texto, hoje)
    ya = random.choice

    if intencao == "nota":
        if not d["texto"]:
            return {"resposta": "O que queres que eu anote? Por exemplo: toma nota: levar a calculadora.",
                    "falado": "Anotar o quê? Diz toma nota e a coisa a seguir."}
        con.execute("INSERT INTO notas (texto) VALUES (?)", (d["texto"][:500],))
        return {"resposta": "Anotado.", "itens": [d["texto"]], "mudou": True,
                "falado": ya(["Siga, já anotei.", "Feito, está anotado.", "Na boa, ficou guardado."])}

    if intencao == "ver_notas":
        notas = con.execute("SELECT * FROM notas ORDER BY id DESC LIMIT 15").fetchall()
        if not notas:
            return {"resposta": "Ainda não tens notas. Diz 'toma nota: ...' para criar uma.",
                    "falado": "Ainda não tens notas nenhumas."}
        falado = "As últimas são: " + lista_falada(n["texto"] for n in notas[:3]) + "."
        return {"resposta": f"As tuas últimas {len(notas)} notas:", "itens": [n["texto"] for n in notas], "falado": falado}

    if intencao == "evento":
        if not d["titulo"]:
            return {"resposta": "O que queres marcar? Por exemplo: marca jantar com a avó sábado às 20h.",
                    "falado": "Marcar o quê? Diz por exemplo: marca treino sexta às 6 da tarde."}
        if not d["data"]:
            return {"resposta": f"Para quando é '{d['titulo']}'? Diz-me o dia, por exemplo: marca {d['titulo'].lower()} sexta às 18h.",
                    "falado": f"Ya, mas {d['titulo'].lower()} é para quando? Diz-me o dia."}
        con.execute("INSERT INTO eventos (titulo, data, hora) VALUES (?,?,?)", (d["titulo"][:200], d["data"].isoformat(), d["hora"]))
        quando = fmt_data(d["data"], hoje) + (f" às {d['hora']}" if d["hora"] else "")
        quando_f = dia_falado(d["data"], hoje) + (f" às {hora_falada(d['hora'])}" if d["hora"] else "")
        return {"resposta": f"Marquei {d['titulo']} para {quando}. Já aparece no calendário.", "mudou": True,
                "falado": ya(["Feito.", "Tá marcado.", "Siga."]) + f" {d['titulo']}, {quando_f}."}

    if intencao == "tarefa":
        if not d["titulo"]:
            return {"resposta": "Qual é a tarefa? Por exemplo: tenho de acabar o trabalho de CN até quinta.",
                    "falado": "Qual é a tarefa?"}
        con.execute("INSERT INTO tarefas (titulo, area, prioridade, prazo) VALUES (?,?,?,?)",
                    (d["titulo"][:200], d["area"], d["prioridade"], d["prazo"].isoformat() if d["prazo"] else None))
        extra = f", para {fmt_data(d['prazo'], hoje)}" if d["prazo"] else ""
        extra_f = f", até {dia_falado(d['prazo'], hoje)}" if d["prazo"] else ""
        return {"resposta": f"Nova tarefa de {d['area']}: {d['titulo']}{extra}.", "mudou": True,
                "falado": ya(["Tranquilo, meti na lista:", "Na boa, ficou na lista:", "Anotado nas tarefas:"]) + f" {d['titulo'].lower()}{extra_f}."}

    if intencao == "testes":
        from datetime import datetime
        op = ">=" if datetime.now().hour < 12 or hoje != date.today() else ">"  # a tarde, o teste de hoje ja passou
        ts = con.execute(f"SELECT * FROM testes WHERE data {op} ? ORDER BY data LIMIT 6", (hoje.isoformat(),)).fetchall()
        if not ts:
            return {"resposta": "Não tens testes marcados. Mete-os no separador Estudo.",
                    "falado": "Não tens testes marcados. Pelo menos que eu saiba."}
        t0 = ts[0]; d0 = date.fromisoformat(t0["data"])
        falado = f"O próximo é {CURTOS.get(t0['disciplina'], t0['disciplina'])}, {dia_falado(d0, hoje)}."
        if (d0 - hoje).days <= 2:
            falado += " Está mesmo aí, bora rever."
        if len(ts) > 1:
            t1 = ts[1]; falado += f" Depois vem {CURTOS.get(t1['disciplina'], t1['disciplina'])}, {dia_falado(date.fromisoformat(t1['data']), hoje)}."
        return {"resposta": "Os teus próximos testes:", "falado": falado,
                "itens": [f"{t['disciplina']}: {fmt_data(date.fromisoformat(t['data']), hoje)}" +
                          (f" · {t['materia']}" if t["materia"] else "") for t in ts]}

    if intencao == "dia":
        dia = d["data"]; iso = dia.isoformat(); qd = dia_falado(dia, hoje)
        itens, fala = [], []
        aulas = con.execute("SELECT * FROM horario WHERE dia = ? ORDER BY inicio", (dia.weekday(),)).fetchall()
        escola = [a for a in aulas if a["area"] == "escola"]
        if escola:
            itens.append(f"Aulas das {escola[0]['inicio']} às {escola[-1]['fim']}: " + ", ".join(dict.fromkeys(a["titulo"] for a in escola)))
            fala.append(f"{qd.capitalize()} tens aulas das {hora_falada(escola[0]['inicio'])} às {hora_falada(escola[-1]['fim'])}.")
        outros = [a for a in aulas if a["area"] != "escola"]
        for a in outros:
            itens.append(f"{a['inicio']} {a['titulo']}")
        if outros:
            fala.append("Tens também " + lista_falada(f"{a['titulo'].lower()} às {hora_falada(a['inicio'])}" for a in outros) + ".")
        evs = con.execute("SELECT * FROM eventos WHERE data = ? ORDER BY hora", (iso,)).fetchall()
        for e in evs:
            itens.append(f"{e['hora'] or 'Durante o dia'} · {e['titulo']}")
        if evs:
            fala.append("Marcado: " + lista_falada(e["titulo"] + (f" às {hora_falada(e['hora'])}" if e["hora"] else "") for e in evs) + ".")
        ts = con.execute("SELECT * FROM testes WHERE data = ?", (iso,)).fetchall()
        for t in ts:
            itens.append(f"TESTE de {t['disciplina']}" + (f" ({t['materia']})" if t["materia"] else ""))
        if ts:
            nomes = lista_falada(CURTOS.get(t["disciplina"], t["disciplina"]) for t in ts)
            fala.append(f"E atenção, tens teste de {nomes}." + (" Bora rever isso hoje." if dia > hoje else " Força nisso!"))
        prox = con.execute("SELECT * FROM testes WHERE data > ? AND data <= ? ORDER BY data", (iso, (dia + timedelta(days=3)).isoformat())).fetchall()
        for t in prox:
            itens.append(f"Estudar para o teste de {t['disciplina']} ({fmt_data(date.fromisoformat(t['data']), hoje)})")
        if prox:
            fala.append("Convém estudar para " + lista_falada(f"{CURTOS.get(t['disciplina'], t['disciplina'])}, que é {dia_falado(date.fromisoformat(t['data']), hoje)}" for t in prox[:2]) + ".")
        tar = con.execute("SELECT * FROM tarefas WHERE feita = 0 AND prazo IS NOT NULL AND prazo <= ? ORDER BY prazo", (iso,)).fetchall()
        for t in tar:
            itens.append(f"Tarefa: {t['titulo']}" + (" (atrasada!)" if t["prazo"] < hoje.isoformat() else ""))
        if tar:
            atrasadas = [t for t in tar if t["prazo"] < hoje.isoformat()]
            fala.append(("Não te esqueças: " + lista_falada(t["titulo"].lower() for t in tar[:3]) + ".") +
                        (f" E tens {len(atrasadas)} atrasada{'s' if len(atrasadas) > 1 else ''}, despacha isso." if atrasadas else ""))
        try:
            import familia
            for p in familia.listar(con, dia):
                if p["dias_aniversario"] == 0:
                    quem = familia.com_artigo(p)
                    itens.insert(0, f"🎂 Faz anos: {quem}")
                    fala.insert(0, f"{'Hoje' if dia == hoje else 'Nesse dia'} faz anos {quem}" + (f", {p['faz_anos']} anos" if p["faz_anos"] else "") + ". Não te esqueças de ligar!")
        except Exception:
            pass
        ola, ola_f = "", ""
        if d.get("saudacao"):
            ola = {"bom dia": "Bom dia!", "boa tarde": "Boa tarde!", "boa noite": "Boa noite!"}.get(d["saudacao"], "Olá!") + " "
            vir = f", {nome}" if nome else ""
            ola_f = {"bom dia": f"Bom dia{vir}!", "boa tarde": f"Boa tarde{vir}!", "boa noite": f"Boa noite{vir}!"}.get(d["saudacao"], f"Ei{vir}!") + " "
        if not itens:
            return {"resposta": f"{ola}Não tens nada marcado para {fmt_data(dia, hoje)}. Dia livre.",
                    "falado": ola_f + ya([f"{qd.capitalize()} está livre, aproveita.", f"Nada marcado para {qd}. Dia chill."])}
        return {"resposta": f"{ola}Para {fmt_data(dia, hoje)}:", "itens": itens,
                "falado": ola_f + (ya(["Ya, então.", "Ora bem.", "Bora lá."]) + " " if not ola_f else "") + " ".join(fala)}

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
            tempo_f = f"Em {prev['nome'].split(',')[0]} vai estar entre {round(tmin)} e {round(tmax)} graus" + \
                      (", e vai chover, leva casaco." if chuva >= 50 else ".")
        else:
            tmax = tmin = None; chuva = 30
            tempo = ("Não sei para onde vais, por isso fiz uma mala genérica. Diz por exemplo: mala para Madrid de sexta a domingo."
                     if not d["destino"] else
                     f"Não consegui ver a previsão para {d['destino']} (fora dos próximos 16 dias, ou sem internet). Mala genérica.")
            tempo_f = "Não consegui ver o tempo, por isso fiz uma mala normal."
        linhas, avisos = fazer_mala(roupa, n, tmax, tmin, chuva)
        if not roupa:
            avisos.append("Ainda não tens roupa na central. Adiciona-a no separador Roupa para eu escolher as peças.")
        periodo = f"{fmt_data(ini, hoje)} a {fmt_data(fim, hoje)}" if n > 1 else fmt_data(ini, hoje)
        falado = f"Bora fazer a mala para {n} dia{'s' if n > 1 else ''}. {tempo_f} Deixei-te a lista no ecrã." + \
                 (" Ah, e tens roupa que ainda está para lavar." if any("lavar" in a for a in avisos) else "")
        return {"resposta": f"Mala para {n} dia{'s' if n > 1 else ''} ({periodo}). {tempo}", "itens": linhas + avisos, "falado": falado}

    if intencao == "obrigado":
        return {"resposta": "De nada!", "falado": ya(["De nada!", "Na boa!", "Sempre que precisares."])}

    if intencao == "acordaste":
        import time as _t
        import alarmes
        u = alarmes.ultimo
        if not u or _t.time() - u.get("quando", 0) > 3 * 3600:
            return {"resposta": "Hoje não te acordei.", "falado": "Eu? Hoje não te acordei. Se calhar foi outra pessoa."}
        dia = responder("o que tenho hoje", con, hoje)
        resumo = dia.get("falado", "")
        for ab in ("Ya, então. ", "Ora bem. ", "Bora lá. "):
            resumo = resumo.replace(ab, "")
        porque = f"Acordei-te às {hora_falada(u['hora'])} por causa do alarme {u['nome']}."
        return {"resposta": porque, "itens": dia.get("itens", []), "falado": porque + " " + resumo}

    if intencao == "musica":
        import spotify
        try:
            o = d["o"]
            if o == "tocar": msg = spotify.tocar(d.get("pedido", ""))
            elif o == "pausar": msg = spotify.pausar()
            elif o == "seguinte": msg = spotify.seguinte()
            elif o == "anterior": msg = spotify.anterior()
            elif o == "volume": msg = spotify.volume(d["valor"])
            elif o in ("volume_mais", "volume_menos"):
                atual = spotify.a_tocar().get("volume") or 50
                msg = spotify.volume(atual + (15 if o == "volume_mais" else -15))
            else:
                a = spotify.a_tocar()
                if not a.get("musica"):
                    return {"resposta": "Não está nada a tocar.", "falado": "Não está nada a tocar."}
                msg = f"Está a tocar {a['musica']}, de {a['artista']}."
                return {"resposta": msg, "falado": msg}
        except spotify.ErroSpotify as e:
            m = str(e)[:1].upper() + str(e)[1:] + "."
            return {"resposta": m, "falado": m}
        curto = {"Música em pausa.": "Pausa.", "Próxima.": "Bora, próxima."}.get(msg, msg)
        return {"resposta": msg, "falado": curto, "musica": True}

    if intencao == "noticias":
        import noticias
        r = noticias.obter(d["categoria"], 5)
        ns = r["noticias"]
        if not ns:
            return {"resposta": f"Não consegui ler as notícias de {r['nome']} (sem internet?).", "falado": "Não consegui ler as notícias agora."}
        titulos = [n["titulo"] for n in ns[:3]]
        fontes = ", ".join(dict.fromkeys(n["fonte"].replace(" (EN)", "") for n in ns[:3]))
        falado = f"Notícias de {r['nome']}, do {fontes}. " + " ".join(f"{p}: {t}." for p, t in zip(["Primeiro", "Depois", "E ainda"], titulos))
        res = {"resposta": f"Notícias de {r['nome']}:", "itens": [f"{n['titulo']} ({n['fonte']})" for n in ns], "falado": falado, "noticias": True}
        if any("(EN)" in n["fonte"] for n in ns[:3]):  # em ingles: o servidor pede ao Claude para resumir em portugues
            res["resumir"] = "Notícias de " + r["nome"] + ":\n" + "\n".join(f"{n['titulo']} (fonte: {n['fonte']})" for n in ns[:3])
        return res

    if intencao == "ciber":
        import noticias
        try:
            v = noticias.vulnerabilidades(3)
        except Exception:
            return {"resposta": "Não consegui ler a lista de ataques da CISA (sem internet?).", "falado": "Não consegui ver os ciberataques agora."}
        rec = v["recentes"]
        falado = (f"Esta semana a agência de cibersegurança dos Estados Unidos confirmou {v['esta_semana']} novas falhas a serem usadas em ataques reais. " if v["esta_semana"]
                  else "Esta semana não houve falhas novas na lista de ataques reais. ")
        if rec:
            falado += f"A mais recente é no {rec[0]['produto']}" + (", e está a ser usada por grupos de ransomware." if rec[0]["ransomware"] else ".")
        return {"resposta": f"Falhas exploradas em ataques reais (CISA): {v['esta_semana']} esta semana, {v['total']} no total.",
                "itens": [f"{x['data']} · {x['produto']} · {x['cve']}" + (" · ransomware" if x["ransomware"] else "") for x in rec], "falado": falado}

    if intencao == "viagem_criar":
        import viagem
        if not d["destino"] or not d["datas"]:
            f = "Para marcar a viagem preciso do destino e das datas. Diz por exemplo: nova viagem para Madrid de 3 a 7 de março."
            return {"resposta": f, "falado": f}
        try:
            viagem.criar(con, d["destino"], d["inicio"], d["fim"])
        except ValueError as e:
            f = str(e)[:1].upper() + str(e)[1:] + "."
            return {"resposta": f, "falado": f}
        except OSError:
            f = "Não consegui chegar ao serviço de mapas. Tenta daqui a pouco."
            return {"resposta": f, "falado": f}
        r = viagem.resumo(con)
        f = f"Viagem marcada: {r['destino']}, de {viagem._dm(r['inicio'])} a {viagem._dm(r['fim'])}. Fiz-te a mala com a tua roupa. " + \
            "Enquanto estiveres fora, os alarmes de todos os dias e as rotinas ficam em pausa."
        return {"resposta": f, "falado": f, "viagem": True, "mudou": True}

    if intencao == "viagem":
        import viagem
        r = viagem.resumo(con)
        f = viagem.frase(r)
        return {"resposta": f, "falado": f, "viagem": bool(r),
                "itens": [i["texto"] for i in (r or {}).get("itens", []) if not i["feito"]][:12]}

    if intencao in ("modo_amigos", "modo_treino", "modo_revisao", "modo_sair"):
        import modos
        if intencao == "modo_amigos":
            modos.por_amigos(True)
            f = "Modo amigos ligado. Escondi as tuas coisas. Divirtam-se."
            cmd = {"acao": "modo", "tipo": "amigos"}
        elif intencao == "modo_treino":
            f = f"Modo treino: {d['rondas']} rondas de {d['trabalho']} segundos, com {d['descanso']} de descanso. Prepara-te."
            cmd = {"acao": "modo", "tipo": "treino", **d}
        elif intencao == "modo_revisao":
            disc = modos.achar_disciplina(con, d["texto"])
            if not disc:   # uma disciplina que ainda nao esta na central: "testa-me a geografia"
                m = re.search(r".*\b(?:de|a|sobre)\s+([a-z][a-z ]{2,30})$", simples(d["texto"]).strip(" ?!."))
                if m and not re.search(r"\b(mim|materia|teste|testes|revisao|rever|perguntas|estudar)\b", m[1]):
                    disc = m[1].strip().capitalize()
            if not disc:
                prox = con.execute("SELECT disciplina FROM testes WHERE data >= ? ORDER BY data LIMIT 1", (hoje.isoformat(),)).fetchone()
                disc = prox[0] if prox else None
            if not disc:
                f = "De que disciplina? Diz por exemplo: faz-me perguntas de Ciências."
                return {"resposta": f, "falado": f}
            f = f"Bora rever {disc}. Vou preparar as perguntas."
            cmd = {"acao": "modo", "tipo": "revisao", "disciplina": disc}
        else:
            f = "Modo desligado." if d["tipo"] != "amigos" else "Para sair do modo amigos, confirma no ecrã."
            cmd = {"acao": "modo", "tipo": "sair", "de": d["tipo"]}
        return {"resposta": f, "falado": f, "comandos": [cmd, {"acao": "falar", "texto": f}]}

    if intencao == "custo_ia":
        import ia
        f = ia.frase_custos()
        return {"resposta": f, "falado": f}

    if intencao == "backup":
        import backups
        e = backups.fazer(con.execute("PRAGMA database_list").fetchone()[2]) if d["fazer"] else backups.estado()
        f = ("Feito. " if d["fazer"] and not e["erro"] else "") + backups.frase(e)
        return {"resposta": f, "falado": f}

    if intencao == "apagao":
        if d["ligado"]:
            f = "Modo apagão ligado. Cortei o que gasta bateria. Se precisares de notícias sem internet, usa um rádio a pilhas."
        else:
            f = "Modo apagão desligado. Voltou tudo ao normal."
        return {"resposta": f, "falado": f, "comandos": [{"acao": "apagao", "ligado": d["ligado"]}, {"acao": "falar", "texto": f}]}

    if intencao == "novo_teste":
        nomes = {"mat": "Matemática", "matematica": "Matemática", "portugues": "Português", "ingles": "Inglês", "frances": "Francês",
                 "espanhol": "Espanhol", "alemao": "Alemão", "historia": "História", "geografia": "Geografia", "ciencias": "Ciências Naturais",
                 "cn": "Ciências Naturais", "fq": "Físico-Química", "fisico quimica": "Físico-Química", "fisico-quimica": "Físico-Química",
                 "tic": "TIC", "ef": "Educação Física", "educacao fisica": "Educação Física", "ev": "Educação Visual"}
        disc = nomes.get(d["disciplina"], d["disciplina"].capitalize())
        if not d["data"]:
            return {"resposta": f"Para quando é o teste de {disc}?", "falado": f"Para quando é o teste de {disc}? Diz, por exemplo: tenho teste de {disc} na sexta."}
        con.execute("INSERT INTO testes (disciplina, data) VALUES (?,?)", (disc[:60], d["data"].isoformat()))
        faltam = (d["data"] - hoje).days
        dica = " Começa a estudar hoje, nem que seja meia hora." if faltam <= 7 else ""
        return {"resposta": f"Teste de {disc} marcado para {d['data'].strftime('%d/%m')}.", "mudou": True,
                "falado": f"Marquei o teste de {disc} {dia_falado(d['data'], hoje)}." + dica}

    if intencao == "horas":
        agora = _agora_dt.now().strftime("%H:%M")
        return {"resposta": agora, "falado": f"São {hora_falada(agora)}." if not agora.startswith(("01:", "13:")) else f"É {hora_falada(agora)}."}
    if intencao == "data_hoje":
        meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
        f = f"Hoje é {NOMES_DIAS[hoje.weekday()]}, {hoje.day} de {meses[hoje.month - 1]}."
        return {"resposta": f, "falado": f}

    if intencao.startswith("familia") or intencao == "mapa":
        import familia
        if intencao == "mapa":
            return {"resposta": "A abrir o mapa.", "falado": ya(["Aqui está o mapa.", "A mostrar o mapa."]), "mapa": True}
        ps = familia.listar(con, hoje)
        if not ps:
            return {"resposta": "Ainda não meteste a família. Abre o modo Iron Man e carrega em Família > adicionar.", "falado": "Ainda não me disseste quem é a tua família. Abre o modo Iron Man e mete-os no painel da família."}
        if intencao == "familia_contacto":
            alvo = familia.procurar(con, d["quem"])
            if not alvo:
                return {"resposta": f"Não sei quem é '{d['quem']}'.", "falado": "Não sei quem é. Mete-o primeiro no painel da família, no modo Iron Man."}
            for p in alvo:
                con.execute("UPDATE familia SET ultimo_contacto = ? WHERE id = ?", (hoje.isoformat(), p["id"]))
            nomes = lista_falada(familia.com_artigo(p) for p in alvo)
            return {"resposta": f"Anotado: falaste com {nomes} hoje.", "falado": ya(["Boa!", "Fixe."]) + f" Anotei que falaste com {nomes}.", "mudou": True}
        if intencao == "familia_tempo":
            linhas = [(p, p["dias_sem_falar"]) for p in ps]
            itens = [f"{p['relacao']} {p['nome']}: " + (f"há {x} dias" if x is not None else "ainda não registaste") for p, x in linhas]
            alvo = familia.procurar(con, simples(texto)) or ps
            linhas = [(p, p["dias_sem_falar"]) for p in alvo]
            longe = [p for p, x in linhas if x is not None and x >= 14]
            nunca = [p for p, x in linhas if x is None]
            if len(alvo) == 1:
                x = linhas[0][1]
                f = (f"Ainda não tenho registo de falares com {familia.com_artigo(alvo[0])}." if x is None else
                     f"Falaste com {familia.com_artigo(alvo[0])} " + ("hoje." if x == 0 else "ontem." if x == 1 else f"há {x} dias.") + (" Que tal ligares hoje?" if x >= 14 else ""))
            elif longe:
                f = "Há mais de duas semanas que não falas com " + lista_falada(familia.com_artigo(p) for p in longe[:3]) + ". Que tal ligares hoje?"
            elif nunca:
                f = "Ainda não tenho registo de falares com " + lista_falada(familia.com_artigo(p) for p in nunca[:3]) + ". Quando falares, diz-me: liguei à avó."
            else:
                f = "Tens falado com todos nas últimas duas semanas. Muito bem."
            return {"resposta": f, "falado": f, "itens": itens}
        if intencao == "familia_anos":
            pedidos = familia.procurar(con, simples(texto))
            com = sorted([p for p in (pedidos or ps) if p["dias_aniversario"] is not None], key=lambda p: p["dias_aniversario"])
            if not com:
                return {"resposta": "Ainda não meteste aniversários.", "falado": "Ainda não me disseste os aniversários."}
            p = com[0]; dd = p["dias_aniversario"]
            quando = "hoje" if dd == 0 else "amanhã" if dd == 1 else f"daqui a {dd} dias"
            f = (f"{familia.com_artigo(p)[0].upper()}{familia.com_artigo(p)[1:]} faz anos {quando}" if pedidos else
                 f"O próximo aniversário é d{familia.com_artigo(p)}, {quando}") + (f", faz {p['faz_anos']} anos." if p["faz_anos"] else ".")
            if dd == 0: f += " Liga-lhe!"
            return {"resposta": f, "falado": f, "itens": [f"{p['relacao']} {p['nome']}: daqui a {p['dias_aniversario']} dias" for p in com]}
        # familia_estado: o tempo e os perigos reais perto da casa deles
        alvo = familia.procurar(con, simples(texto)) or [p for p in ps if p.get("lat") is not None]
        alvo = [p for p in alvo if p.get("lat") is not None][:3]
        if not alvo:
            return {"resposta": "Não sei onde vivem. Mete a cidade no painel da família.", "falado": "Não sei onde vivem. Mete a cidade no painel da família, no modo Iron Man."}
        frases = [familia.frase_pessoa(p, familia.perigos(p["lat"], p["lon"]), familia.tempo(p["lat"], p["lon"])) for p in alvo]
        return {"resposta": frases[0], "itens": frases[1:], "falado": " ".join(frases), **({"pessoa": alvo[0]["id"]} if len(alvo) == 1 else {})}

    if intencao == "despesa":
        if not d["da_loja"]:
            return {"resposta": "Isso foi da loja? Diz por exemplo: gastei 15 euros em anúncios do TikTok.",
                    "falado": "Foi para a loja? Se foi, diz por exemplo: gastei 15 euros em anúncios."}
        con.execute("INSERT INTO despesas (data, descricao, valor, tipo) VALUES (?,?,?,?)", (hoje.isoformat(), d["descricao"][:80], d["valor"], d["tipo"]))
        import loja as _l
        return {"resposta": f"Despesa da loja registada: {d['valor']:.2f} € ({d['descricao']}).".replace(".", ",", 1), "mudou": True,
                "falado": ya(["Anotado.", "Registado."]) + f" {_l.euros(d['valor'])} em {d['descricao']}. Isso conta para o lucro."}

    if intencao == "loja":
        import loja as _l
        try:
            r = _l.resumo(con, d["periodo"])
        except _l.ErroLoja as e:
            m = str(e)[:1].upper() + str(e)[1:] + "."
            return {"resposta": m, "falado": m}
        if d["enviar"]:
            n = len(r["por_enviar"])
            f = (f"Tens {n} encomenda{'s' if n > 1 else ''} por enviar: {', '.join(r['por_enviar'][:5])}." if n else "Não tens encomendas por enviar. Tudo despachado!")
            return {"resposta": f, "falado": f, "itens": r["por_enviar"]}
        itens = [f"Vendas: {r['receita']:.2f} €", f"Reembolsos: -{r['reembolsos']:.2f} €", f"Custo dos produtos: -{r['custo_produtos']:.2f} €",
                 f"Taxas (estimadas): -{r['taxas']:.2f} €", f"Anúncios e despesas: -{r['despesas']:.2f} €", f"LUCRO REAL: {r['lucro']:.2f} €"]
        itens += [f"Mais vendido: {t} ({q})" for t, q in r["mais_vendidos"][:2]]
        return {"resposta": f"Loja, {r['periodo']}: {r['encomendas']} encomendas.", "itens": [i.replace(".", ",") for i in itens], "falado": _l.frase(r)}

    if intencao in ("rede", "casa", "energia", "desastres", "servicos"):
        import avisos, casa
        cfg = {r["chave"]: r["valor"] for r in con.execute("SELECT * FROM config")}
        if intencao == "servicos":
            import servicos
            r = servicos.verificar()
            if d.get("alvo"):
                x = next(z for z in r["servicos"] if z["nome"] == d["alvo"])
                f = (f"O {x['nome']} está a funcionar daqui de casa" + (f", mas lento ({x['ms']} milissegundos)." if x.get("lento") else ".")) if x["ok"] else \
                    (f"O {x['nome']} não está a responder. " + ("E a tua internet também não, por isso o problema é a ligação." if not (r["internet"] and r["dns"]) else "A tua internet está bem, por isso o problema deve ser do próprio serviço."))
                return {"resposta": f, "falado": f, "servicos": True}
            return {"resposta": r["conclusao"], "falado": servicos.frase(r), "servicos": True,
                    "itens": [f"{'✅' if z['ok'] else '❌'} {z['nome']}" + (f" ({z['ms']} ms)" if z.get("ms") else "") for z in r["servicos"]]}
        if intencao == "rede":
            r = casa.verificar_rede()
            return {"resposta": f"Segurança da rede: {r['nota']}/100" if r["nota"] is not None else "Não consegui verificar a rede.", "itens": [f"{v['titulo']}: {v['texto']}" for v in r["verificacoes"]],
                    "falado": casa.frase_rede(r)}
        if intencao == "casa":
            e = casa.estado_casa(con, cfg)
            itens = [f"{x['nome']}: {x['estado']} ({x['quando'][11:16]})" for x in e["sensores"]] + \
                    [f"{x['nome']}: {'ligada' if x['ligada'] else 'desligada' if x['ligada'] is False else 'sem resposta'}" for x in e["luzes"]]
            return {"resposta": casa.frase_casa(e), "itens": itens, "falado": casa.frase_casa(e)}
        if intencao == "energia":
            en = avisos.estado_energia()
            if en["a_carregar"] is None:
                f = "Não consigo saber: falta a app Termux:API para ver se o tablet está a carregar."
            elif en["sem_luz"]:
                f = f"Parece que não há luz desde as {en['desde']}: o tablet está a funcionar a bateria."
            else:
                f = "Há luz: o tablet está a carregar normalmente." + (f" O último apagão foi das {en['historico'][-1]}." if en["historico"] else "")
            if en["sem_internet"]:
                f += f" A internet está em baixo desde as {en['sem_internet_desde']}."
            return {"resposta": f, "falado": f, "itens": [f"Apagão: {h}" for h in en["historico"]]}
        r = avisos.resumo(cfg)
        itens = []
        for a in r.get("ipma", {}).get("avisos", []): itens.append(f"IPMA · aviso {a['nivel']} · {a['tipo']}" + (f" até às {a['ate']}" if a["ate"] else ""))
        for x in r.get("sismos", {}).get("perto", []): itens.append(f"USGS · sismo {x['mag']} a {x['km']} km · {x['onde']} · {x['hora']}")
        for x in r.get("sismos", {}).get("grandes", []): itens.append(f"USGS · sismo forte {x['mag']} · {x['onde']}")
        for x in r.get("fogos", {}).get("perto", []): itens.append(f"fogos.pt · incêndio a {x['km']} km · {x['onde']} · {x['estado']}")
        f = avisos.frase(r)
        return {"resposta": f, "itens": itens, "falado": f}

    if intencao == "seguranca":
        import seguranca
        r = seguranca.resumo(con)
        novos = [a for a in r["aparelhos"] if not a["confiavel"]]
        if not novos:
            return {"resposta": "Tudo calmo: só aparelhos de confiança acederam à central.", "falado": ya(["Tudo calmo.", "Está tudo seguro."]) + " Só aparelhos teus acederam à central."}
        itens = [f"{a['tipo']} ({a['ip']}) · visto às {a['ultimo'][11:16]}" for a in novos]
        return {"resposta": f"{len(novos)} aparelho(s) que ainda não marcaste como teus:", "itens": itens,
                "falado": f"Atenção: há {len(novos)} aparelho{'s' if len(novos) > 1 else ''} que acedeu à central e que ainda não marcaste como teu. "
                          f"O último foi um {novos[0]['tipo']}. Vê em Definições, Segurança."}

    if intencao == "link":
        import seguranca
        a = seguranca.analisar_link(d["link"])
        veredito = {"ok": "Parece normal", "cuidado": "Cuidado com este link", "perigo": "Este link parece perigoso"}[a["nivel"]]
        return {"resposta": f"{veredito} ({a['dominio']}).", "itens": a["sinais"], "falado": f"{veredito}. " + a["sinais"][0]}

    if intencao == "escuta":
        return {"resposta": "Deixei de ouvir. Para voltar a ligar, toca no botão do ouvido em cima.",
                "falado": "Ok, deixo de ouvir. Quando precisares, toca no botão em cima.", "escuta": False, "hud": False}

    if intencao == "hud":
        if d.get("modo") == "ironman":
            return {"resposta": "Protocolo Iron Man.", "hud": "ironman",
                    "falado": ya(["Bem-vindo de volta, senhor. Todos os sistemas estão operacionais.",
                                  "Sistemas online, senhor. Ao seu dispor.", "Protocolo Iron Man ativado. Bem-vindo de volta, senhor."])}
        if d["abrir"]:
            return {"resposta": "Ao teu dispor.", "falado": ya(["Ao teu dispor.", "Estou aqui."]), "hud": True}
        return {"resposta": "Até já.", "falado": ya(["Até já.", "Fui."]), "hud": False}

    if intencao == "ver":
        # a central nao tem olhos: o ecra tira a foto e pergunta ao Claude
        return {"resposta": "Deixa-me ver…", "falado": "", "ver": d["pergunta"]}

    if intencao in ("luz_cor", "luz_brilho"):
        import dispositivos
        ip = con.execute("SELECT valor FROM config WHERE chave = 'wled_ip'").fetchone()
        if intencao == "luz_cor":
            ok, msg = dispositivos.wled(ip[0] if ip else "", cor=dispositivos.CORES[d["cor"]])
            fala = ya(["Feito.", "Siga."]) + f" Luz {d['cor']}."
        else:
            ok, msg = dispositivos.wled(ip[0] if ip else "", brilho=d["valor"])
            fala = f"Luz a {d['valor']} por cento."
        if not ok:
            return {"resposta": msg, "falado": "Não consegui falar com a fita LED. " + ("Ainda não a configuraste." if not ip else "Vê se está ligada.")}
        return {"resposta": fala, "falado": fala}

    if intencao == "tomada":
        import dispositivos
        wl = con.execute("SELECT valor FROM config WHERE chave = 'wled_ip'").fetchone()
        if wl:  # com a fita WLED, "liga a luz" vai para ela
            ok, msg = dispositivos.wled(wl[0], ligar=d["estado"] == "ligar")
            if ok:
                return {"resposta": "Luz " + ("ligada." if d["estado"] == "ligar" else "desligada."),
                        "falado": ya(["Feito.", "Siga."]) if d["estado"] == "ligar" else "Apagada."}
        ip = con.execute("SELECT valor FROM config WHERE chave = 'tomada_ip'").fetchone()
        ok, msg = dispositivos.tomada(ip[0] if ip else "", d["estado"])
        if not ok:
            return {"resposta": msg, "falado": "Não consegui falar com a tomada. " + ("Ainda não a configuraste." if not ip else "Vê se está ligada.")}
        return {"resposta": "Luz " + ("ligada." if d["estado"] == "ligar" else "desligada."),
                "falado": ya(["Feito.", "Siga.", "Na boa."]) if d["estado"] == "ligar" else ya(["Apagada.", "Feito, luz apagada."])}

    if intencao in ("alarme", "alarme_sem", "alarme_ver"):
        import alarmes
        from datetime import datetime
        if intencao == "alarme_sem":
            n = alarmes.sem_alarme_no_dia(con, d["data"])
            if not n:
                return {"resposta": f"Não tinhas alarme para {fmt_data(d['data'], hoje)}.", "falado": f"Já não tinhas alarme para {dia_falado(d['data'], hoje)}."}
            return {"resposta": f"Sem alarme {fmt_data(d['data'], hoje)}.", "mudou": True,
                    "falado": ya(["Feito, ", "Na boa, "]) + f"{dia_falado(d['data'], hoje)} não te acordo. Dorme bem."}
        if intencao == "alarme_ver":
            p = alarmes.proximo(con)
            if not p:
                return {"resposta": "Não tens alarmes. Diz por exemplo: acorda-me amanhã às 7h.",
                        "falado": "Não tens alarme nenhum. Diz acorda-me amanhã às 7, por exemplo."}
            dp = date.fromisoformat(p["data"])
            return {"resposta": f"Próximo alarme: {fmt_data(dp, hoje)} às {p['hora']}" + (f" ({p['nome']})" if p["nome"] else "") + ".",
                    "falado": f"O próximo alarme é {dia_falado(dp, hoje)} às {hora_falada(p['hora'])}."}
        hora = d["hora"]
        if d["dias"]:
            alarmes.criar(con, hora, d["dias"], None, d["nome"])
            quais = {"0123456": "todos os dias", "01234": "de segunda a sexta", "56": "aos fins de semana"}[d["dias"]]
            return {"resposta": f"Alarme às {hora}, {quais}.", "mudou": True,
                    "falado": f"Siga, alarme às {hora_falada(hora)}, {quais}."}
        dia = d["data"]
        if not dia:  # sem dia: hoje se ainda nao passou, senao amanha
            dia = hoje if hora > datetime.now().strftime("%H:%M") and hoje == date.today() else hoje + timedelta(days=1)
        alarmes.criar(con, hora, "", dia.isoformat(), d["nome"])
        normais = [a for a in con.execute("SELECT * FROM alarmes WHERE ativo = 1 AND data IS NULL AND instr(dias, ?) > 0", (str(dia.weekday()),))]
        extra = " Nesse dia substitui o alarme normal." if normais else ""
        return {"resposta": f"Alarme para {fmt_data(dia, hoje)} às {hora}.{extra}", "mudou": True,
                "falado": ya(["Feito.", "Tá combinado.", "Siga."]) + f" Acordo-te {dia_falado(dia, hoje)} às {hora_falada(hora)}." +
                          (" Boa viagem!" if d["nome"] == "Viagem" else "")}

    return AJUDA


# ---------- estilos de personalidade ----------

MORDOMO = [  # (o que diria, como diz um mordomo)
    ("Ya, então. ", "Muito bem, senhor. "), ("Ora bem. ", "Muito bem, senhor. "), ("Bora lá. ", "Com certeza, senhor. "),
    ("Siga.", "Certamente, senhor."), ("Feito.", "Está feito, senhor."), ("Tá marcado.", "Fica marcado, senhor."),
    ("Tá combinado.", "Combinado, senhor."), ("Na boa, ", "Com certeza, "), ("Na boa.", "Com todo o gosto, senhor."),
    ("Tranquilo, ", "Muito bem, "), ("Ya?", "Sim, senhor?"), ("Diz lá.", "Às suas ordens."), ("Diz.", "Sim, senhor?"),
    ("Bora rever isso hoje.", "Sugiro que reveja a matéria hoje, senhor."), ("Está mesmo aí, bora rever.", "Está próximo, senhor. Convém rever."),
    ("Hmm, não apanhei essa.", "Peço desculpa, senhor, não percebi."), ("Modo estudo ligado.", "Modo estudo ativado, senhor."),
    ("Eu não te interrompo, força.", "Não o vou interromper."), ("Força nisso!", "Boa sorte, senhor."),
    ("Ei, ", "Senhor, "), ("De nada!", "Sempre às ordens, senhor."), ("Sempre que precisares.", "Sempre às ordens, senhor."),
    ("Dorme bem.", "Durma bem, senhor."), ("Boa viagem!", "Faça boa viagem, senhor."), ("despacha isso", "convém tratar disso"),
    ("Bora, hora de acordar.", "Lamento incomodar, senhor, mas são horas de acordar."), ("Está na hora de ir para a cama.", "Senhor, são horas de recolher."),
    ("Apagada.", "Luz apagada, senhor."), ("Ao teu dispor.", "Ao seu dispor, senhor."), ("Estou aqui.", "Às suas ordens, senhor."),
    ("Ok, deixo de ouvir. Quando precisares, toca no botão em cima.", "Muito bem, senhor. Fico em silêncio até me chamar pelo botão."),
    ("Até já.", "Com licença, senhor."), ("Fui.", "Com licença, senhor."), ("Bora, próxima.", "A seguinte, senhor."), ("Pausa.", "Em pausa, senhor."),
]


def estilizar(texto, estilo):
    """'mordomo': fala como o Jarvis dos filmes. 'descontraido' (normal): fica igual."""
    if estilo != "mordomo" or not texto:
        return texto
    for a, b in MORDOMO:
        texto = texto.replace(a, b)
    texto = re.sub(r"^(Bom dia|Boa tarde|Boa noite)(, [^!]+)?!", lambda m: f"{m[1]}, senhor.", texto)
    return texto

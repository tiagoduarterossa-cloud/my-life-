"""
O cerebro do Claude para o assistente da central.

So entra quando as regras (assistente.py) nao percebem a pergunta: "porque e que o ceu e azul?",
"explica-me equacoes", "e na quarta?". Assim o que ja funciona continua gratis e instantaneo.

O Claude pode usar a central atraves da ferramenta `central`, que chama as mesmas acoes do assistente
(o dia, testes, tarefas, eventos, notas, alarmes, mala, luz).

Precisa de:
  - pip install anthropic   (ver instalar_claude.sh)
  - uma chave da API (de um adulto, com limite de gastos), guardada em chave_claude.txt, fora do GitHub
"""

import json
import os
import threading
import time
from datetime import date, datetime
from pathlib import Path

import assistente

CHAVE = Path(__file__).resolve().parent / "chave_claude.txt"

MODELOS = [
    ("claude-haiku-5-5", "Haiku 5.5: o mais rápido e barato (~0,04 cêntimos por pergunta) · recomendado"),
    ("claude-sonnet-5-5", "Sonnet 5.5: equilibrado (~1 cêntimo por pergunta)"),
    ("claude-opus-5-5", "Opus 5.5: o mais inteligente (~2 cêntimos por pergunta)"),
]
MODELO_PADRAO = "claude-haiku-5-5"
# pesquisa na web: "0" desligada, "1" ou "3" pesquisas no maximo por pergunta (cada uma custa 1 centimo)
PESQUISA = [("0", "Pesquisa na web desligada (0 €)"), ("1", "Pesquisa na web: até 1 por pergunta (+1 cêntimo)"),
            ("3", "Pesquisa na web: até 3 por pergunta (até +3 cêntimos)")]
PESQUISA_PADRAO = "1"

SISTEMA = """És o {nome_assistente}, o assistente da central pessoal que um rapaz de 13 anos montou no tablet do quarto. Ele vive em Portugal e anda no 8.º ano.

Como falas:
- Português de Portugal, sempre (tu, estás, telemóvel, autocarro). Nunca português do Brasil.
- As tuas respostas vão ser LIDAS EM VOZ ALTA. Responde em 1 a 3 frases curtas e naturais. Sem listas, sem markdown, sem emojis, sem links.
{estilo}
- Se não souberes ou não tiveres a certeza, diz isso. Não inventes.

Escola:
- Se for um exercício, um TPC ou uma pergunta de teste, ajuda-o a PERCEBER: dá a ideia, uma pista ou o primeiro passo, e pergunta se quer continuar. Não dês só a resposta final pronta a copiar.
- Explicações de matéria: claras e curtas, com um exemplo do dia a dia.

A vida dele:
- Para tudo o que é dele (horário, aulas, testes, tarefas, eventos, notas, alarmes, fazer a mala, ligar a luz), usa a ferramenta `central`. Não inventes horários nem datas.
- Depois de usares a ferramenta, responde com base no que ela devolveu, no teu estilo.

{internet}

Segurança:
- Saúde, perigo, ou algo que o preocupe a sério: dá um conselho simples e diz-lhe para falar com os pais ou outro adulto de confiança.

Agora: {data}, {hora}.{sobre_ele}"""

# precos oficiais da Anthropic em dolares por milhao de tokens: (entrada, saida, leitura de cache)
# fonte: tabela de precos da Anthropic (platform.claude.com/docs/en/about-claude/pricing, versao de 2026-11-03).
# A escrita de cache custa 1,25x a entrada. A central nao usa cache, por isso a coluna da cache quase nunca conta.
# Os modelos que nao estao no menu podem aparecer quando o servidor passa a outro modelo depois de uma recusa.
PRECOS = {
    "claude-opus-5-5": (4.00, 20.00, 0.20), "claude-sonnet-5-5": (2.00, 10.00, 0.10), "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-opus-5": (5.00, 25.00, 0.50), "claude-opus-4-8": (5.00, 25.00, 0.50), "claude-sonnet-5": (2.00, 10.00, 0.20),
}
PRECO_PESQUISA = 10.00 / 1000          # pesquisa na web: 10 $ por cada 1000
TABELAS = """
CREATE TABLE IF NOT EXISTS ia_custos (
    mes TEXT PRIMARY KEY,              -- AAAA-MM
    pedidos INTEGER NOT NULL DEFAULT 0,
    pesquisas INTEGER NOT NULL DEFAULT 0,
    entrada INTEGER NOT NULL DEFAULT 0,
    saida INTEGER NOT NULL DEFAULT 0,
    dolares REAL NOT NULL DEFAULT 0
);
"""
_db = None                 # o servidor liga aqui a base de dados (ia._db = db)


def _custo(mensagens):
    """soma o que a Anthropic disse que gastou (usage) em todas as voltas de um pedido. Devolve (entrada, saida, pesquisas, dolares)."""
    ent = sai = pesq = 0
    usd = 0.0
    for m in mensagens:
        u = getattr(m, "usage", None)
        if not u:
            continue
        p_in, p_out, p_cache = PRECOS.get(getattr(m, "model", ""), PRECOS["claude-opus-5"])   # desconhecido: o mais caro
        i, o = u.input_tokens or 0, u.output_tokens or 0
        cr, cw = getattr(u, "cache_read_input_tokens", 0) or 0, getattr(u, "cache_creation_input_tokens", 0) or 0
        st = getattr(u, "server_tool_use", None)
        n = (getattr(st, "web_search_requests", 0) or 0) if st else 0
        ent += i + cr + cw; sai += o; pesq += n
        usd += (i * p_in + cw * p_in * 1.25 + cr * p_cache + o * p_out) / 1e6 + n * PRECO_PESQUISA
    return ent, sai, pesq, usd


def registar(mensagens, pedidos=1):
    if not _db:
        return
    ent, sai, pesq, usd = _custo(mensagens)
    try:
        with _db() as con:
            con.executescript(TABELAS)
            con.execute("""INSERT INTO ia_custos (mes, pedidos, pesquisas, entrada, saida, dolares) VALUES (?,?,?,?,?,?)
                           ON CONFLICT(mes) DO UPDATE SET pedidos = pedidos + excluded.pedidos, pesquisas = pesquisas + excluded.pesquisas,
                           entrada = entrada + excluded.entrada, saida = saida + excluded.saida, dolares = dolares + excluded.dolares""",
                        (date.today().strftime("%Y-%m"), pedidos, pesq, ent, sai, usd))
    except Exception as e:
        print("custos do claude:", e)


def custos(meses=6):
    if not _db:
        return []
    with _db() as con:
        con.executescript(TABELAS)
        return [dict(r) for r in con.execute("SELECT * FROM ia_custos ORDER BY mes DESC LIMIT ?", (meses,))]


def frase_custos():
    cs = custos(2)
    usd = lambda v: f"{v:.2f}".replace(".", ",") + " dólares"
    if not cs or cs[0]["mes"] != date.today().strftime("%Y-%m"):
        return "Este mês ainda não gastaste nada no Claude."
    c = cs[0]
    pl = lambda n, um, varios: f"{n} {um if n == 1 else varios}"
    f = (f"Este mês o Claude custou {usd(c['dolares'])}, em {pl(c['pedidos'], 'pedido', 'pedidos')}"
         + (f" e {pl(c['pesquisas'], 'pesquisa', 'pesquisas')} na web" if c["pesquisas"] else "") + ".")
    if len(cs) > 1:
        f += f" No mês passado foram {usd(cs[1]['dolares'])}."
    return f + " São contas da central com os preços oficiais; a fatura exata está na consola da Anthropic."


def _usadas_hoje():
    """quantos pedidos ao Claude ja houve hoje. Fica na base de dados (config 'ia_uso' = 'AAAA-MM-DD:n'),
    para o limite nao voltar a zero quando a central reinicia (atualizar.sh, falta de luz...)."""
    hoje = date.today()
    if _uso["dia"] != hoje:
        n = 0
        if _db:
            try:
                with _db() as con:
                    r = con.execute("SELECT valor FROM config WHERE chave = 'ia_uso'").fetchone()
                if r and r[0].startswith(hoje.isoformat() + ":"):
                    n = int(r[0].split(":")[1])
            except Exception as e:
                print("limite do claude:", e)
        _uso.update(dia=hoje, n=n)
    return _uso["n"]


def _contar(cfg):
    """conta um pedido no limite diario. Devolve False se o limite ja foi atingido."""
    with _hist_lock:
        if _usadas_hoje() >= int(cfg.get("ia_limite", 100)):
            return False
        _uso["n"] += 1
        if _db:
            try:
                with _db() as con:
                    con.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('ia_uso', ?)", (f"{_uso['dia'].isoformat()}:{_uso['n']}",))
            except Exception as e:
                print("limite do claude:", e)
        return True


INTERNET_LIGADA = """Internet:
- Tens a ferramenta `web_search`. Usa-a para tudo o que muda com o tempo (notícias, resultados, preços, horários, lançamentos, quem é o atual...) e sempre que não tenhas a certeza de um facto. Não respondas a nada disso de memória.
- Diz de onde vem, numa palavra natural ("segundo o Público", "no site da CP"). Se a pesquisa não encontrar, diz que não encontraste; não adivinhes.
- Para o que é dele (horário, testes, alarmes...) usa a `central`, nunca a internet."""
INTERNET_DESLIGADA = """Internet:
- A pesquisa na web está desligada nesta central. Para tudo o que muda com o tempo (notícias, resultados, preços, horários, quem é o atual...) diz que não sabes coisas de hoje porque a pesquisa está desligada nas definições. Não adivinhes.
- Para o que é dele (horário, testes, alarmes...) usa a `central`."""

_hist = []                 # ultimas trocas [(pergunta, resposta, quando)] para perguntas de seguimento
_hist_lock = threading.Lock()
_uso = {"dia": None, "n": 0}


def sdk_instalado():
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def chave_configurada():
    return CHAVE.exists() and CHAVE.read_text().strip().startswith("sk-ant-")


def disponivel():
    return sdk_instalado() and chave_configurada()


def guardar_chave(chave):
    chave = (chave or "").strip()
    if not chave.startswith("sk-ant-") or len(chave) < 30 or any(c.isspace() for c in chave):
        raise ValueError("isso não parece uma chave da API do Claude (começa por sk-ant-)")
    CHAVE.write_text(chave)
    try:
        os.chmod(CHAVE, 0o600)  # so este utilizador a pode ler
    except OSError:
        pass


def apagar_chave():
    CHAVE.unlink(missing_ok=True)
    with _hist_lock:
        _hist.clear()


def estado(cfg):
    usadas = _usadas_hoje()
    return {"sdk": sdk_instalado(), "chave": chave_configurada(), "modelo": cfg.get("ia_modelo", MODELO_PADRAO),
            "modelos": MODELOS, "limite": int(cfg.get("ia_limite", 100)), "usadas_hoje": usadas, "custos": custos(),
            "pesquisa": cfg.get("ia_pesquisa", PESQUISA_PADRAO), "pesquisas": PESQUISA}


def forcar(texto):
    """'claude, ...' ou 'pergunta ao claude ...' vai direto para a IA. Devolve o texto sem o prefixo, ou None."""
    s = assistente.simples(texto)
    for p in ("pergunta ao claude", "pergunta a ia", "claude", "ia,", "ia "):
        if s.startswith(p):
            return texto[len(p):].lstrip(" ,:.-") or None
    return None


def perguntar(texto, db, cfg, privado_ok=True):
    """devolve {resposta, mudou} ou {erro}"""
    if not _contar(cfg):
        return {"erro": f"Hoje já fizeste {cfg.get('ia_limite', 100)} perguntas ao Claude, que é o limite diário. Amanhã há mais."}

    import anthropic
    from anthropic import beta_tool

    nome = cfg.get("nome", "")
    mudou = {"v": False, "privado": False, "comandos": []}

    @beta_tool
    def central(pedido: str) -> str:
        """Faz um pedido à central do quarto, numa frase simples em português, como estes exemplos:
        "o que tenho amanhã", "o que tenho na quinta", "quando é o próximo teste",
        "marca dentista quarta às 15h", "tenho de entregar o trabalho de CN até sexta",
        "toma nota: levar a calculadora", "mostra as notas", "acorda-me sexta às 5 e meia",
        "a que horas é o meu alarme", "amanhã não me acordes", "faz-me a mala para Madrid de sexta a domingo",
        "liga a luz", "desliga a luz", "põe música de estudo", "toca Travis Scott", "pausa a música",
        "próxima música", "volume 30", "que música é esta". Devolve a resposta da central.

        Args:
            pedido: o pedido numa frase curta, parecida com os exemplos.
        """
        import modos
        if modos.bloqueado(pedido):
            return modos.FRASE_AMIGOS + " Não respondas a isto nem digas nada sobre a vida dele."
        if not privado_ok and assistente.entender(pedido)[0] in assistente.PRIVADAS:
            return "Isso é privado (loja, família, segurança) e está trancado com PIN. Diz-lhe para meter o PIN no ecrã."
        if assistente.entender(pedido)[0] in assistente.PRIVADAS:
            mudou["privado"] = True   # esta conversa tocou em coisas privadas: nao fica na memoria para quem nao tem PIN
        with db() as con:
            r = assistente.responder(pedido, con, nome=nome)
        if r is assistente.AJUDA:
            return "A central não percebeu esse pedido. Reformula de forma mais parecida com os exemplos."
        if r.get("mudou"):
            mudou["v"] = True
        mudou["comandos"] += [c for c in r.get("comandos", []) if c.get("acao") != "falar"]
        return json.dumps({"resposta": r.get("resposta"), "itens": r.get("itens", [])}, ensure_ascii=False)

    agora = datetime.now()
    dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    sistema = SISTEMA.format(
        nome_assistente=cfg.get("palavra_ativacao") or "assistente",
        data=f"{dias[agora.weekday()]}, {agora.day}/{agora.month}/{agora.year}", hora=agora.strftime("%H:%M"),
        sobre_ele=f" Ele chama-se {nome}." if nome else "",
        internet=INTERNET_LIGADA if cfg.get("ia_pesquisa", PESQUISA_PADRAO) in ("1", "3") else INTERNET_DESLIGADA,
        estilo=("- Fala como um mordomo britânico elegante, à maneira do Jarvis dos filmes do Homem de Ferro: educado, "
                "seco e com humor subtil. Trata-o por \"senhor\". Português de Portugal na mesma."
                if cfg.get("estilo") == "mordomo" else
                "- Estilo descontraído e jovem, como um amigo mais velho que sabe muito. Um pouco de calão está bem; não exageres."))

    with _hist_lock:  # ultimas 6 trocas dos ultimos 15 minutos, para perceber "e na quarta?"
        _hist[:] = [h for h in _hist if time.time() - h[2] < 15 * 60][-6:]
        mensagens = []
        import modos
        for p, r, _, priv in _hist:
            if (priv and not privado_ok) or modos.amigos():   # no modo amigos o Claude nao se lembra das conversas de antes
                continue
            mensagens += [{"role": "user", "content": p}, {"role": "assistant", "content": r}]
    mensagens.append({"role": "user", "content": texto})

    modelo = cfg.get("ia_modelo", MODELO_PADRAO)
    if modelo not in {m for m, _ in MODELOS}:
        modelo = MODELO_PADRAO
    # pesquisa na web (servidor da Anthropic): para o que e de hoje ou o que ele nao sabe ao certo. Max. 3 por pergunta.
    ferramentas = [central]
    pesq = cfg.get("ia_pesquisa", PESQUISA_PADRAO)
    if pesq in ("1", "3"):
        ferramentas.append({"type": "web_search_20250305" if modelo == "claude-haiku-5-5" else "web_search_20260209", "name": "web_search",
                            "max_uses": int(pesq), "user_location": {"type": "approximate", "country": "PT", "timezone": "Europe/Lisbon"}})
    params = dict(model=modelo, max_tokens=4000, system=sistema, tools=ferramentas, messages=mensagens,
                  max_iterations=6, output_config={"effort": "low"})  # low: respostas curtas e rapidas para voz
    if modelo != "claude-haiku-5-5":
        # se o modelo recusar por seguranca, o servidor tenta outro modelo sozinho
        params.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")

    try:
        client = anthropic.Anthropic(api_key=CHAVE.read_text().strip(), max_retries=1, timeout=40)
        voltas, feitas, orcamento = [], 0, int(pesq) if pesq in ("1", "3") else 0
        runner = client.beta.messages.tool_runner(**params)
        try:
            for m in runner:
                voltas.append(m)
                st = getattr(getattr(m, "usage", None), "server_tool_use", None)
                feitas += (getattr(st, "web_search_requests", 0) or 0) if st else 0
                if orcamento and feitas >= orcamento and params.get("tool_choice") is None:
                    # o max_uses so conta dentro de cada pedido; com varias voltas podia pesquisar mais.
                    # Gasto o orcamento: as proximas voltas ja nao usam ferramentas e respondem com o que ha.
                    # (mudar o tool_choice nao mexe nas ferramentas nem no historico)
                    params["tool_choice"] = {"type": "none"}
                    runner.set_messages_params(lambda p: {**p, "tool_choice": {"type": "none"}})
        finally:
            registar(voltas)          # paga-se mesmo quando corre mal a meio
        if not voltas:
            return {"erro": "O Claude não respondeu nada. Tenta outra vez."}
        final = voltas[-1]
    except anthropic.AuthenticationError:
        return {"erro": "A chave do Claude não é válida. Vê-a nas definições."}
    except anthropic.PermissionDeniedError:
        return {"erro": "A chave não tem permissão para usar este modelo."}
    except anthropic.RateLimitError:
        return {"erro": "Muitas perguntas seguidas. Espera um minuto."}
    except anthropic.BadRequestError as e:
        msg = str(getattr(e, "message", e))
        if "credit" in msg.lower() or "billing" in msg.lower():
            return {"erro": "Acabou o saldo da conta do Claude. Fala com o teu pai."}
        return {"erro": "O Claude não aceitou o pedido."}
    except anthropic.APIConnectionError:
        return {"erro": "Sem ligação à internet para falar com o Claude."}
    except anthropic.APIStatusError:
        return {"erro": "O Claude está com problemas. Tenta daqui a pouco."}

    if final.stop_reason == "refusal":
        return {"erro": "Com isso não te posso ajudar."}
    if final.stop_reason == "pause_turn":
        return {"erro": "A pesquisa demorou demasiado. Pergunta de forma mais curta."}
    resposta = " ".join(b.text for b in final.content if b.type == "text").strip()
    if not resposta:
        return {"erro": "O Claude não respondeu nada. Tenta outra vez."}
    with _hist_lock:
        _hist.append((texto, resposta, time.time(), mudou["privado"]))
    return {"resposta": resposta, "mudou": mudou["v"], "comandos": mudou["comandos"]}


def ver(pergunta, jpeg, cfg):
    """o Claude olha para uma foto da camara do tablet e responde. Devolve {resposta} ou {erro}."""
    import base64
    if not _contar(cfg):
        return {"erro": "Hoje já chegaste ao limite de perguntas ao Claude."}
    import anthropic
    modelo = cfg.get("ia_modelo", MODELO_PADRAO)
    if modelo not in {m for m, _ in MODELOS}:
        modelo = MODELO_PADRAO
    estilo = ("Fala como um mordomo britânico elegante (Jarvis dos filmes), trata-o por \"senhor\"."
              if cfg.get("estilo") == "mordomo" else "Estilo descontraído e jovem.")
    sistema = ("Estás a ver uma foto tirada agora pela câmara do tablet do quarto de um rapaz de 13 anos, em Portugal. "
               "Responde à pergunta dele sobre o que vês, em português de Portugal, em 1 a 3 frases curtas para serem lidas em voz alta. "
               "Sem listas nem markdown. Se a foto estiver escura ou desfocada, diz isso. Não descrevas pessoas em pormenor; foca-te nos objetos. "
               + estilo)
    params = dict(model=modelo, max_tokens=4000, system=sistema, output_config={"effort": "low"}, messages=[{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(jpeg).decode()}},
        {"type": "text", "text": pergunta or "O que é isto?"}]}])
    if modelo != "claude-haiku-5-5":
        params.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    try:
        client = anthropic.Anthropic(api_key=CHAVE.read_text().strip(), max_retries=1, timeout=40)
        r = client.beta.messages.create(**params)
        registar([r])
    except anthropic.AuthenticationError:
        return {"erro": "A chave do Claude não é válida."}
    except anthropic.APIConnectionError:
        return {"erro": "Sem ligação à internet para falar com o Claude."}
    except anthropic.APIStatusError:
        return {"erro": "O Claude está com problemas. Tenta daqui a pouco."}
    if r.stop_reason == "refusal":
        return {"erro": "Com isso não te posso ajudar."}
    txt = " ".join(b.text for b in r.content if b.type == "text").strip()
    return {"resposta": txt} if txt else {"erro": "Não consegui perceber a imagem."}


ESQUEMA_PERGUNTAS = {
    "type": "object",
    "properties": {"perguntas": {"type": "array", "items": {
        "type": "object",
        "properties": {"pergunta": {"type": "string"}, "opcoes": {"type": "array", "items": {"type": "string"}},
                       "certa": {"type": "integer"}, "explicacao": {"type": "string"}},
        "required": ["pergunta", "opcoes", "certa", "explicacao"], "additionalProperties": False}}},
    "required": ["perguntas"], "additionalProperties": False,
}


def gerar_perguntas(cfg, tipo, disciplina="", materia_txt="", n=6):
    """perguntas de escolha multipla. tipo 'revisao' (materia da escola) ou 'jogo' (cultura geral, modo amigos).
    Devolve {perguntas: [{pergunta, opcoes[4], certa, explicacao}]} ou {erro}"""
    if not disponivel():
        return {"erro": "Para isto é preciso o Claude ligado (definições do Claude)."}
    if not _contar(cfg):
        return {"erro": "Hoje já chegaste ao limite de perguntas ao Claude."}
    import anthropic
    if tipo == "revisao":
        pedido = (f"Faz {n} perguntas de revisão de {disciplina} para um aluno do 8.º ano em Portugal, sobre esta matéria:\n"
                  f"{materia_txt}\n\nFoca-te no que ele escreveu como dúvida, se houver. Usa a terminologia das escolas portuguesas.")
    else:
        pedido = (f"Faz {n} perguntas de cultura geral divertidas para um grupo de amigos de 13 anos em Portugal "
                  "(desporto, música, ciência, geografia, jogos, internet). Variadas e nem todas fáceis.")
    sistema = ("Escreves perguntas de escolha múltipla em português de Portugal. Cada pergunta tem exatamente 4 opções curtas, "
               "uma só certa ('certa' é o índice 0 a 3, varia a posição), e uma explicação de uma frase. "
               "Pergunta só factos bem estabelecidos de que tens a certeza; nada que mude com o tempo (resultados, recordes recentes, "
               "quem é o atual...). Se a matéria for vaga, fica pelo que é básico e certo.")
    modelo = cfg.get("ia_modelo", MODELO_PADRAO)
    modelo = modelo if modelo in {m for m, _ in MODELOS} else MODELO_PADRAO
    params = dict(model=modelo, max_tokens=6000, system=sistema, output_config={"effort": "low", "format": {"type": "json_schema", "schema": ESQUEMA_PERGUNTAS}},
                  messages=[{"role": "user", "content": pedido}])
    if modelo != "claude-haiku-5-5":
        params.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    try:
        r = anthropic.Anthropic(api_key=CHAVE.read_text().strip(), max_retries=1, timeout=60).beta.messages.create(**params)
        registar([r])
    except anthropic.APIConnectionError:
        return {"erro": "Sem ligação à internet para falar com o Claude."}
    except anthropic.APIStatusError:
        return {"erro": "O Claude está com problemas. Tenta daqui a pouco."}
    if r.stop_reason in ("refusal", "max_tokens"):
        return {"erro": "Não consegui fazer as perguntas. Tenta outra matéria."}
    try:
        d = json.loads(next(b.text for b in r.content if b.type == "text"))
    except (StopIteration, ValueError):
        return {"erro": "As perguntas vieram mal feitas. Tenta outra vez."}
    ok = [q for q in d.get("perguntas", []) if isinstance(q.get("opcoes"), list) and len(q["opcoes"]) == 4
          and isinstance(q.get("certa"), int) and 0 <= q["certa"] <= 3 and q.get("pergunta")]
    return {"perguntas": ok[:n]} if ok else {"erro": "As perguntas vieram mal feitas. Tenta outra vez."}


def resumir(texto, cfg):
    """resume/traduz um texto curto (ex.: titulos de noticias em ingles) para ser dito em voz alta. Devolve texto ou None."""
    if not _contar(cfg):          # os resumos tambem contam para o limite diario
        return None
    try:
        import anthropic
        estilo = "como um mordomo britânico elegante, tratando-o por senhor" if cfg.get("estilo") == "mordomo" else "num tom descontraído e jovem"
        modelo = cfg.get("ia_modelo", MODELO_PADRAO)
        params = dict(model=modelo if modelo in {m for m, _ in MODELOS} else MODELO_PADRAO, max_tokens=3000, output_config={"effort": "low"},
                      system=f"Resume em português de Portugal, {estilo}, em 2 a 4 frases curtas para ler em voz alta. Sem listas nem markdown. Usa SÓ a informação que está no texto: não acrescentes factos, números, nomes nem explicações que lá não estejam. Diz de que fonte vêm as notícias.",
                      messages=[{"role": "user", "content": texto[:4000]}])
        if params["model"] != "claude-haiku-5-5":
            params.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        r = anthropic.Anthropic(api_key=CHAVE.read_text().strip(), max_retries=1, timeout=30).beta.messages.create(**params)
        registar([r])
        if r.stop_reason == "refusal":
            return None
        return " ".join(b.text for b in r.content if b.type == "text").strip() or None
    except Exception as e:
        print("resumir falhou:", e)
        return None

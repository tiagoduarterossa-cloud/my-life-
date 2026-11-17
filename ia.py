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
    ("claude-opus-5-5", "Opus 5.5: o mais inteligente (~1 a 3 cêntimos por pergunta)"),
    ("claude-sonnet-5-5", "Sonnet 5.5: equilibrado (~0,5 a 1 cêntimo por pergunta)"),
    ("claude-haiku-5-5", "Haiku 5.5: o mais rápido e barato (~0,05 cêntimos por pergunta)"),
]
MODELO_PADRAO = "claude-opus-5-5"

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

Segurança:
- Saúde, perigo, ou algo que o preocupe a sério: dá um conselho simples e diz-lhe para falar com os pais ou outro adulto de confiança.

Agora: {data}, {hora}.{sobre_ele}"""

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
    hoje = date.today()
    usadas = _uso["n"] if _uso["dia"] == hoje else 0
    return {"sdk": sdk_instalado(), "chave": chave_configurada(), "modelo": cfg.get("ia_modelo", MODELO_PADRAO),
            "modelos": MODELOS, "limite": int(cfg.get("ia_limite", 100)), "usadas_hoje": usadas}


def forcar(texto):
    """'claude, ...' ou 'pergunta ao claude ...' vai direto para a IA. Devolve o texto sem o prefixo, ou None."""
    s = assistente.simples(texto)
    for p in ("pergunta ao claude", "pergunta a ia", "claude", "ia,", "ia "):
        if s.startswith(p):
            return texto[len(p):].lstrip(" ,:.-") or None
    return None


def perguntar(texto, db, cfg):
    """devolve {resposta, mudou} ou {erro}"""
    hoje = date.today()
    if _uso["dia"] != hoje:
        _uso.update(dia=hoje, n=0)
    limite = int(cfg.get("ia_limite", 100))
    if _uso["n"] >= limite:
        return {"erro": f"Hoje já fizeste {limite} perguntas ao Claude, que é o limite diário. Amanhã há mais."}
    _uso["n"] += 1

    import anthropic
    from anthropic import beta_tool

    nome = cfg.get("nome", "")
    mudou = {"v": False}

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
        with db() as con:
            r = assistente.responder(pedido, con, nome=nome)
        if r is assistente.AJUDA:
            return "A central não percebeu esse pedido. Reformula de forma mais parecida com os exemplos."
        if r.get("mudou"):
            mudou["v"] = True
        return json.dumps({"resposta": r.get("resposta"), "itens": r.get("itens", [])}, ensure_ascii=False)

    agora = datetime.now()
    dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    sistema = SISTEMA.format(
        nome_assistente=cfg.get("palavra_ativacao") or "assistente",
        data=f"{dias[agora.weekday()]}, {agora.day}/{agora.month}/{agora.year}", hora=agora.strftime("%H:%M"),
        sobre_ele=f" Ele chama-se {nome}." if nome else "",
        estilo=("- Fala como um mordomo britânico elegante, à maneira do Jarvis dos filmes do Homem de Ferro: educado, "
                "seco e com humor subtil. Trata-o por \"senhor\". Português de Portugal na mesma."
                if cfg.get("estilo") == "mordomo" else
                "- Estilo descontraído e jovem, como um amigo mais velho que sabe muito. Um pouco de calão está bem; não exageres."))

    with _hist_lock:  # ultimas 6 trocas dos ultimos 15 minutos, para perceber "e na quarta?"
        _hist[:] = [h for h in _hist if time.time() - h[2] < 15 * 60][-6:]
        mensagens = []
        for p, r, _ in _hist:
            mensagens += [{"role": "user", "content": p}, {"role": "assistant", "content": r}]
    mensagens.append({"role": "user", "content": texto})

    modelo = cfg.get("ia_modelo", MODELO_PADRAO)
    if modelo not in {m for m, _ in MODELOS}:
        modelo = MODELO_PADRAO
    params = dict(model=modelo, max_tokens=4000, system=sistema, tools=[central], messages=mensagens,
                  max_iterations=5, output_config={"effort": "low"})  # low: respostas curtas e rapidas para voz
    if modelo != "claude-haiku-5-5":
        # se o modelo recusar por seguranca, o servidor tenta outro modelo sozinho
        params.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")

    try:
        client = anthropic.Anthropic(api_key=CHAVE.read_text().strip(), max_retries=1, timeout=40)
        final = client.beta.messages.tool_runner(**params).until_done()
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
    resposta = " ".join(b.text for b in final.content if b.type == "text").strip()
    if not resposta:
        return {"erro": "O Claude não respondeu nada. Tenta outra vez."}
    with _hist_lock:
        _hist.append((texto, resposta, time.time()))
    return {"resposta": resposta, "mudou": mudou["v"]}

"""
Rascunhos para as redes sociais da loja, feitos em lote (Batch API da Anthropic: metade do preco, prontos em ate 24 h).

- Ao domingo a noite (21h-23h), se a loja estiver ligada e o Claude tambem, a central pede de uma vez:
  ideias de videos curtos com guiao, legendas para publicacoes e descricoes dos produtos que mais vendem.
  Tambem se pode pedir a qualquer hora no painel da Loja (com um tema opcional).
- De 15 em 15 minutos ve se o lote ja acabou; quando acaba, guarda os textos e avisa no ecra.
- Sao RASCUNHOS: ele le, corrige e publica. A central nunca publica nada sozinha.
- O lote nao aceita "fallbacks" (nem streaming): se o modelo recusar um pedido, esse rascunho fica sem texto.
- Interruptor: config 'conteudos' = '0' desliga o pedido automatico de domingo.
"""

import threading
import time
from datetime import date, datetime, timedelta

import ia

TABELAS = """
CREATE TABLE IF NOT EXISTS conteudos_lotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'a fazer',     -- a fazer, pronto, falhou
    tema TEXT,
    criado TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    terminado TEXT
);
CREATE TABLE IF NOT EXISTS conteudos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_id INTEGER NOT NULL,
    tipo TEXT NOT NULL,                         -- videos, legendas, descricoes
    texto TEXT NOT NULL,
    criado TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""
TIPOS = {
    "videos": "Ideias de vídeos curtos (TikTok, Reels)",
    "legendas": "Legendas para publicações",
    "descricoes": "Descrições dos produtos",
}
SISTEMA = ("Ajudas um rapaz de 13 anos, em Portugal, a gerir as redes sociais da sua loja online (dropshipping, supervisionada pelos pais). "
           "Escreves rascunhos em português de Portugal, prontos a usar mas para ele rever. Nada de promessas falsas sobre os produtos, "
           "nem de alegações de saúde, nem de preços inventados; cumpre as regras do TikTok e do Instagram para publicidade. "
           "Formata em Markdown simples, com um título curto por cada ideia.")


def _pedidos(produtos, tema):
    base = (f"Produtos que mais vendem: {', '.join(produtos)}." if produtos else "Ainda não há vendas registadas: faz ideias gerais para uma loja online.")
    extra = f" Tema desta semana: {tema}." if tema else ""
    return {
        "videos": base + extra + " Dá 5 ideias de vídeos curtos (15 a 30 segundos), cada uma com: gancho dos primeiros 2 segundos, guião em 3 a 5 passos e a frase final.",
        "legendas": base + extra + " Escreve 5 legendas curtas para publicações, cada uma com uma chamada à ação e 3 a 5 hashtags relevantes.",
        "descricoes": base + extra + " Escreve uma descrição de produto (60 a 100 palavras) para cada um dos produtos, clara e honesta, com 3 pontos fortes.",
    }


def mais_vendidos(con):
    import loja
    try:
        if not loja.configurada():
            return []
        return [n for n, _ in loja.resumo(con, "mes").get("mais_vendidos", [])]
    except Exception as e:
        print("conteudos:", e)
        return []


def pedir(con, cfg, tema=""):
    """manda o lote. Devolve o id do lote na central, ou levanta ValueError com uma frase clara.
    A chamada a Anthropic e feita ANTES de escrever na base de dados (com a rede lenta, nao fica nada bloqueado),
    e o pedido so conta no limite diario se o lote for mesmo criado."""
    if not ia.disponivel():
        raise ValueError("para os rascunhos é preciso o Claude ligado (definições do Claude)")
    if con.execute("SELECT 1 FROM conteudos_lotes WHERE estado = 'a fazer'").fetchone():
        raise ValueError("já há um lote de rascunhos a ser feito; fica pronto em até 24 horas")
    if ia._usadas_hoje() >= int(cfg.get("ia_limite", 100)):
        raise ValueError("hoje já chegaste ao limite diário de pedidos ao Claude")
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    modelo = ia.modelo_(cfg, "conteudos")
    pedidos = _pedidos(mais_vendidos(con), (tema or "").strip()[:120])
    cliente = anthropic.Anthropic(api_key=ia.CHAVE.read_text().strip(), max_retries=1, timeout=60)
    try:
        lote = cliente.messages.batches.create(requests=[
            Request(custom_id=tipo, params=MessageCreateParamsNonStreaming(
                model=modelo, max_tokens=4000, system=SISTEMA, output_config={"effort": "medium"},
                messages=[{"role": "user", "content": texto}]))
            for tipo, texto in pedidos.items()])
    except anthropic.APIConnectionError:
        raise ValueError("sem ligação à Anthropic; tenta mais tarde")
    except anthropic.APIStatusError as e:
        raise ValueError(f"a Anthropic recusou o lote (erro {e.status_code})")
    ia._contar(cfg)
    ia.registar([], pedidos=1, con=con)   # conta o pedido no mes (os tokens entram quando o lote acabar)
    return con.execute("INSERT INTO conteudos_lotes (batch_id, tema) VALUES (?, ?)", (lote.id, tema or None)).lastrowid


def _buscar(cliente, l):
    """vai buscar um lote a Anthropic (so rede, sem escrever). Devolve ('a fazer'|'pronto'|'falhou', [(tipo, mensagem)])"""
    import anthropic
    try:
        b = cliente.messages.batches.retrieve(l["batch_id"])
    except anthropic.NotFoundError:          # ex.: a chave mudou para outra conta: este lote ja nao se consegue ler
        return "falhou", []
    if b.processing_status != "ended":
        velho = datetime.now() - datetime.fromisoformat(l["criado"]) > timedelta(hours=25)
        return ("falhou", []) if velho else ("a fazer", [])
    res = [(r.custom_id, r.result.message) for r in cliente.messages.batches.results(l["batch_id"]) if r.result.type == "succeeded"]
    return ("pronto" if res else "falhou"), res


def verificar(db):
    """ve os lotes por acabar e guarda os que acabaram. Primeiro a rede (sem a base de dados presa), depois a escrita.
    Devolve quantos ficaram prontos."""
    with db() as con:
        pendentes = [dict(r) for r in con.execute("SELECT * FROM conteudos_lotes WHERE estado = 'a fazer'")]
    if not pendentes:
        return 0
    import anthropic
    cliente = anthropic.Anthropic(api_key=ia.CHAVE.read_text().strip(), max_retries=1, timeout=60)
    acabados = []
    for l in pendentes:
        try:
            estado, res = _buscar(cliente, l)
        except Exception as e:                 # um lote com problemas nao trava os outros
            print("conteudos:", l["batch_id"], e)
            continue
        if estado != "a fazer":
            acabados.append((l, estado, res))
    prontos = 0
    with db() as con:
        for l, estado, res in acabados:
            for tipo, m in res:
                texto = "\n\n".join(x.text for x in m.content if x.type == "text").strip()
                if texto and tipo in TIPOS:
                    con.execute("INSERT INTO conteudos (lote_id, tipo, texto) VALUES (?,?,?)", (l["id"], tipo, texto))
            if res:
                ia.registar([m for _, m in res], pedidos=0, fator=0.5, con=con)   # o lote paga metade
            con.execute("UPDATE conteudos_lotes SET estado = ?, terminado = datetime('now','localtime') WHERE id = ?", (estado, l["id"]))
            prontos += estado == "pronto"
    return prontos


def listar(con, lotes=3):
    ls = [dict(r) for r in con.execute("SELECT * FROM conteudos_lotes ORDER BY id DESC LIMIT ?", (lotes,))]
    for l in ls:
        l["rascunhos"] = [dict(r) for r in con.execute("SELECT id, tipo, texto FROM conteudos WHERE lote_id = ? ORDER BY id", (l["id"],))]
    return {"lotes": ls, "tipos": TIPOS}


def vigiar(db, ler_config, avisar):
    """thread: ao domingo a noite pede o lote da semana (uma tentativa por semana); de 15 em 15 minutos ve se os lotes acabaram"""
    tentado = set()      # semanas em que o pedido automatico ja foi tentado (mesmo que tenha falhado): nao insiste a noite toda

    def ciclo():
        time.sleep(180)
        while True:
            try:
                agora = datetime.now()
                semana = (agora.date() - timedelta(days=agora.weekday())).isoformat()
                if agora.weekday() == 6 and 21 <= agora.hour < 23 and semana not in tentado:
                    with db() as con:
                        cfg = ler_config()
                        ja = con.execute("SELECT 1 FROM conteudos_lotes WHERE criado >= ?", (semana,)).fetchone()
                        if not ja and cfg.get("conteudos") != "0" and ia.disponivel() and mais_vendidos(con):
                            tentado.add(semana)
                            pedir(con, cfg)
                if verificar(db):
                    avisar("Os rascunhos da loja para esta semana estão prontos (Iron Man, Loja).")
            except Exception as e:
                print("conteudos:", e)
            time.sleep(900)
    threading.Thread(target=ciclo, daemon=True).start()

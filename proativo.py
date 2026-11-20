"""
Jarvis proativo: fala primeiro, mas pouco e so com dados reais da central.

Regras (por ordem de importancia):
1. Teste daqui a 1 a 5 dias e menos de 60 minutos de estudo dessa disciplina nos ultimos 14 dias.
2. Tarefa por fazer com prazo amanha.
3. Sem treino ha 4 dias ou mais (so se ja tiveres registado treino alguma vez: nao chateia quem nao treina).

Limites, para nao ser chato:
- So entre as 17h00 e as 20h30, com o ecra ligado. No maximo 2 avisos por dia, com 90 minutos entre eles, e nunca o mesmo duas vezes no mesmo dia.
- Nada no modo amigos, durante uma viagem, nem com o interruptor desligado (config 'proativo' = '0').
- No modo estudo o ecra guarda o aviso para o fim (acao 'proativo').
"""

import threading
import time
from datetime import date, datetime, timedelta

import assistente

JANELA = ("17:00", "20:30")
MAX_DIA = 2
INTERVALO_MIN = 90


def sugestoes(con, hoje=None):
    """[(chave, texto)] por ordem de importancia, com o que a central sabe agora"""
    hoje = hoje or date.today()
    out = []
    for t in con.execute("SELECT * FROM testes WHERE data > ? AND data <= ? ORDER BY data",
                         (hoje.isoformat(), (hoje + timedelta(days=5)).isoformat())):
        d = assistente.simples(t["disciplina"])
        estudado = sum(r["minutos"] for r in con.execute("SELECT disciplina, minutos FROM diario WHERE data >= ?",
                                                          ((hoje - timedelta(days=14)).isoformat(),))
                       if assistente.simples(r["disciplina"]) == d)
        if estudado < 60:
            n = (date.fromisoformat(t["data"]) - hoje).days
            quando = "amanhã" if n == 1 else f"daqui a {n} dias"
            out.append((f"teste:{t['id']}",
                        f"Tens teste de {t['disciplina']} {quando} e estudaste {estudado} minutos nas últimas duas semanas. "
                        f"Bora fazer 30 minutos hoje? Diz \"modo estudo\"."))
    amanha = (hoje + timedelta(days=1)).isoformat()
    for t in con.execute("SELECT * FROM tarefas WHERE feita = 0 AND prazo = ?", (amanha,)):
        out.append((f"tarefa:{t['id']}", f"Amanhã é o prazo de: {t['titulo']}."))
    try:
        n = con.execute("SELECT COUNT(*) FROM jarvis_aprendido WHERE estado = 'proposta'").fetchone()[0]
    except Exception:
        n = 0
    if n:
        out.append(("propostas", f"Tenho {n} coisa{'s' if n > 1 else ''} nova{'s' if n > 1 else ''} para aprender contigo. Vê no Iron Man, em Sistemas, Aprendizagem."))
    ult = con.execute("SELECT MAX(data) FROM registo WHERE area = 'desporto'").fetchone()[0]
    if ult:
        dias = (hoje - date.fromisoformat(ult)).days
        if dias >= 4:
            out.append(("treino", f"Não treinas há {dias} dias. Que tal 10 minutos? Diz \"modo treino\"."))
    return out


def frase(sug):
    if not sug:
        return "Por agora está tudo em dia. Não tenho nada para te sugerir."
    return " ".join(t for _, t in sug[:3])


def _feitos(con, hoje):
    r = con.execute("SELECT valor FROM config WHERE chave = 'proativo_feito'").fetchone()
    if r and r[0].startswith(hoje.isoformat() + "|"):
        partes = r[0].split("|")
        return set(p for p in partes[2:] if p), float(partes[1] or 0)
    return set(), 0.0


def _guardar(con, hoje, feitos, ultimo):
    con.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('proativo_feito', ?)",
                ("|".join([hoje.isoformat(), str(ultimo)] + sorted(feitos)),))


def verificar(con, ecra_ativo, agora=None):
    """devolve o texto a dizer agora, ou None. Marca-o como feito."""
    import modos
    import viagem
    agora = agora or datetime.now()
    hoje = agora.date()
    cfg = con.execute("SELECT valor FROM config WHERE chave = 'proativo'").fetchone()
    if cfg and cfg[0] == "0":
        return None
    if not (JANELA[0] <= agora.strftime("%H:%M") <= JANELA[1]) or not ecra_ativo:
        return None
    if modos.amigos() or viagem.em_viagem(con, hoje):
        return None
    feitos, ultimo = _feitos(con, hoje)
    if len(feitos) >= MAX_DIA or agora.timestamp() - ultimo < INTERVALO_MIN * 60:
        return None
    for chave, texto in sugestoes(con, hoje):
        if chave not in feitos:
            feitos.add(chave)
            _guardar(con, hoje, feitos, agora.timestamp())
            return texto
    return None


def vigiar(db, ecra_ativo, por_na_fila):
    """thread: de 10 em 10 minutos ve se ha alguma coisa importante a dizer"""
    def ciclo():
        time.sleep(120)
        while True:
            try:
                with db() as con:
                    t = verificar(con, ecra_ativo())
                if t:
                    por_na_fila([{"acao": "proativo", "texto": t}])
            except Exception as e:
                print("proativo:", e)
            time.sleep(600)
    threading.Thread(target=ciclo, daemon=True).start()

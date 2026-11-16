"""
Rotinas da central: QUANDO acontece uma coisa -> (SE uma condicao) -> faz estas ACOES.

Camada 1, ACOES: cada coisa que a central sabe fazer tem um nome (ver ACOES em baixo).
  Algumas correm no servidor (ex.: criar tarefa), outras no ecra (ex.: cronometro, mudar cor).
  O assistente com regras usa-as hoje; o Claude pode usar as mesmas amanha.
Camada 2, ROTINAS: guardadas na base de dados, ligam-se e desligam-se na central.
Camada 3, DISPOSITIVOS (tomada, luzes, coluna): entram como novas acoes quando houver aparelhos.

Gatilhos (quando):  {"tipo": "hora", "hora": "22:00", "dias": "0123456"}
                    {"tipo": "alarme_parado"}
                    {"tipo": "voz", "frases": ["modo estudo", "vou estudar"]}
                    {"tipo": "manual"}
Condicoes (se):     "", "teste_amanha", "dia_de_aulas", "fim_de_semana"
"""

import json
import threading
import time
from datetime import date, datetime, timedelta

import alarmes
import assistente

TABELAS = """
CREATE TABLE IF NOT EXISTS rotinas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    ativa INTEGER NOT NULL DEFAULT 1,
    quando TEXT NOT NULL,       -- JSON com o gatilho
    se TEXT NOT NULL DEFAULT '',
    acoes TEXT NOT NULL         -- JSON: lista de {"acao": ..., ...}
);
"""

# ---------- camada 1: acoes ----------
# "onde": servidor = faz-se aqui; ecra = manda-se para a pagina da central fazer
ACOES = {
    "falar":          {"onde": "ecra",     "descricao": "Diz um texto em voz alta"},
    "aviso":          {"onde": "ecra",     "descricao": "Mostra uma mensagem no ecrã"},
    "cronometro":     {"onde": "ecra",     "descricao": "Começa o cronómetro de estudo"},
    "nao_incomodar":  {"onde": "ecra",     "descricao": "Deixa de ouvir o 'Rosserini' durante uns minutos"},
    "ecra":           {"onde": "ecra",     "descricao": "Põe o ecrã em modo noite ou normal"},
    "abrir":          {"onde": "ecra",     "descricao": "Abre um separador da central"},
    "cor":            {"onde": "ecra",     "descricao": "Muda a cor do ecrã principal"},
    "tarefa":         {"onde": "servidor", "descricao": "Cria uma tarefa"},
    "som":            {"onde": "servidor", "descricao": "Toca o som do alarme uma vez"},
}

PADRAO = [
    {"nome": "Bom dia", "quando": {"tipo": "alarme_parado"}, "se": "",
     "acoes": [{"acao": "ecra", "modo": "normal"},
               {"acao": "falar", "texto": "Bom dia{virgula_nome}! {resumo_hoje} {tempo_hoje}"}]},
    {"nome": "Modo estudo", "quando": {"tipo": "voz", "frases": ["modo estudo", "vou estudar", "bora estudar", "hora de estudar"]}, "se": "",
     "acoes": [{"acao": "cronometro", "minutos": 45, "disciplina": "auto"},
               {"acao": "abrir", "separador": "estudo"},
               {"acao": "falar", "texto": "Modo estudo ligado. 45 minutos de {disciplina}. Eu não te interrompo, força."},
               {"acao": "nao_incomodar", "minutos": 45}]},
    {"nome": "Hora de dormir", "quando": {"tipo": "hora", "hora": "22:00", "dias": "0123456"}, "se": "",
     "acoes": [{"acao": "falar", "texto": "Está na hora de ir para a cama. {resumo_amanha_curto} {alarme_amanha} Boa noite."},
               {"acao": "ecra", "modo": "noite"}]},
    {"nome": "Véspera de teste", "quando": {"tipo": "hora", "hora": "18:00", "dias": "0123456"}, "se": "teste_amanha",
     "acoes": [{"acao": "falar", "texto": "Ei, amanhã tens teste de {teste_amanha}. Quando estiveres pronto, diz modo estudo."},
               {"acao": "aviso", "texto": "Amanhã: teste de {teste_amanha}"}]},
]


def criar_padrao(con):
    if con.execute("SELECT COUNT(*) FROM rotinas").fetchone()[0] == 0:
        for r in PADRAO:
            con.execute("INSERT INTO rotinas (nome, quando, se, acoes) VALUES (?,?,?,?)",
                        (r["nome"], json.dumps(r["quando"], ensure_ascii=False), r["se"], json.dumps(r["acoes"], ensure_ascii=False)))


def listar(con):
    out = []
    for r in con.execute("SELECT * FROM rotinas ORDER BY id"):
        d = dict(r); d["quando"] = json.loads(d["quando"]); d["acoes"] = json.loads(d["acoes"])
        out.append(d)
    return out


# ---------- condicoes e textos ----------

def _testes_em(con, dia):
    return [t["disciplina"] for t in con.execute("SELECT disciplina FROM testes WHERE data = ?", (dia.isoformat(),))]


def condicao_ok(con, se, hoje=None):
    hoje = hoje or date.today()
    if se == "teste_amanha":
        return bool(_testes_em(con, hoje + timedelta(days=1)))
    if se == "dia_de_aulas":
        return bool(con.execute("SELECT 1 FROM horario WHERE dia = ? AND area = 'escola'", (hoje.weekday(),)).fetchone())
    if se == "fim_de_semana":
        return hoje.weekday() >= 5
    return True


def _proxima_disciplina(con, hoje):
    # depois do meio-dia, o teste de hoje ja passou: conta o proximo
    op = ">=" if datetime.now().hour < 12 else ">"
    t = con.execute(f"SELECT disciplina FROM testes WHERE data {op} ? ORDER BY data LIMIT 1", (hoje.isoformat(),)).fetchone()
    return t["disciplina"] if t else None


def preencher(texto, con, nome="", tempo_hoje=""):
    """troca {resumo_hoje}, {alarme_amanha}... pelos valores de agora"""
    hoje = date.today(); amanha = hoje + timedelta(days=1)
    valores = {"nome": nome, "virgula_nome": f", {nome}" if nome else "", "hora": assistente.hora_falada(datetime.now().strftime("%H:%M"))}
    if "{tempo_hoje}" in texto:  # so vai a internet se o texto precisar
        valores["tempo_hoje"] = (tempo_hoje() if callable(tempo_hoje) else tempo_hoje) or ""
    if "{resumo_hoje}" in texto:
        valores["resumo_hoje"] = _sem_abertura(assistente.responder("o que tenho hoje", con, hoje)["falado"])
    if "{resumo_amanha}" in texto or "{resumo_amanha_curto}" in texto:
        r = _sem_abertura(assistente.responder("o que tenho amanhã", con, hoje)["falado"])
        valores["resumo_amanha"] = r
        testes = _testes_em(con, amanha)
        valores["resumo_amanha_curto"] = (f"Amanhã tens teste de {assistente.lista_falada(testes)}." if testes
                                          else ("Amanhã tens aulas." if condicao_ok(con, "dia_de_aulas", amanha) else "Amanhã não tens aulas."))
    if "{alarme_amanha}" in texto:
        a = alarmes.alarmes_do_dia(con, amanha)
        valores["alarme_amanha"] = f"O alarme toca às {assistente.hora_falada(a[0]['hora'])}." if a else "Amanhã não tens alarme."
    if "{teste_amanha}" in texto:
        valores["teste_amanha"] = assistente.lista_falada(_testes_em(con, amanha)) or "nada"
    if "{disciplina}" in texto:
        valores["disciplina"] = _proxima_disciplina(con, hoje) or "estudo"
    for k, v in valores.items():
        texto = texto.replace("{" + k + "}", v)
    return " ".join(texto.split())


def _sem_abertura(t):
    """tira o 'Bora la.' / 'Ora bem.' do inicio, que numa rotina fica a mais"""
    for ab in ("Ya, então. ", "Ora bem. ", "Bora lá. "):
        if t.startswith(ab):
            return t[len(ab):]
    return t


# ---------- executar ----------

_fila = []          # comandos para o ecra: {"id", "t", ...}
_fila_lock = threading.Lock()
_ultimo_id = 0
_ecra_visto = 0.0   # a ultima vez que a pagina perguntou por comandos


def ecra_ativo():
    return time.time() - _ecra_visto < 15


def comandos_para_ecra(depois):
    global _ecra_visto
    _ecra_visto = time.time()
    with _fila_lock:
        limite = time.time() - 120
        _fila[:] = [c for c in _fila if c["t"] > limite]
        return {"ultimo": _ultimo_id, "comandos": [c for c in _fila if c["id"] > depois]}


def _por_na_fila(cmds):
    global _ultimo_id
    with _fila_lock:
        for c in cmds:
            _ultimo_id += 1
            _fila.append(dict(c, id=_ultimo_id, t=time.time()))


def executar(con, rotina, nome="", tempo_hoje="", falar_servidor=None, para_ecra=True):
    """corre as acoes de uma rotina. Devolve os comandos que a pagina tem de fazer.
    para_ecra=False: quem chamou nao e a pagina (ex.: as 22h), por isso os comandos vao para a fila
    e, se o ecra estiver desligado, o servidor fala sozinho pelo tablet."""
    hoje = date.today()
    cmds = []
    for a in rotina["acoes"]:
        a = dict(a)
        for k in ("texto",):
            if k in a:
                a[k] = preencher(a[k], con, nome, tempo_hoje)
        if a.get("acao") == "cronometro" and a.get("disciplina") == "auto":
            a["disciplina"] = _proxima_disciplina(con, hoje) or "Estudo"
        if a["acao"] == "tarefa":
            con.execute("INSERT INTO tarefas (titulo, area, prioridade) VALUES (?, 'outro', 2)", (a.get("titulo", "Tarefa")[:200],))
        elif a["acao"] == "som":
            alarmes.tocar_ficheiro(alarmes.SOM)
        elif a["acao"] in ACOES:
            cmds.append(a)
    if not para_ecra:
        if ecra_ativo():
            _por_na_fila(cmds)
        elif falar_servidor:  # ecra apagado: pelo menos fala
            for c in cmds:
                if c["acao"] == "falar":
                    falar_servidor(c["texto"])
    return cmds


def por_voz(con, texto):
    """se a frase pedir uma rotina ('modo estudo', 'rotina hora de dormir'), devolve-a"""
    s = assistente.simples(texto)
    for r in listar(con):
        if not r["ativa"]:
            continue
        frases = r["quando"].get("frases", []) if r["quando"].get("tipo") == "voz" else []
        frases = frases + [f"rotina {r['nome']}", f"modo {r['nome']}"]
        if any(assistente.simples(f) in s for f in frases):
            return r
    return None


def disparar(db, tipo, **extra):
    """chamado quando acontece um gatilho (ex.: 'alarme_parado')"""
    with db() as con:
        for r in listar(con):
            if r["ativa"] and r["quando"].get("tipo") == tipo and condicao_ok(con, r["se"]):
                executar(con, r, para_ecra=False, **extra)


def vigiar(db, extra):
    """thread: corre as rotinas com hora marcada"""
    feitas = set()

    def ciclo():
        while True:
            try:
                agora = datetime.now(); hm = agora.strftime("%H:%M"); hoje = agora.date()
                with db() as con:
                    for r in listar(con):
                        q = r["quando"]
                        if not r["ativa"] or q.get("tipo") != "hora" or q.get("hora") != hm:
                            continue
                        if str(hoje.weekday()) not in q.get("dias", "0123456"):
                            continue
                        chave = (r["id"], hoje.isoformat(), hm)
                        if chave in feitas:
                            continue
                        feitas.add(chave)
                        if condicao_ok(con, r["se"]):
                            executar(con, r, para_ecra=False, **extra())
            except Exception as e:
                print("rotinas:", e)
            time.sleep(10)
    threading.Thread(target=ciclo, daemon=True).start()

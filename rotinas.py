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
import re
import threading
import time
from datetime import date, datetime, timedelta

import alarmes
import assistente
import dispositivos
import spotify

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
    "modo":           {"onde": "ecra",     "descricao": "Abre um modo do Jarvis (estudo, revisão, amigos, treino)"},
    "tarefa":         {"onde": "servidor", "descricao": "Cria uma tarefa"},
    "som":            {"onde": "servidor", "descricao": "Toca o som do alarme uma vez"},
    "tomada":         {"onde": "servidor", "descricao": "Liga ou desliga a tomada inteligente (luz LED)"},
    "verificar_casa": {"onde": "servidor", "descricao": "Diz se ficou alguma janela aberta ou luz ligada"},
    "musica":         {"onde": "servidor", "descricao": "Spotify: toca uma playlist, pausa ou muda o volume"},
}

SEPARADORES = ["inicio", "tarefas", "estudo", "horario", "tempo", "quarto", "roupa"]
CORES = ["roxo", "azul", "ciano", "verde", "sol", "vermelho", "aurora", "ceu"]
CONDICOES = ["", "teste_amanha", "dia_de_aulas", "fim_de_semana"]


class Invalida(ValueError):
    pass


def validar(d):
    """confirma que uma rotina vinda do ecra faz sentido, e devolve-a limpa"""
    nome = str(d.get("nome") or "").strip()[:40]
    if not nome:
        raise Invalida("a rotina precisa de um nome")
    q = d.get("quando") or {}
    tipo = q.get("tipo")
    if tipo == "hora":
        h = str(q.get("hora") or "")
        if len(h) != 5 or h[2] != ":" or not (h[:2] + h[3:]).isdigit() or int(h[:2]) > 23 or int(h[3:]) > 59:
            raise Invalida("hora inválida")
        dias = "".join(sorted(set(c for c in str(q.get("dias", "")) if c in "0123456")))
        if not dias:
            raise Invalida("escolhe pelo menos um dia")
        quando = {"tipo": "hora", "hora": h, "dias": dias}
    elif tipo == "voz":
        frases = [f.strip()[:40] for f in q.get("frases", []) if str(f).strip()][:6]
        if not frases:
            raise Invalida("escreve pelo menos uma frase para a ativar")
        quando = {"tipo": "voz", "frases": frases}
    elif tipo in ("alarme_parado", "manual"):
        quando = {"tipo": tipo}
    else:
        raise Invalida("escolhe quando a rotina acontece")
    se = d.get("se") or ""
    if se not in CONDICOES:
        raise Invalida("condição inválida")
    acoes = []
    for a in (d.get("acoes") or [])[:12]:
        n = a.get("acao")
        if n not in ACOES:
            raise Invalida(f"ação desconhecida: {n}")
        if n in ("falar", "aviso"):
            t = str(a.get("texto") or "").strip()[:300]
            if not t: raise Invalida("uma das ações 'falar' ou 'aviso' está sem texto")
            acoes.append({"acao": n, "texto": t})
        elif n in ("cronometro", "nao_incomodar"):
            m = int(a.get("minutos") or 0)
            if not 1 <= m <= 180: raise Invalida("os minutos têm de estar entre 1 e 180")
            x = {"acao": n, "minutos": m}
            if n == "cronometro": x["disciplina"] = str(a.get("disciplina") or "auto").strip()[:40] or "auto"
            acoes.append(x)
        elif n == "ecra":
            acoes.append({"acao": n, "modo": "noite" if a.get("modo") == "noite" else "normal"})
        elif n == "abrir":
            if a.get("separador") not in SEPARADORES: raise Invalida("separador inválido")
            acoes.append({"acao": n, "separador": a["separador"]})
        elif n == "cor":
            if a.get("cor") not in CORES: raise Invalida("cor inválida")
            acoes.append({"acao": n, "cor": a["cor"]})
        elif n == "tarefa":
            t = str(a.get("titulo") or "").strip()[:200]
            if not t: raise Invalida("a tarefa precisa de um título")
            acoes.append({"acao": n, "titulo": t})
        elif n == "musica":
            o = a.get("o") if a.get("o") in ("tocar", "pausar", "volume") else "tocar"
            x = {"acao": n, "o": o}
            if o == "tocar": x["pedido"] = str(a.get("pedido") or "").strip()[:100]
            if o == "volume": x["valor"] = max(0, min(100, int(a.get("valor") or 40)))
            acoes.append(x)
        elif n == "tomada":
            e = a.get("estado") if a.get("estado") in ("ligar", "desligar", "alternar") else "ligar"
            acoes.append({"acao": n, "estado": e})
        else:
            acoes.append({"acao": n})
    if not acoes:
        raise Invalida("a rotina precisa de pelo menos uma ação")
    return {"nome": nome, "quando": quando, "se": se, "acoes": acoes}


def guardar(con, d, rid=None):
    r = validar(d)
    valores = (r["nome"], json.dumps(r["quando"], ensure_ascii=False), r["se"], json.dumps(r["acoes"], ensure_ascii=False))
    if rid:
        con.execute("UPDATE rotinas SET nome = ?, quando = ?, se = ?, acoes = ? WHERE id = ?", valores + (rid,))
    else:
        con.execute("INSERT INTO rotinas (nome, quando, se, acoes) VALUES (?,?,?,?)", valores)

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
               {"acao": "verificar_casa"},
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
                if a.get("acao") == "falar":
                    est = con.execute("SELECT valor FROM config WHERE chave = 'estilo'").fetchone()
                    a[k] = assistente.estilizar(a[k], est[0] if est else "")
        if a.get("acao") == "cronometro" and a.get("disciplina") == "auto":
            a["disciplina"] = _proxima_disciplina(con, hoje) or "Estudo"
        if a["acao"] == "tarefa":
            con.execute("INSERT INTO tarefas (titulo, area, prioridade) VALUES (?, 'outro', 2)", (a.get("titulo", "Tarefa")[:200],))
        elif a["acao"] == "som":
            alarmes.tocar_ficheiro(alarmes.SOM)
        elif a["acao"] == "verificar_casa":
            import casa
            cfg = {r["chave"]: r["valor"] for r in con.execute("SELECT * FROM config")}
            e = casa.estado_casa(con, cfg)
            if e["abertos"] or e["luzes_ligadas"]:  # so fala se houver alguma coisa
                cmds.append({"acao": "falar", "texto": "Antes de dormires: " + casa.frase_casa(e)})
        elif a["acao"] == "musica":
            try:
                if a.get("o") == "pausar": spotify.pausar()
                elif a.get("o") == "volume": spotify.volume(a.get("valor", 40))
                else: spotify.tocar(a.get("pedido", ""))
            except spotify.ErroSpotify as e:
                cmds.append({"acao": "aviso", "texto": f"Spotify: {e}"})
        elif a["acao"] == "tomada":
            ip = con.execute("SELECT valor FROM config WHERE chave = 'tomada_ip'").fetchone()
            ok, msg = dispositivos.tomada(ip[0] if ip else "", a.get("estado", "ligar"))
            if not ok:
                cmds.append({"acao": "aviso", "texto": msg})
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
    if re.search(r"\b(sai|sair|acabou|acaba|termina|terminar|desliga|fecha)\b.*\bmodo\b|^para (o )?modo\b", s):
        return None                             # "sai do modo estudo" nao e para ligar a rotina
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
    import modos
    if modos.amigos():          # com amigos no quarto, o "bom dia" nao le a tua agenda
        return
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
                    import viagem, modos
                    if viagem.em_viagem(con, hoje) or modos.amigos():   # fora de casa, ou com amigos no quarto: nada de rotinas   # estas fora: as rotinas com hora ficam em pausa
                        time.sleep(10); continue
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

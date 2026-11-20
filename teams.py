"""
Trabalhos do Teams: a central le as notificacoes do Android (Termux:API, termux-notification-list) e, quando
uma notificacao do Teams fala de um trabalho, cria a tarefa sozinha, com o prazo se a data vier no texto.

- So olha para as notificacoes do Teams (com.microsoft.teams). As outras nao sao lidas nem guardadas.
- Cada notificacao so cria uma tarefa uma vez (tabela teams_vistas).
- Precisa de dar a Termux:API o acesso as notificacoes (Definicoes do Android > Acesso a notificacoes).
- O texto exato das notificacoes do Teams nao foi confirmado: as ultimas 20 ficam em memoria
  (GET /api/teams, com PIN) para se ver o formato real no tablet e afinar as regras.
"""

import hashlib
import json
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from datetime import date

import assistente

PACOTES = ("com.microsoft.teams",)
# so notificacoes de trabalhos atribuidos (a app Tarefas/Assignments do Teams), nao conversas onde alguem diz "trabalho"
INICIO = r"^(nova tarefa|novo trabalho|nova atribuicao|new assignment|assignment|tarefa atribuida|trabalho atribuido|trabalho de casa)\b"
TITULOS = ("assignments", "tarefas", "atribuicoes", "trabalhos")
PRAZO = r"\b(data de conclusao|data limite|due)\b"
TABELAS = """
CREATE TABLE IF NOT EXISTS teams_vistas (
    chave TEXT PRIMARY KEY,
    quando TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""
_ultimas = deque(maxlen=20)        # as ultimas notificacoes do Teams, so em memoria
MESES_EN = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def disponivel():
    return bool(shutil.which("termux-notification-list"))


def ler():
    """as notificacoes do Teams que estao agora no tablet"""
    try:
        out = subprocess.run(["termux-notification-list"], capture_output=True, timeout=20).stdout
        ns = json.loads(out or b"[]")
    except Exception as e:
        print("teams:", e)
        return []
    return [n for n in ns if isinstance(n, dict) and n.get("packageName") in PACOTES]


def _prazo(texto, hoje):
    datas = [d for d in assistente.achar_datas(texto, hoje) if d >= hoje]
    if datas:
        return datas[0]
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)(?:uary|ruary|ch|il|e|y|ust|tember|ober|ember)?\.? (\d{1,2})\b", texto.lower())   # "Due Nov 25"
    if m:
        try:
            d = date(hoje.year, MESES_EN[m[1]], int(m[2]))
            return d if d >= hoje else d.replace(year=d.year + 1)
        except ValueError:
            pass
    return None


def trabalho(n, hoje=None):
    """se a notificacao for de um trabalho, devolve (titulo da tarefa, prazo ou None); senao None"""
    hoje = hoje or date.today()
    titulo, conteudo = str(n.get("title") or "").strip(), str(n.get("content") or "").strip()
    texto = f"{titulo} {conteudo}"
    c, ti = assistente.simples(conteudo), assistente.simples(titulo)
    if not (re.search(INICIO, c) or ti in TITULOS or re.search(PRAZO, c)):
        return None
    nome = re.sub(r"^(nova tarefa|novo trabalho|new assignment|assignment|tarefa|trabalho)\s*[:\-–]\s*", "", conteudo, flags=re.I)
    nome = re.split(r"\s*[·|]\s*|\s+(?:data de conclus[aã]o|due|prazo|entrega at[eé])\b", nome, maxsplit=1, flags=re.I)[0].strip() or conteudo
    nome = nome.strip(" .,;:")[:90]
    turma = f" ({titulo[:30]})" if titulo and assistente.simples(titulo) not in ("teams", "microsoft teams", "tarefas", "assignments") else ""
    return f"Teams: {nome}{turma}", _prazo(texto, hoje)


def _chave(n):
    base = n.get("key") or ""
    return hashlib.sha1(f"{base}|{n.get('title')}|{n.get('content')}".encode()).hexdigest()


def processar(con, ns, hoje=None):
    """cria as tarefas novas. Devolve os titulos criados."""
    criadas = []
    for n in ns:
        if not isinstance(n, dict) or n.get("packageName") not in PACOTES:   # so o Teams, sempre
            continue
        k = _chave(n)
        if con.execute("SELECT 1 FROM teams_vistas WHERE chave = ?", (k,)).fetchone():
            continue
        con.execute("INSERT INTO teams_vistas (chave) VALUES (?)", (k,))
        _ultimas.append({"title": n.get("title"), "content": n.get("content"), "when": n.get("when")})
        t = trabalho(n, hoje)
        if not t:
            continue
        titulo, prazo = t
        if con.execute("SELECT 1 FROM tarefas WHERE titulo = ? AND feita = 0", (titulo,)).fetchone():
            continue
        con.execute("INSERT INTO tarefas (titulo, area, prioridade, prazo) VALUES (?, 'escola', 2, ?)",
                    (titulo, prazo.isoformat() if prazo else None))
        criadas.append(titulo + (f" · até {prazo.strftime('%d/%m')}" if prazo else ""))
    return criadas


def ultimas():
    return list(_ultimas)


def vigiar(db, avisar):
    """thread: de 5 em 5 minutos ve as notificacoes do Teams"""
    if not disponivel():
        return

    def ciclo():
        time.sleep(90)
        while True:
            try:
                ns = ler()
                if ns:
                    with db() as con:
                        for t in processar(con, ns):
                            avisar(f"Novo trabalho do Teams na tua lista: {t}")
            except Exception as e:
                print("teams:", e)
            time.sleep(300)
    threading.Thread(target=ciclo, daemon=True).start()

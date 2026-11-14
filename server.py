#!/usr/bin/env python3
"""
A minha central - servidor pessoal para correr no tablet (Termux).

So usa a biblioteca padrao do Python: nao e preciso instalar nada com pip.
Os dados ficam guardados no ficheiro vida.db (SQLite) ao lado deste ficheiro.

Correr:  python server.py
Abrir:   http://<ip-do-tablet>:8080
"""

import json
import os
import re
import socket
import sqlite3
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("VIDA_DB", BASE / "vida.db"))
STATIC = BASE / "static"
PORT = int(os.environ.get("VIDA_PORT", "8080"))

AREAS = ["escola", "dropshipping", "programar", "encriptar", "musica", "desporto", "outro"]


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS tarefas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                area TEXT NOT NULL,
                prioridade INTEGER NOT NULL DEFAULT 2,  -- 1 alta, 2 media, 3 baixa
                prazo TEXT,                            -- AAAA-MM-DD ou NULL
                feita INTEGER NOT NULL DEFAULT 0,
                criada TEXT NOT NULL DEFAULT (date('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS horario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dia INTEGER NOT NULL,                  -- 0 segunda ... 6 domingo
                inicio TEXT NOT NULL,                  -- HH:MM
                fim TEXT NOT NULL,
                titulo TEXT NOT NULL,
                area TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS registo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,                    -- AAAA-MM-DD
                area TEXT NOT NULL,
                minutos INTEGER NOT NULL,
                nota TEXT
            );
            """
        )


# ---------- validacao ----------

class Erro(Exception):
    pass


def texto(d, campo, obrigatorio=True, maximo=200):
    v = (d.get(campo) or "").strip()
    if obrigatorio and not v:
        raise Erro(f"falta o campo '{campo}'")
    if len(v) > maximo:
        raise Erro(f"'{campo}' e demasiado comprido")
    return v or None


def area(d):
    a = d.get("area")
    if a not in AREAS:
        raise Erro("area invalida")
    return a


def data_ok(v, campo):
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(v).isoformat()
    except ValueError:
        raise Erro(f"'{campo}' tem de ser AAAA-MM-DD")


def hora_ok(v, campo):
    if not v or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
        raise Erro(f"'{campo}' tem de ser HH:MM")
    return v


# ---------- logica ----------

def listar_tarefas():
    with db() as con:
        rows = con.execute(
            """SELECT * FROM tarefas
               ORDER BY feita, prazo IS NULL, prazo, prioridade, id"""
        ).fetchall()
    return [dict(r) for r in rows]


def criar_tarefa(d):
    p = int(d.get("prioridade") or 2)
    if p not in (1, 2, 3):
        raise Erro("prioridade tem de ser 1, 2 ou 3")
    with db() as con:
        con.execute(
            "INSERT INTO tarefas (titulo, area, prioridade, prazo) VALUES (?,?,?,?)",
            (texto(d, "titulo"), area(d), p, data_ok(d.get("prazo"), "prazo")),
        )


def alternar_tarefa(tid):
    with db() as con:
        con.execute("UPDATE tarefas SET feita = 1 - feita WHERE id = ?", (tid,))


def listar_horario():
    with db() as con:
        rows = con.execute("SELECT * FROM horario ORDER BY dia, inicio").fetchall()
    return [dict(r) for r in rows]


def criar_bloco(d):
    dia = int(d.get("dia", -1))
    if dia not in range(7):
        raise Erro("dia invalido")
    ini, fim = hora_ok(d.get("inicio"), "inicio"), hora_ok(d.get("fim"), "fim")
    if fim <= ini:
        raise Erro("o fim tem de ser depois do inicio")
    with db() as con:
        con.execute(
            "INSERT INTO horario (dia, inicio, fim, titulo, area) VALUES (?,?,?,?,?)",
            (dia, ini, fim, texto(d, "titulo"), area(d)),
        )


def listar_registo(dias):
    desde = (date.today() - timedelta(days=dias - 1)).isoformat()
    with db() as con:
        entradas = con.execute(
            "SELECT * FROM registo WHERE data >= ? ORDER BY data DESC, id DESC", (desde,)
        ).fetchall()
        totais = con.execute(
            "SELECT area, SUM(minutos) AS minutos FROM registo WHERE data >= ? GROUP BY area",
            (desde,),
        ).fetchall()
    return {
        "desde": desde,
        "entradas": [dict(r) for r in entradas],
        "totais": {r["area"]: r["minutos"] for r in totais},
    }


def criar_registo(d):
    m = int(d.get("minutos") or 0)
    if not 1 <= m <= 24 * 60:
        raise Erro("minutos tem de estar entre 1 e 1440")
    with db() as con:
        con.execute(
            "INSERT INTO registo (data, area, minutos, nota) VALUES (?,?,?,?)",
            (
                data_ok(d.get("data"), "data") or date.today().isoformat(),
                area(d),
                m,
                texto(d, "nota", obrigatorio=False),
            ),
        )


def apagar(tabela, rid):
    assert tabela in ("tarefas", "horario", "registo")
    with db() as con:
        con.execute(f"DELETE FROM {tabela} WHERE id = ?", (rid,))


# ---------- HTTP ----------

TIPOS = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
         ".png": "image/png", ".svg": "image/svg+xml", ".json": "application/json"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silencio no terminal

    def enviar(self, codigo, corpo, tipo="application/json"):
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo + "; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(dados)

    def corpo_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 10_000:
            raise Erro("pedido demasiado grande")
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            raise Erro("JSON invalido")

    def tratar(self, metodo):
        caminho = self.path.split("?")[0].rstrip("/") or "/"
        query = dict(p.split("=", 1) for p in self.path.partition("?")[2].split("&") if "=" in p)
        try:
            # API
            if caminho == "/api/areas" and metodo == "GET":
                return self.enviar(200, AREAS)
            if caminho == "/api/tarefas":
                if metodo == "GET":
                    return self.enviar(200, listar_tarefas())
                if metodo == "POST":
                    criar_tarefa(self.corpo_json())
                    return self.enviar(201, {"ok": True})
            if caminho == "/api/horario":
                if metodo == "GET":
                    return self.enviar(200, listar_horario())
                if metodo == "POST":
                    criar_bloco(self.corpo_json())
                    return self.enviar(201, {"ok": True})
            if caminho == "/api/registo":
                if metodo == "GET":
                    dias = max(1, min(int(query.get("dias", 7)), 365))
                    return self.enviar(200, listar_registo(dias))
                if metodo == "POST":
                    criar_registo(self.corpo_json())
                    return self.enviar(201, {"ok": True})

            m = re.fullmatch(r"/api/tarefas/(\d+)/alternar", caminho)
            if m and metodo == "POST":
                alternar_tarefa(int(m[1]))
                return self.enviar(200, {"ok": True})
            m = re.fullmatch(r"/api/(tarefas|horario|registo)/(\d+)", caminho)
            if m and metodo == "DELETE":
                apagar(m[1], int(m[2]))
                return self.enviar(200, {"ok": True})

            # ficheiros estaticos
            if metodo == "GET" and not caminho.startswith("/api"):
                nome = "index.html" if caminho == "/" else caminho.lstrip("/")
                f = (STATIC / nome).resolve()
                if STATIC.resolve() in f.parents and f.is_file():
                    return self.enviar(200, f.read_bytes(), TIPOS.get(f.suffix, "application/octet-stream"))

            self.enviar(404, {"erro": "nao encontrado"})
        except (Erro, ValueError) as e:
            self.enviar(400, {"erro": str(e)})

    def do_GET(self):
        self.tratar("GET")

    def do_POST(self):
        self.tratar("POST")

    def do_DELETE(self):
        self.tratar("DELETE")


def ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    init_db()
    print(f"A central esta a correr. Abre no telemovel: http://{ip_local()}:{PORT}")
    print("Para parar: Ctrl+C")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

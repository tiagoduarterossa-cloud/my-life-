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
import urllib.request

import assistente
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urljoin

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("VIDA_DB", BASE / "vida.db"))
STATIC = BASE / "static"
PORT = int(os.environ.get("VIDA_PORT", "8080"))

TIPOS_ROUPA = ["t-shirt", "camisola", "sweat", "casaco", "calcas", "calcoes", "desporto", "calcado", "outro"]
ESTADOS_ROUPA = ["arrumada", "para lavar", "emprestada"]
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
            CREATE TABLE IF NOT EXISTS diario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                disciplina TEXT NOT NULL,
                minutos INTEGER NOT NULL,
                materia TEXT NOT NULL,                 -- o que estudei
                correu INTEGER NOT NULL DEFAULT 3,     -- 1 mal ... 5 muito bem
                duvidas TEXT,                          -- o que ficou por perceber
                registo_id INTEGER                     -- entrada ligada no registo de tempo
            );
            CREATE TABLE IF NOT EXISTS roupa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                tipo TEXT NOT NULL,
                cor TEXT,
                local TEXT,                            -- onde esta guardada
                estado TEXT NOT NULL DEFAULT 'arrumada'
            );
            CREATE TABLE IF NOT EXISTS notas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                texto TEXT NOT NULL,
                criada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                data TEXT NOT NULL,                    -- AAAA-MM-DD
                hora TEXT                              -- HH:MM ou NULL
            );
            CREATE TABLE IF NOT EXISTS testes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                disciplina TEXT NOT NULL,
                data TEXT NOT NULL,
                materia TEXT,
                criado TEXT NOT NULL DEFAULT (date('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS config (
                chave TEXT PRIMARY KEY,
                valor TEXT
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
        colunas = {r["name"] for r in con.execute("PRAGMA table_info(roupa)")}
        for c in ("link", "imagem"):
            if c not in colunas:
                con.execute(f"ALTER TABLE roupa ADD COLUMN {c} TEXT")


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


def url_ok(v, campo):
    v = (v or "").strip()
    if not v:
        return None
    if not re.match(r"https?://", v, re.I) or len(v) > 1000:
        raise Erro(f"'{campo}' tem de ser um link que comece por http:// ou https://")
    return v


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


def listar_diario(dias):
    desde = (date.today() - timedelta(days=dias - 1)).isoformat()
    with db() as con:
        entradas = con.execute(
            "SELECT * FROM diario WHERE data >= ? ORDER BY data DESC, id DESC", (desde,)
        ).fetchall()
        por_disciplina = con.execute(
            """SELECT disciplina, SUM(minutos) AS minutos, ROUND(AVG(correu), 1) AS media
               FROM diario WHERE data >= ? GROUP BY disciplina ORDER BY minutos DESC""",
            (desde,),
        ).fetchall()
    return {"entradas": [dict(r) for r in entradas],
            "disciplinas": [dict(r) for r in por_disciplina]}


def criar_diario(d):
    m = int(d.get("minutos") or 0)
    if not 1 <= m <= 24 * 60:
        raise Erro("minutos tem de estar entre 1 e 1440")
    c = int(d.get("correu") or 3)
    if c not in range(1, 6):
        raise Erro("'correu' tem de ser de 1 a 5")
    dia = data_ok(d.get("data"), "data") or date.today().isoformat()
    disc = texto(d, "disciplina", maximo=60)
    with db() as con:
        # o estudo conta automaticamente no registo de tempo, na area escola
        cur = con.execute(
            "INSERT INTO registo (data, area, minutos, nota) VALUES (?,?,?,?)",
            (dia, "escola", m, f"Estudo: {disc}"),
        )
        con.execute(
            """INSERT INTO diario (data, disciplina, minutos, materia, correu, duvidas, registo_id)
               VALUES (?,?,?,?,?,?,?)""",
            (dia, disc, m, texto(d, "materia", maximo=500), c,
             texto(d, "duvidas", obrigatorio=False, maximo=500), cur.lastrowid),
        )


def listar_roupa():
    with db() as con:
        rows = con.execute("SELECT * FROM roupa ORDER BY tipo, nome").fetchall()
    return [dict(r) for r in rows]


def imagem_do_link(link):
    """Tenta descobrir a foto do produto (og:image) na pagina da loja."""
    try:
        req = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "pt-PT,pt"})
        with urllib.request.urlopen(req, timeout=6) as r:
            html = r.read(600_000).decode("utf-8", "ignore")
    except Exception:
        return None
    for padrao in (r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]*content=["\']([^"\']+)',
                   r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*property=["\']og:image',
                   r'<meta[^>]+name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)'):
        m = re.search(padrao, html, re.I)
        if m:
            img = urljoin(link, m[1].replace("&amp;", "&"))
            return img if img.startswith(("http://", "https://")) else None
    return None


def criar_roupa(d):
    if d.get("tipo") not in TIPOS_ROUPA:
        raise Erro("tipo de roupa invalido")
    link = url_ok(d.get("link"), "link")
    imagem = url_ok(d.get("imagem"), "imagem")
    if link and not imagem:
        imagem = imagem_do_link(link)
    with db() as con:
        con.execute(
            "INSERT INTO roupa (nome, tipo, cor, local, link, imagem) VALUES (?,?,?,?,?,?)",
            (texto(d, "nome", maximo=100), d["tipo"],
             texto(d, "cor", obrigatorio=False, maximo=40),
             texto(d, "local", obrigatorio=False, maximo=100), link, imagem),
        )


def listar_testes():
    desde = (date.today() - timedelta(days=90)).isoformat()
    with db() as con:
        rows = con.execute(
            """SELECT t.*,
                 (SELECT COALESCE(SUM(d.minutos), 0) FROM diario d
                   WHERE lower(trim(d.disciplina)) = lower(trim(t.disciplina))
                     AND d.data >= t.criado AND d.data <= t.data) AS minutos_estudados
               FROM testes t WHERE t.data >= ? ORDER BY t.data""",
            (desde,),
        ).fetchall()
    return [dict(r) for r in rows]


def criar_teste(d):
    dia = data_ok(d.get("data"), "data")
    if not dia:
        raise Erro("falta a data do teste")
    with db() as con:
        con.execute(
            "INSERT INTO testes (disciplina, data, materia) VALUES (?,?,?)",
            (texto(d, "disciplina", maximo=60), dia, texto(d, "materia", obrigatorio=False, maximo=300)),
        )


CHAVES_CONFIG = {"cidade", "lat", "lon", "ecra_inicio", "ecra_fim", "tema", "repouso", "nome"}
TEMAS = {"roxo", "azul", "ciano", "verde", "sol", "vermelho", "aurora", "ceu"}


def ler_config():
    with db() as con:
        return {r["chave"]: r["valor"] for r in con.execute("SELECT * FROM config")}


def gravar_config(d):
    for k, v in d.items():
        if k not in CHAVES_CONFIG:
            raise Erro(f"configuracao desconhecida: {k}")
        v = str(v).strip()[:100]
        if v == "":
            with db() as con:
                con.execute("DELETE FROM config WHERE chave = ?", (k,))
            continue
        if k in ("ecra_inicio", "ecra_fim"):
            hora_ok(v, k)
        if k == "tema" and v not in TEMAS:
            raise Erro("tema desconhecido")
        if k == "repouso" and v not in ("0", "1", "3", "5", "10"):
            raise Erro("repouso invalido")
        if k in ("lat", "lon"):
            float(v)
        with db() as con:
            con.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES (?,?)", (k, v))


def estado_roupa(rid, d):
    if d.get("estado") not in ESTADOS_ROUPA:
        raise Erro("estado invalido")
    with db() as con:
        con.execute("UPDATE roupa SET estado = ? WHERE id = ?", (d["estado"], rid))


def apagar(tabela, rid):
    assert tabela in ("tarefas", "horario", "registo", "diario", "roupa", "testes", "notas", "eventos")
    with db() as con:
        if tabela == "diario":
            row = con.execute("SELECT registo_id FROM diario WHERE id = ?", (rid,)).fetchone()
            if row and row["registo_id"]:
                con.execute("DELETE FROM registo WHERE id = ?", (row["registo_id"],))
        con.execute(f"DELETE FROM {tabela} WHERE id = ?", (rid,))


# ---------- HTTP ----------

TIPOS = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
         ".png": "image/png", ".jpg": "image/jpeg", ".bin": "application/octet-stream", ".svg": "image/svg+xml", ".json": "application/json"}


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

            if caminho == "/api/diario":
                if metodo == "GET":
                    dias = max(1, min(int(query.get("dias", 30)), 365))
                    return self.enviar(200, listar_diario(dias))
                if metodo == "POST":
                    criar_diario(self.corpo_json())
                    return self.enviar(201, {"ok": True})
            if caminho == "/api/roupa":
                if metodo == "GET":
                    return self.enviar(200, {"pecas": listar_roupa(), "tipos": TIPOS_ROUPA,
                                             "estados": ESTADOS_ROUPA})
                if metodo == "POST":
                    criar_roupa(self.corpo_json())
                    return self.enviar(201, {"ok": True})
            if caminho == "/api/assistente" and metodo == "POST":
                texto = (self.corpo_json().get("texto") or "").strip()[:500]
                with db() as con:
                    return self.enviar(200, assistente.responder(texto, con, nome=ler_config().get("nome", "")))
            if caminho == "/api/notas" and metodo == "GET":
                with db() as con:
                    return self.enviar(200, [dict(r) for r in con.execute("SELECT * FROM notas ORDER BY id DESC")])
            if caminho == "/api/eventos":
                if metodo == "GET":
                    desde = (date.today() - timedelta(days=90)).isoformat()
                    with db() as con:
                        rows = con.execute("SELECT * FROM eventos WHERE data >= ? ORDER BY data, hora", (desde,)).fetchall()
                    return self.enviar(200, [dict(r) for r in rows])
                if metodo == "POST":
                    d = self.corpo_json()
                    dia = data_ok(d.get("data"), "data")
                    if not dia:
                        raise Erro("falta a data")
                    with db() as con:
                        con.execute("INSERT INTO eventos (titulo, data, hora) VALUES (?,?,?)",
                                    (texto(d, "titulo"), dia, hora_ok(d["hora"], "hora") if d.get("hora") else None))
                    return self.enviar(201, {"ok": True})
            if caminho == "/api/testes":
                if metodo == "GET":
                    return self.enviar(200, listar_testes())
                if metodo == "POST":
                    criar_teste(self.corpo_json())
                    return self.enviar(201, {"ok": True})
            if caminho == "/api/config":
                if metodo == "GET":
                    return self.enviar(200, ler_config())
                if metodo == "POST":
                    gravar_config(self.corpo_json())
                    return self.enviar(200, {"ok": True})
            m = re.fullmatch(r"/api/roupa/(\d+)/estado", caminho)
            if m and metodo == "POST":
                estado_roupa(int(m[1]), self.corpo_json())
                return self.enviar(200, {"ok": True})

            m = re.fullmatch(r"/api/tarefas/(\d+)/alternar", caminho)
            if m and metodo == "POST":
                alternar_tarefa(int(m[1]))
                return self.enviar(200, {"ok": True})
            m = re.fullmatch(r"/api/(tarefas|horario|registo|diario|roupa|testes|notas|eventos)/(\d+)", caminho)
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

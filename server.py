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

import alarmes
import assistente
import avisos
import backups
import casa
import dispositivos
import familia
import ia
import loja
import modos
import noticias
import pin
import radio
import servicos
import time
import rotinas
import seguranca
import spotify
import viagem
import voz
from datetime import date, datetime, timedelta
from http.cookies import SimpleCookie
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
        con.executescript(alarmes.TABELAS)
        con.executescript(rotinas.TABELAS)
        con.executescript(seguranca.TABELAS)
        con.executescript(casa.TABELAS)
        con.executescript(loja.TABELAS)
        con.executescript(familia.TABELAS)
        con.executescript(pin.TABELAS)
        con.executescript(viagem.TABELAS)
        con.executescript(ia.TABELAS)
        rotinas.criar_padrao(con)
        if not con.execute("SELECT 1 FROM config WHERE chave = 'ia_haiku_feito'").fetchone():
            con.execute("DELETE FROM config WHERE chave = 'ia_modelo' AND valor = 'claude-opus-5-5'")   # o antigo padrao passa a Haiku
            con.execute("INSERT INTO config (chave, valor) VALUES ('ia_haiku_feito', '1')")
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


CHAVES_CONFIG = {"cidade", "lat", "lon", "ecra_inicio", "ecra_fim", "tema", "repouso", "nome",
                 "voz_motor", "voz_neural", "voz_rate", "voz_pitch", "tomada_ip",
                 "ia_modelo", "ia_limite", "ia_pesquisa", "palavra_ativacao", "spotify_client", "estilo", "wled_ip"}
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
        if k == "estilo" and v not in ("descontraido", "mordomo"):
            raise Erro("estilo desconhecido")
        if k == "spotify_client" and not re.fullmatch(r"[0-9a-f]{32}", v):
            raise Erro("o Client ID do Spotify tem 32 letras e numeros (0-9, a-f)")
        if k == "ia_modelo" and v not in {m for m, _ in ia.MODELOS}:
            raise Erro("modelo desconhecido")
        if k == "ia_pesquisa" and v not in {p for p, _ in ia.PESQUISA}:
            raise Erro("opção de pesquisa desconhecida")
        if k == "ia_limite" and not (v.isdigit() and 1 <= int(v) <= 1000):
            raise Erro("o limite tem de ser entre 1 e 1000 perguntas por dia")
        if k == "wled_ip" and not re.fullmatch(r"[\w.\-]{1,60}(:\d{1,5})?", v):
            raise Erro("IP da fita LED invalido (ex: 192.168.1.60)")
        if k == "tomada_ip" and not re.fullmatch(r"[\w.\-]{1,60}(:\d{1,5})?", v):
            raise Erro("IP da tomada invalido (ex: 192.168.1.50)")
        if k == "voz_motor" and v not in ("neural", "tablet"):
            raise Erro("motor de voz invalido")
        if k == "voz_neural" and v not in {n for n, _ in voz.VOZES}:
            raise Erro("voz desconhecida")
        if k in ("voz_rate", "voz_pitch") and not 0.5 <= float(v) <= 2:
            raise Erro("valor de voz invalido")
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
    assert tabela in ("tarefas", "horario", "registo", "diario", "roupa", "testes", "notas", "eventos", "despesas", "familia")
    with db() as con:
        if tabela == "diario":
            row = con.execute("SELECT registo_id FROM diario WHERE id = ?", (rid,)).fetchone()
            if row and row["registo_id"]:
                con.execute("DELETE FROM registo WHERE id = ?", (row["registo_id"],))
        con.execute(f"DELETE FROM {tabela} WHERE id = ?", (rid,))


# ---------- HTTP ----------

TIPOS = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
         ".png": "image/png", ".jpg": "image/jpeg", ".bin": "application/octet-stream", ".wav": "audio/wav", ".svg": "image/svg+xml", ".json": "application/json"}


_servicos_cache = None

# o que e privado: so com PIN (tambem no proprio tablet)
PRIVADOS = ("/api/familia", "/api/viagens", "/api/mapa", "/api/loja", "/api/despesas", "/api/seguranca", "/api/rede", "/api/ia/chave",
            "/api/pin/sessoes", "/api/pin/chave", "/api/pin/remover")
ABERTOS = ("/api/pin/estado", "/api/pin/entrar", "/api/pin/sair")


def alerta_seguranca(texto):
    with db() as con:
        con.execute("INSERT INTO alertas (texto) VALUES (?)", (texto,))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silencio no terminal

    def enviar(self, codigo, corpo, tipo="application/json"):
        if isinstance(corpo, dict) and corpo.get("falado") and self.path.startswith(("/api/assistente", "/api/ia/ver")):
            corpo = dict(corpo, falado=assistente.estilizar(corpo["falado"], ler_config().get("estilo", "descontraido")))
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo + "; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        for k, v in getattr(self, "extra", []):
            self.send_header(k, v)
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
        try:
            seguranca.registar(db, self.client_address[0], self.headers.get("User-Agent", ""))
        except Exception as e:
            print("seguranca:", e)
        caminho = self.path.split("?")[0].rstrip("/") or "/"
        query = dict(p.split("=", 1) for p in self.path.partition("?")[2].split("&") if "=" in p)
        self.extra = []
        try:
            # ----- PIN -----
            local = self.client_address[0] in ("127.0.0.1", "::1")
            ck = SimpleCookie(self.headers.get("Cookie", ""))
            token = (ck["central"].value if "central" in ck else None) or self.headers.get("X-Chave") or query.get("chave")
            ses = None
            if pin.ativo() and token:
                with db() as con:
                    ses = pin.sessao(con, token)
            self.sessao = ses
            if pin.ativo() and not caminho.startswith(ABERTOS):
                e_api = caminho.startswith("/api") or caminho.startswith("/quarto")
                if not ses and ((e_api and not local) or caminho.startswith(PRIVADOS)):
                    return self.enviar(401, {"erro": "precisa do PIN", "pin": True})
            if caminho.startswith("/api/pin"):
                return self.tratar_pin(metodo, caminho, token, ses, local)

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
                corpo = self.corpo_json()
                frase = str(corpo.get("texto") or "").strip()[:500]
                do_telemovel = corpo.get("origem") == "telemovel"   # Atalho da Siri no iPhone
                direto = ia.forcar(frase)  # "Claude, ..." vai direto para a IA
                privado_ok = not pin.ativo() or bool(self.sessao)
                def para_tablet(r):
                    """vindo do iPhone: o telemovel so fala; o que mexe no ecra (modos...) vai para o tablet"""
                    if do_telemovel and r.get("comandos"):
                        rotinas._por_na_fila([c for c in r["comandos"] if c.get("acao") != "falar"])
                        r = {k: v for k, v in r.items() if k != "comandos"}
                    return r
                if direto and ia.disponivel():
                    return self.enviar(200, para_tablet(responder_ia(direto, privado_ok)))
                em_amigos, rotina_pessoal = modos.amigos(), False
                if em_amigos:
                    with db() as con:
                        rotina_pessoal = bool(rotinas.por_voz(con, frase))   # "modo estudo" diria a proxima disciplina
                if em_amigos and (modos.bloqueado(frase) or rotina_pessoal):
                    return self.enviar(200, {"resposta": modos.FRASE_AMIGOS, "falado": modos.FRASE_AMIGOS})
                if not privado_ok and assistente.entender(frase)[0] in assistente.PRIVADAS:
                    return self.enviar(200, {"resposta": "🔒 Isso é privado: mete o PIN.", "falado": "Isso é privado. Mete o PIN no ecrã.",
                                             "bloqueado": True, "privado": True})
                with db() as con:
                    r = rotinas.por_voz(con, frase)
                    if r:  # "modo estudo", "rotina hora de dormir"...
                        cmds = rotinas.executar(con, r, **extras_rotina(sem_falar=True))
                        if do_telemovel:
                            # o iPhone diz o que a rotina fala; o resto (cronometro, ecra...) vai para o tablet
                            falas = " ".join(c["texto"] for c in cmds if c["acao"] == "falar")
                            rotinas._por_na_fila([c for c in cmds if c["acao"] != "falar"])
                            return self.enviar(200, {"resposta": f"Rotina {r['nome']}.", "falado": falas or f"Rotina {r['nome']} a correr."})
                        return self.enviar(200, {"resposta": f"Rotina {r['nome']}.", "falado": "", "comandos": cmds})
                    r = assistente.responder(frase, con, nome=ler_config().get("nome", ""))
                if r is assistente.AJUDA and ia.disponivel():  # as regras nao perceberam: pergunta ao Claude
                    return self.enviar(200, para_tablet(responder_ia(frase, privado_ok)))
                if r.get("resumir") and ia.disponivel():  # noticias em ingles: o Claude resume em portugues
                    resumo = ia.resumir(r["resumir"], ler_config())
                    if resumo:
                        r = dict(r, falado=resumo)
                if do_telemovel and r.get("mudou"):
                    rotinas._por_na_fila([{"acao": "aviso", "texto": f"Do telemóvel: {r.get('resposta', '')}"}])
                return self.enviar(200, para_tablet(dict(r, falado=r.get("falado") or r.get("resposta", ""))))
            # ----- despertador -----
            if caminho == "/api/alarmes":
                with db() as con:
                    if metodo == "GET":
                        return self.enviar(200, alarmes.listar(con))
                    if metodo == "POST":
                        d = self.corpo_json()
                        alarmes.criar(con, hora_ok(d.get("hora"), "hora"), d.get("dias", ""),
                                      data_ok(d.get("data"), "data"), texto(d, "nome", obrigatorio=False, maximo=60))
                        return self.enviar(201, {"ok": True})
            m = re.fullmatch(r"/api/alarmes/(\d+)/(ativo|saltar)", caminho)
            if m and metodo == "POST":
                d = self.corpo_json()
                with db() as con:
                    if m[2] == "ativo":
                        con.execute("UPDATE alarmes SET ativo = ? WHERE id = ?", (1 if d.get("ativo") else 0, int(m[1])))
                    else:
                        alarmes.saltar(con, int(m[1]), data_ok(d.get("data"), "data") or date.today().isoformat())
                return self.enviar(200, {"ok": True})
            m = re.fullmatch(r"/api/alarmes/(\d+)", caminho)
            if m and metodo == "DELETE":
                with db() as con:
                    con.execute("DELETE FROM alarmes_saltar WHERE alarme_id = ?", (int(m[1]),))
                    con.execute("DELETE FROM alarmes WHERE id = ?", (int(m[1]),))
                return self.enviar(200, {"ok": True})
            if caminho == "/api/alarme/estado" and metodo == "GET":
                return self.enviar(200, alarmes.estado())
            if caminho == "/api/alarme/parar" and metodo == "POST":
                estava = alarmes.estado().get("tocando")
                alarmes.parar()
                cmds = []
                if estava:  # gatilho das rotinas "quando paro o alarme" (ex.: Bom dia)
                    with db() as con:
                        for r in rotinas.listar(con):
                            if r["ativa"] and r["quando"].get("tipo") == "alarme_parado" and rotinas.condicao_ok(con, r["se"]):
                                cmds += rotinas.executar(con, r, **extras_rotina(sem_falar=True))
                return self.enviar(200, {"ok": True, "comandos": cmds})
            if caminho == "/api/alarme/adiar" and metodo == "POST":
                return self.enviar(200, {"ate": alarmes.adiar()})
            if caminho == "/api/alarme/testar" and metodo == "POST":
                alarmes.tocar({"nome": "Teste", "hora": datetime.now().strftime("%H:%M")}, bom_dia_falado)
                return self.enviar(200, {"ok": True})

            # ----- rotinas -----
            if caminho == "/api/rotinas":
                with db() as con:
                    if metodo == "GET":
                        return self.enviar(200, {"rotinas": rotinas.listar(con),
                                                 "acoes": {k: v["descricao"] for k, v in rotinas.ACOES.items()}})
                    if metodo == "POST":
                        try: rotinas.guardar(con, self.corpo_json())
                        except rotinas.Invalida as e: raise Erro(str(e))
                        return self.enviar(201, {"ok": True})
            m = re.fullmatch(r"/api/rotinas/(\d+)", caminho)
            if m and metodo in ("PUT", "DELETE"):
                with db() as con:
                    if metodo == "DELETE":
                        con.execute("DELETE FROM rotinas WHERE id = ?", (int(m[1]),))
                    else:
                        try: rotinas.guardar(con, self.corpo_json(), int(m[1]))
                        except rotinas.Invalida as e: raise Erro(str(e))
                return self.enviar(200, {"ok": True})
            if caminho == "/api/tomada" and metodo == "POST":
                ok, msg = dispositivos.tomada(ler_config().get("tomada_ip", ""), self.corpo_json().get("estado", "alternar"))
                return self.enviar(200 if ok else 502, {"ok": ok, "erro": None if ok else msg})
            m = re.fullmatch(r"/api/rotinas/(\d+)/(ativa|hora|executar)", caminho)
            if m and metodo == "POST":
                d = self.corpo_json()
                with db() as con:
                    r = next((x for x in rotinas.listar(con) if x["id"] == int(m[1])), None)
                    if not r:
                        raise Erro("rotina nao encontrada")
                    if m[2] == "ativa":
                        con.execute("UPDATE rotinas SET ativa = ? WHERE id = ?", (1 if d.get("ativa") else 0, r["id"]))
                    elif m[2] == "hora":
                        r["quando"]["hora"] = hora_ok(d.get("hora"), "hora")
                        con.execute("UPDATE rotinas SET quando = ? WHERE id = ?", (json.dumps(r["quando"]), r["id"]))
                    else:
                        return self.enviar(200, {"comandos": rotinas.executar(con, r, **extras_rotina(sem_falar=True))})
                return self.enviar(200, {"ok": True})
            if caminho == "/api/estado" and metodo == "GET":
                depois = int(query.get("depois", 0) or 0)
                return self.enviar(200, {"alarme": alarmes.estado(), **rotinas.comandos_para_ecra(depois)})

            # ----- o que esta a funcionar -----
            if caminho == "/api/servicos" and metodo == "GET":
                global _servicos_cache
                if not _servicos_cache or time.time() - _servicos_cache[0] > 60 or query.get("agora"):
                    _servicos_cache = (time.time(), servicos.verificar())
                return self.enviar(200, _servicos_cache[1])

            # ----- modo viagem (privado: as datas em que a casa fica vazia) -----
            if caminho == "/api/viagens":
                with db() as con:
                    if metodo == "GET":
                        return self.enviar(200, {"atual": viagem.resumo(con), "todas": viagem.listar(con)})
                    if metodo == "POST":
                        d = self.corpo_json()
                        ini, fim = data_ok(d.get("inicio"), "inicio"), data_ok(d.get("fim"), "fim")
                        if not ini or not fim:
                            raise Erro("faltam as datas da viagem")
                        if fim < ini:
                            raise Erro("a volta é antes da ida")
                        moeda = (d.get("moeda") or "").strip().upper() or None
                        if moeda and not re.fullmatch(r"[A-Z]{3}", moeda):
                            raise Erro("a moeda é o código de 3 letras (ex.: THB, USD, GBP)")
                        try:
                            vid = viagem.criar(con, texto(d, "destino", maximo=80), date.fromisoformat(ini), date.fromisoformat(fim), moeda,
                                               url_ok(d.get("link"), "link"), texto(d, "notas", obrigatorio=False, maximo=500),
                                               d.get("pausar_casa", True) is not False)
                        except ValueError as e:
                            raise Erro(str(e))
                        except OSError:
                            raise Erro("sem ligação ao serviço de mapas (Open-Meteo), tenta mais tarde")
                        return self.enviar(201, {"id": vid})
            m = re.fullmatch(r"/api/viagens/(\d+)(?:/(refazer|itens|casa))?", caminho)
            if m:
                vid = int(m[1])
                with db() as con:
                    if not con.execute("SELECT 1 FROM viagens WHERE id = ?", (vid,)).fetchone():
                        raise Erro("viagem não encontrada")
                    if not m[2] and metodo == "DELETE":
                        viagem.apagar(con, vid); return self.enviar(200, {"ok": True})
                    if m[2] == "refazer" and metodo == "POST":
                        viagem.gerar_mala(con, vid); return self.enviar(200, {"ok": True})
                    if m[2] == "casa" and metodo == "POST":
                        con.execute("UPDATE viagens SET pausar_casa = ? WHERE id = ?", (1 if self.corpo_json().get("pausar") else 0, vid))
                        return self.enviar(200, {"ok": True})
                    if m[2] == "itens" and metodo == "POST":
                        d = self.corpo_json()
                        g = d.get("grupo") if d.get("grupo") in viagem.GRUPOS else "outros"
                        con.execute("INSERT INTO viagem_itens (viagem_id, grupo, texto, auto) VALUES (?,?,?,0)", (vid, g, texto(d, "texto", maximo=120)))
                        return self.enviar(201, {"ok": True})
            m = re.fullmatch(r"/api/viagens/itens/(\d+)", caminho)
            if m and metodo in ("POST", "DELETE"):
                with db() as con:
                    if metodo == "DELETE":
                        con.execute("DELETE FROM viagem_itens WHERE id = ?", (int(m[1]),))
                    else:
                        con.execute("UPDATE viagem_itens SET feito = ? WHERE id = ?", (1 if self.corpo_json().get("feito") else 0, int(m[1])))
                return self.enviar(200, {"ok": True})

            # ----- modos do Jarvis -----
            if caminho == "/api/modo":
                if metodo == "GET":
                    return self.enviar(200, {"amigos": modos.amigos()})
                if metodo == "POST":
                    ligar = bool(self.corpo_json().get("amigos"))
                    if not ligar and modos.amigos() and pin.ativo() and not self.sessao:
                        return self.enviar(401, {"erro": "mete o PIN para sair do modo amigos", "pin": True})
                    modos.por_amigos(ligar)
                    return self.enviar(200, {"amigos": ligar})
            if caminho == "/api/revisao" and metodo == "POST":
                d = self.corpo_json()
                if d.get("tipo") == "jogo":
                    return self.enviar(200, ia.gerar_perguntas(ler_config(), "jogo"))
                if modos.amigos():
                    raise Erro(modos.FRASE_AMIGOS)
                disc = texto(d, "disciplina", maximo=60)
                with db() as con:
                    ctx, teste = modos.contexto(con, disc, texto(d, "materia", obrigatorio=False, maximo=300) or "")
                if not ctx:
                    return self.enviar(200, {"precisa_materia": True, "disciplina": disc})
                r = ia.gerar_perguntas(ler_config(), "revisao", disc, ctx)
                return self.enviar(200, dict(r, disciplina=disc, teste=teste and teste["data"]))

            # ----- copias de seguranca do vida.db -----
            if caminho == "/api/backups" and metodo == "GET":
                return self.enviar(200, backups.estado())
            if caminho == "/api/backups" and metodo == "POST":
                return self.enviar(200, backups.fazer(DB_PATH))

            # ----- modo apagao -----
            if caminho == "/api/radio" and metodo == "GET":
                return self.enviar(200, radio.estacoes())
            if caminho == "/api/apagao" and metodo == "GET":
                return self.enviar(200, avisos.estado_energia())
            if caminho == "/api/apagao" and metodo == "POST":   # ligar/desligar a mao
                modo_apagao(bool(self.corpo_json().get("ligado")))
                return self.enviar(200, {"ok": True})

            # ----- familia e mapa -----
            if caminho == "/api/familia":
                with db() as con:
                    if metodo == "GET":
                        ps = familia.listar(con)
                        if query.get("detalhes"):
                            for p in ps:
                                if p.get("lat") is not None:
                                    p["perigos"] = familia.perigos(p["lat"], p["lon"]); p["graus"] = familia.tempo(p["lat"], p["lon"])
                                    p["frase"] = familia.frase_pessoa(p, p["perigos"], p["graus"])
                        return self.enviar(200, ps)
                    if metodo == "POST":
                        d = self.corpo_json()
                        cidade, lat, lon = (str(d.get("cidade") or "").strip()[:60] or None), None, None
                        if cidade:
                            try:
                                g = familia.geocodificar(cidade)
                            except Exception:
                                raise Erro("sem ligação ao serviço de mapas (Open-Meteo), tenta mais tarde")
                            if not g:
                                raise Erro(f"nao encontrei a cidade '{cidade}'")
                            cidade, lat, lon = g
                        aniv = d.get("aniversario") or None
                        if aniv and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", aniv):
                            raise Erro("aniversario invalido")
                        con.execute("INSERT INTO familia (nome, relacao, aniversario, cidade, lat, lon) VALUES (?,?,?,?,?,?)",
                                    (texto(d, "nome", maximo=40), texto(d, "relacao", obrigatorio=False, maximo=20) or "", aniv, cidade, lat, lon))
                        return self.enviar(201, {"ok": True})
            m = re.fullmatch(r"/api/familia/(\d+)/detalhe", caminho)
            if m and metodo == "GET":
                with db() as con:
                    r = familia.detalhe(con, int(m[1]))
                return self.enviar(200, r) if r else self.enviar(404, {"erro": "não encontrei essa pessoa"})
            m = re.fullmatch(r"/api/familia/(\d+)/contacto", caminho)
            if m and metodo == "POST":
                with db() as con:
                    con.execute("UPDATE familia SET ultimo_contacto = ? WHERE id = ?", (date.today().isoformat(), int(m[1])))
                return self.enviar(200, {"ok": True})
            if caminho == "/api/mapa" and metodo == "GET":
                with db() as con:
                    return self.enviar(200, familia.mapa(con, ler_config()))

            # ----- loja (Shopify) -----
            if caminho == "/api/loja/estado" and metodo == "GET":
                return self.enviar(200, {"configurada": loja.configurada(),
                                         "dominio": json.loads(loja.TOKEN.read_text())["dominio"] if loja.configurada() else None})
            if caminho == "/api/loja/ligar" and metodo == "POST":
                d = self.corpo_json()
                try:
                    loja.guardar(str(d.get("dominio", "")), str(d.get("token", "")), float(d.get("taxa_pct") or 2.9), float(d.get("taxa_fixa") or 0.30))
                    nome = loja._gql("{ shop { name } }")["shop"]["name"]
                except loja.ErroLoja as e:
                    loja.apagar(); raise Erro(str(e))
                return self.enviar(200, {"ok": True, "nome": nome})
            if caminho == "/api/loja" and metodo == "DELETE":
                loja.apagar(); return self.enviar(200, {"ok": True})
            if caminho == "/api/loja" and metodo == "GET":
                try:
                    with db() as con:
                        r = loja.resumo(con, query.get("p", "hoje"))
                except loja.ErroLoja as e:
                    raise Erro(str(e))
                return self.enviar(200, dict(r, frase=loja.frase(r)))
            if caminho == "/api/despesas":
                with db() as con:
                    if metodo == "GET":
                        return self.enviar(200, [dict(x) for x in con.execute("SELECT * FROM despesas ORDER BY data DESC, id DESC LIMIT 60")])
                    if metodo == "POST":
                        d = self.corpo_json()
                        v = float(str(d.get("valor", "0")).replace(",", "."))
                        if not 0 < v < 100000:
                            raise Erro("valor invalido")
                        tipo = d.get("tipo") if d.get("tipo") in ("anuncios", "apps", "mensalidade", "outro") else "outro"
                        con.execute("INSERT INTO despesas (data, descricao, valor, tipo) VALUES (?,?,?,?)",
                                    (data_ok(d.get("data"), "data") or date.today().isoformat(), texto(d, "descricao", maximo=80), v, tipo))
                        return self.enviar(201, {"ok": True})

            # ----- casa, rede, desastres -----
            if caminho == "/api/sensor" and metodo in ("GET", "POST"):
                # chamado pelos sensores (ex.: Shelly Door/Window): /api/sensor?nome=janela&estado=aberta
                from urllib.parse import unquote_plus
                with db() as con:
                    nome, estado = casa.registar_sensor(con, unquote_plus(query.get("nome", "")), unquote_plus(query.get("estado", "")))
                return self.enviar(200, {"ok": True, "nome": nome, "estado": estado})
            if caminho == "/api/casa" and metodo == "GET":
                with db() as con:
                    e = casa.estado_casa(con, ler_config())
                return self.enviar(200, dict(e, frase=casa.frase_casa(e)))
            if caminho == "/api/rede" and metodo == "GET":
                return self.enviar(200, casa.verificar_rede())
            if caminho == "/api/desastres" and metodo == "GET":
                r = avisos.resumo(ler_config())
                return self.enviar(200, dict(r, frase=avisos.frase(r)))

            # ----- noticias e seguranca -----
            if caminho == "/api/noticias" and metodo == "GET":
                return self.enviar(200, noticias.obter(query.get("c", "portugal"), int(query.get("n", 6))))
            if caminho == "/api/ciber" and metodo == "GET":
                try: return self.enviar(200, noticias.vulnerabilidades())
                except Exception: raise Erro("nao consegui ler a lista da CISA (sem internet?)")
            if caminho == "/api/seguranca" and metodo == "GET":
                with db() as con:
                    return self.enviar(200, seguranca.resumo(con))
            if caminho == "/api/seguranca/aparelho" and metodo == "POST":
                d = self.corpo_json()
                with db() as con:
                    con.execute("UPDATE aparelhos SET confiavel = ?, nome = COALESCE(?, nome) WHERE ip = ?",
                                (1 if d.get("confiavel") else 0, texto(d, "nome", obrigatorio=False, maximo=40), str(d.get("ip"))))
                return self.enviar(200, {"ok": True})
            if caminho == "/api/seguranca/visto" and metodo == "POST":
                with db() as con:
                    con.execute("UPDATE alertas SET visto = 1")
                return self.enviar(200, {"ok": True})
            if caminho == "/api/seguranca/link" and metodo == "POST":
                return self.enviar(200, seguranca.analisar_link(str(self.corpo_json().get("link", ""))[:2000]))

            # ----- spotify -----
            if caminho == "/api/spotify" and metodo == "GET":
                info = {"ligado": spotify.ligado(), "client_id": bool(ler_config().get("spotify_client"))}
                if info["ligado"]:
                    try: info["agora"] = spotify.a_tocar()
                    except spotify.ErroSpotify as e: info["erro"] = str(e)
                return self.enviar(200, info)
            if caminho == "/api/spotify" and metodo == "DELETE":
                spotify.desligar(); return self.enviar(200, {"ok": True})
            if caminho == "/api/spotify/entrar" and metodo == "GET":
                cid = ler_config().get("spotify_client")
                if not cid:
                    raise Erro("primeiro cola o Client ID do Spotify nas definicoes")
                self.send_response(302)
                self.send_header("Location", spotify.link_entrar(cid, f"http://127.0.0.1:{PORT}/api/spotify/callback"))
                self.end_headers(); return
            if caminho == "/api/spotify/callback" and metodo == "GET":
                from urllib.parse import unquote
                try:
                    if query.get("error"):
                        raise spotify.ErroSpotify("não deste autorização")
                    spotify.terminar_entrada(unquote(query.get("state", "")), unquote(query.get("code", "")))
                    msg = "Spotify ligado! A voltar à central…"
                except spotify.ErroSpotify as e:
                    msg = f"Não consegui ligar o Spotify: {e}"
                pagina = f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="2;url=/"><body style="font:20px system-ui;background:#000;color:#fff;display:grid;place-content:center;height:90vh;text-align:center">{msg}</body>'
                return self.enviar(200, pagina.encode(), "text/html")
            m = re.fullmatch(r"/api/spotify/(tocar|pausar|seguinte|anterior|volume)", caminho)
            if m and metodo == "POST":
                d = self.corpo_json()
                try:
                    if m[1] == "tocar": msg = spotify.tocar(str(d.get("pedido") or "")[:100])
                    elif m[1] == "volume": msg = spotify.volume(d.get("volume", 50))
                    else: msg = getattr(spotify, m[1])()
                except spotify.ErroSpotify as e:
                    raise Erro(str(e))
                return self.enviar(200, {"ok": True, "msg": msg})

            # ----- inteligencia (Claude) -----
            if caminho == "/api/ia/ver" and metodo == "POST":
                # foto da camara (ate ~1,5 MB) + pergunta
                n = int(self.headers.get("Content-Length") or 0)
                if n > 3_000_000:
                    raise Erro("foto demasiado grande")
                d = json.loads(self.rfile.read(n) or b"{}")
                if not ia.disponivel():
                    return self.enviar(200, {"resposta": "Para ver, preciso do Claude ligado (roda dentada > Inteligência).",
                                             "falado": "Para ver, preciso do Claude ligado."})
                import base64
                try:
                    jpeg = base64.b64decode(str(d.get("imagem", "")).split(",")[-1], validate=True)
                except Exception:
                    raise Erro("foto invalida")
                r = ia.ver(str(d.get("pergunta") or "")[:300], jpeg, ler_config())
                fala = r.get("resposta") or r.get("erro")
                return self.enviar(200, {"resposta": fala, "falado": fala})
            if caminho == "/api/wled" and metodo == "POST":
                d = self.corpo_json()
                cor = dispositivos.CORES.get(d.get("cor")) if d.get("cor") else (tuple(d["rgb"]) if d.get("rgb") else None)
                ok, msg = dispositivos.wled(ler_config().get("wled_ip", ""), cor=cor, brilho=d.get("brilho"), ligar=d.get("ligar"))
                return self.enviar(200 if ok else 502, {"ok": ok, "erro": None if ok else msg})
            if caminho == "/api/ia" and metodo == "GET":
                return self.enviar(200, ia.estado(ler_config()))
            if caminho == "/api/ia/chave":
                if metodo == "POST":
                    try: ia.guardar_chave(self.corpo_json().get("chave"))
                    except ValueError as e: raise Erro(str(e))
                    return self.enviar(200, {"ok": True})
                if metodo == "DELETE":
                    ia.apagar_chave(); return self.enviar(200, {"ok": True})

            # ----- voz neural -----
            if caminho == "/api/voz/info" and metodo == "GET":
                return self.enviar(200, {"disponivel": voz.disponivel(), "vozes": voz.VOZES})
            if caminho == "/api/voz/ouvir" and metodo == "GET":
                # transmite o som enquanto e gerado: o browser comeca a tocar logo o primeiro pedaco
                from urllib.parse import unquote_plus
                q = {k: unquote_plus(v) for k, v in query.items()}
                pedacos = voz.transmitir(q.get("t", "")[:600], q.get("v") or "pt-PT-DuarteNeural",
                                         float(q.get("r") or 1.08), float(q.get("p") or 1.05))
                primeiro = next(pedacos, None) if pedacos else None
                if not primeiro:
                    return self.enviar(503, {"erro": "voz neural indisponivel"})
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    self.wfile.write(primeiro); self.wfile.flush()
                    for p in pedacos:
                        self.wfile.write(p); self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass  # o browser desistiu (ex.: falou a voz do tablet)
                return
            if caminho == "/api/voz" and metodo == "POST":
                d = self.corpo_json()
                ficheiro = voz.gerar((d.get("texto") or "")[:600], d.get("voz") or "pt-PT-DuarteNeural",
                                     float(d.get("velocidade") or 1.08), float(d.get("tom") or 1.05))
                if not ficheiro:
                    return self.enviar(503, {"erro": "voz neural indisponivel"})
                return self.enviar(200, ficheiro.read_bytes(), "audio/mpeg")

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
            m = re.fullmatch(r"/api/(tarefas|horario|registo|diario|roupa|testes|notas|eventos|despesas|familia)/(\d+)", caminho)
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
        except (BrokenPipeError, ConnectionResetError):
            pass   # o browser fechou a ligacao antes de receber a resposta
        except Exception as e:
            # um erro inesperado nao deita a ligacao abaixo: fica no terminal e o ecra recebe uma mensagem clara
            import traceback
            traceback.print_exc()
            try:
                self.enviar(500, {"erro": f"erro na central ({e.__class__.__name__}). Vê o Termux para saber mais."})
            except Exception:
                pass

    def cookie(self, token, local):
        idade = "" if local else f"; Max-Age={pin.DURACAO['browser']}"   # no tablet: so ate fechar o browser
        self.extra.append(("Set-Cookie", f"central={token}; Path=/; HttpOnly; SameSite=Lax{idade}"))

    def tratar_pin(self, metodo, caminho, token, ses, local):
        ua = self.headers.get("User-Agent", "")
        aparelho = "Este tablet" if local else ("iPhone" if "iPhone" in ua else "Android" if "Android" in ua else "Mac" if "Macintosh" in ua else "Windows" if "Windows" in ua else "browser")
        try:
            with db() as con:
                if caminho == "/api/pin/estado" and metodo == "GET":
                    return self.enviar(200, {"ativo": pin.ativo(), "sessao": bool(ses), "tipo": ses and ses["tipo"], "local": local})
                if caminho == "/api/pin/entrar" and metodo == "POST":
                    tok = pin.entrar(con, self.corpo_json().get("pin"), self.client_address[0], aparelho, local, alerta_seguranca)
                    self.cookie(tok, local)
                    return self.enviar(200, {"ok": True})
                if caminho == "/api/pin/sair" and metodo == "POST":
                    if ses and ses["tipo"] != "chave":
                        pin.sair(con, token)
                    self.extra.append(("Set-Cookie", "central=; Path=/; Max-Age=0"))
                    return self.enviar(200, {"ok": True})
                if caminho == "/api/pin/definir" and metodo == "POST":
                    d = self.corpo_json()
                    if not pin.ativo() and not local:
                        raise pin.ErroPin("o primeiro PIN só se mete no próprio tablet")
                    if pin.ativo() and not ses:
                        raise pin.ErroPin("mete primeiro o PIN atual")
                    pin.definir(con, d.get("novo"), d.get("atual"))
                    self.cookie(pin.entrar(con, d.get("novo"), self.client_address[0], aparelho, local), local)
                    return self.enviar(200, {"ok": True})
                if caminho == "/api/pin/remover" and metodo == "POST":
                    pin.remover(con, self.corpo_json().get("atual"))
                    self.extra.append(("Set-Cookie", "central=; Path=/; Max-Age=0"))
                    return self.enviar(200, {"ok": True})
                if caminho == "/api/pin/sessoes" and metodo == "GET":
                    return self.enviar(200, pin.listar(con))
                m = re.fullmatch(r"/api/pin/sessoes/([0-9a-f]{12})", caminho)
                if m and metodo == "DELETE":
                    pin.apagar(con, m[1])
                    return self.enviar(200, {"ok": True})
                if caminho == "/api/pin/chave" and metodo == "POST":
                    nome = texto(self.corpo_json(), "nome", maximo=40)
                    return self.enviar(201, {"chave": pin.criar_chave(con, nome)})
        except pin.ErroPin as e:
            return self.enviar(400, {"erro": str(e)})
        return self.enviar(404, {"erro": "nao encontrado"})

    def do_GET(self):
        self.tratar("GET")

    def do_POST(self):
        self.tratar("POST")

    def do_PUT(self):
        self.tratar("PUT")

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


def bom_dia_falado():
    """o que o Rosserini diz enquanto o alarme toca. Se a rotina Bom dia estiver ligada, o resumo fica para
    quando parares o alarme; senao diz logo tudo."""
    agora = assistente.hora_falada(datetime.now().strftime("%H:%M"))
    with db() as con:
        if any(r["ativa"] and r["quando"].get("tipo") == "alarme_parado" for r in rotinas.listar(con)):
            return assistente.estilizar(f"São {agora}. Bora, hora de acordar.", ler_config().get("estilo", ""))
        r = assistente.responder("bom dia", con, nome=ler_config().get("nome", ""))
    return f"São {agora}. " + r.get("falado", "")


def tempo_hoje_falado():
    """'Lá fora estão 12 graus, vai até 18, e vai chover.' (precisa de internet e da cidade escolhida)"""
    cfg = ler_config()
    if not cfg.get("lat"):
        return ""
    try:
        m = assistente._json(f"https://api.open-meteo.com/v1/forecast?latitude={cfg['lat']}&longitude={cfg['lon']}"
                             "&current=temperature_2m&daily=temperature_2m_max,precipitation_probability_max&timezone=auto&forecast_days=1")
        agora, maxima = round(m["current"]["temperature_2m"]), round(m["daily"]["temperature_2m_max"][0])
        chuva = m["daily"]["precipitation_probability_max"][0] or 0
        return f"Lá fora estão {agora} graus, vai até {maxima}" + (", e vai chover, leva casaco." if chuva >= 50 else ".")
    except Exception:
        return ""


def extras_rotina(sem_falar=False):
    """o que as rotinas precisam de saber: o nome, o tempo, e como falar se o ecra estiver apagado"""
    return {"nome": ler_config().get("nome", ""), "tempo_hoje": tempo_hoje_falado,
            **({} if sem_falar else {"falar_servidor": falar_alarme})}


def aviso_familia(texto, dizer):
    """perigo perto da casa de um familiar: e urgente (aparece mesmo no modo estudo), mas com amigos no quarto nao diz quem nem onde"""
    if modos.amigos():
        texto = dizer = "Há um alerta da família. Abre o modo Iron Man para veres."
    if rotinas.ecra_ativo():
        rotinas._por_na_fila([{"acao": "aviso", "texto": texto, "urgente": True}, {"acao": "falar", "texto": dizer}])
    else:
        falar_alarme(dizer)


def responder_ia(frase, privado_ok=True):
    r = ia.perguntar(frase, db, ler_config(), privado_ok=privado_ok)
    if "erro" in r:
        return {"resposta": r["erro"], "falado": r["erro"]}
    out = {"resposta": r["resposta"], "falado": r["resposta"], "mudou": r.get("mudou", False), "ia": True}
    if r.get("comandos"):   # o Claude pediu a central uma coisa que mexe no ecra (ex.: modo amigos): o ecra faz, e depois fala
        out["comandos"] = r["comandos"] + [{"acao": "falar", "texto": r["resposta"]}]
    return out


def modo_apagao(ligado):
    """quando falta a luz: baixa o brilho do ecra (Termux:API) e poe o ecra no modo apagao; quando volta, desfaz"""
    import shutil, subprocess
    if shutil.which("termux-brightness"):
        try:
            subprocess.run(["termux-brightness", "25" if ligado else "auto"], timeout=10)
        except Exception as e:
            print("brilho:", e)
    rotinas._por_na_fila([{"acao": "apagao", "ligado": ligado}])


def falar_alarme(texto):
    """quando o alarme toca: usa a voz neural se estiver escolhida, senao a do tablet"""
    cfg = ler_config()
    if cfg.get("voz_motor", "neural") == "neural":
        f = voz.gerar(texto, cfg.get("voz_neural", "pt-PT-DuarteNeural"),
                      float(cfg.get("voz_rate", 1.08)), float(cfg.get("voz_pitch", 1.05)))
        if f:
            alarmes.tocar_ficheiro(f)
            return len(texto) / 13 + 1.5  # mais ou menos o tempo que demora a dizer
    return alarmes._falar(texto)


if __name__ == "__main__":
    init_db()
    modos.ligar(db)    # le o modo amigos guardado
    ia._db = db        # para a central guardar quanto o Claude gasta por mes
    alarmes.falar = falar_alarme
    alarmes.vigiar(db, bom_dia_falado)
    rotinas.vigiar(db, extras_rotina)
    backups.vigiar(DB_PATH)   # uma copia verificada por dia em backups/ (e no armazenamento do tablet, se houver)
    # perigos perto da casa da familia (incendios, avisos laranja/vermelho, sismos)
    familia.vigiar(db, aviso_familia)
    # encomendas novas: aviso + som de caixa registadora no ecra; se o ecra estiver apagado, fala pelo tablet
    loja.vigiar(lambda texto, dizer: None if modos.amigos() else   # com amigos no quarto, as vendas ficam caladas
                rotinas._por_na_fila([{"acao": "aviso", "texto": texto}, {"acao": "caixa"}, {"acao": "falar", "texto": dizer}])
                if rotinas.ecra_ativo() else falar_alarme(dizer))
    # apagoes e internet: fala pelo tablet (Termux:API) e deixa o aviso no ecra
    avisos.vigiar(db, lambda t: (rotinas._por_na_fila([{"acao": "aviso", "texto": t}]),
                                 None if rotinas.ecra_ativo() else falar_alarme(t)), ao_mudar=modo_apagao)
    print(f"A central esta a correr. Abre no telemovel: http://{ip_local()}:{PORT}")
    print("Para parar: Ctrl+C")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

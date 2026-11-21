"""
A Conversa: o chat completo do Jarvis (como a app do Claude), para o telemovel, o PC e o tablet.

- As conversas ficam no vida.db (privadas: /api/conversas pede o PIN). Podes ter varias e voltar a cada uma.
- Cada conversa tem o seu modelo (Sonnet por defeito; Opus num toque) e "pensar mais" (esforco alto).
- Fotos: guardam-se em base64 (ja reduzidas no ecra). Vao ao Claude as fotos que estao na janela (no maximo 6);
  como a conversa e reenviada igual, as fotos ja vistas pagam-se a ~10% (cache).
- Vao ao Claude no maximo cerca de 40 mensagens: o inicio corta-se de 20 em 20, para a cache continuar a servir.
  Uma conversa muito longa fica mais cara: para um assunto novo, comeca outra.
"""

import base64

TABELAS = """
CREATE TABLE IF NOT EXISTS conversas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL DEFAULT '',
    modelo TEXT,
    pensar INTEGER NOT NULL DEFAULT 0,
    criada TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    atualizada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS conversa_msgs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversa_id INTEGER NOT NULL,
    papel TEXT NOT NULL,               -- user ou assistant
    texto TEXT NOT NULL,
    img_tipo TEXT,                     -- image/jpeg, image/png, image/webp
    img_b64 TEXT,
    agora TEXT,                        -- a linha "(Agora: ...)" que foi com a mensagem: reenvia-se igual, para a cache servir
    custo REAL NOT NULL DEFAULT 0,     -- dolares (so nas respostas)
    criada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""
MAX_MSGS = 40
MAX_FOTOS = 6                      # fotos que ficam como imagem na janela (as mais antigas passam a "[foto enviada antes]")
TIPOS_IMG = ("image/jpeg", "image/png", "image/webp")
MAX_IMG = 5 * 1024 * 1024          # 5 MB depois de descodificada


def migrar(con):
    """acrescenta colunas novas a tabelas antigas"""
    cols = {r[1] for r in con.execute("PRAGMA table_info(conversa_msgs)")}
    if "agora" not in cols:
        con.execute("ALTER TABLE conversa_msgs ADD COLUMN agora TEXT")


def listar(con):
    return [dict(r) for r in con.execute(
        """SELECT c.id, c.titulo, c.modelo, c.pensar, c.atualizada,
                  (SELECT COUNT(*) FROM conversa_msgs m WHERE m.conversa_id = c.id) AS msgs,
                  (SELECT COALESCE(SUM(custo), 0) FROM conversa_msgs m WHERE m.conversa_id = c.id) AS custo
           FROM conversas c ORDER BY c.atualizada DESC, c.id DESC LIMIT 100""")]


def criar(con, modelo=None):
    return con.execute("INSERT INTO conversas (modelo) VALUES (?)", (modelo,)).lastrowid


def obter(con, cid):
    c = con.execute("SELECT * FROM conversas WHERE id = ?", (cid,)).fetchone()
    if not c:
        return None
    msgs = [{"id": m["id"], "papel": m["papel"], "texto": m["texto"], "foto": bool(m["img_b64"]), "custo": m["custo"], "criada": m["criada"]}
            for m in con.execute("SELECT * FROM conversa_msgs WHERE conversa_id = ? ORDER BY id", (cid,))]
    return dict(dict(c), mensagens=msgs)


def imagem(con, mid):
    m = con.execute("SELECT img_tipo, img_b64 FROM conversa_msgs WHERE id = ?", (mid,)).fetchone()
    if not m or not m["img_b64"]:
        return None
    return m["img_tipo"], base64.b64decode(m["img_b64"])


def atualizar(con, cid, **campos):
    """so muda os campos que vierem; modelo None volta ao modelo por defeito, titulo '' limpa o titulo"""
    for k in ("titulo", "modelo", "pensar"):
        if k in campos:
            con.execute(f"UPDATE conversas SET {k} = ? WHERE id = ?", (campos[k], cid))


def apagar(con, cid):
    con.execute("DELETE FROM conversa_msgs WHERE conversa_id = ?", (cid,))
    con.execute("DELETE FROM conversas WHERE id = ?", (cid,))


def ler_foto(data_url):
    """'data:image/jpeg;base64,...' -> (tipo, base64). Erro com uma frase clara se nao servir."""
    if not data_url:
        return None, None
    try:
        cab, b64 = data_url.split(",", 1)
        tipo = cab.split(":", 1)[1].split(";", 1)[0]
    except (ValueError, IndexError):
        raise ValueError("a foto não veio bem")
    if tipo not in TIPOS_IMG:
        raise ValueError("a foto tem de ser JPEG, PNG ou WebP")
    try:
        dados = base64.b64decode(b64, validate=True)
    except ValueError:
        raise ValueError("a foto não veio bem")
    if len(dados) > MAX_IMG:
        raise ValueError("a foto é demasiado grande (máximo 5 MB)")
    return tipo, b64


def juntar(con, cid, papel, texto, img_tipo=None, img_b64=None, custo=0.0, agora=None):
    con.execute("INSERT INTO conversa_msgs (conversa_id, papel, texto, img_tipo, img_b64, custo, agora) VALUES (?,?,?,?,?,?,?)",
                (cid, papel, texto, img_tipo, img_b64, custo, agora))
    con.execute("UPDATE conversas SET atualizada = datetime('now','localtime') WHERE id = ?", (cid,))


def historico(con, cid):
    """as mensagens para o Claude (as ultimas MAX_MSGS; so as IMGS_RECENTES fotos mais novas vao como imagem)"""
    todas = [dict(r) for r in con.execute("SELECT * FROM conversa_msgs WHERE conversa_id = ? ORDER BY id", (cid,))]
    # corta o inicio de 20 em 20 mensagens (e nao uma a uma): assim o comeco do historico so muda de vez em quando
    # e a cache continua a servir entre cortes
    excesso = len(todas) - MAX_MSGS
    rs = todas[-(-excesso // 20) * 20:] if excesso > 0 else todas
    while rs and rs[0]["papel"] != "user":     # tem de comecar por uma mensagem tua
        rs.pop(0)
    com_foto = [r["id"] for r in rs if r["img_b64"]][-MAX_FOTOS:]
    out = []
    for r in rs:
        if r["papel"] == "user":
            # a mesma ordem com que foi enviada (hora, foto, texto): assim o Claude le-a da cache
            blocos = [{"type": "text", "text": r["agora"]}] if r["agora"] else []
            if r["img_b64"] and r["id"] in com_foto:
                blocos.append({"type": "image", "source": {"type": "base64", "media_type": r["img_tipo"], "data": r["img_b64"]}})
            elif r["img_b64"]:
                blocos.append({"type": "text", "text": "[foto enviada antes]"})
            blocos.append({"type": "text", "text": r["texto"] or "(foto)"})
            out.append({"role": "user", "content": blocos})
        else:
            out.append({"role": "assistant", "content": r["texto"]})
    return out

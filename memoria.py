"""
Memoria do Jarvis: coisas que lhe dizes para ele se lembrar ("lembra-te que quero ter 4 a Matematica").

- Guardada so no vida.db. Ver e apagar pede o PIN (/api/memoria esta nos PRIVADOS; 'memoria_ver' e 'memoria_apagar' nas PRIVADAS).
- O Claude recebe a memoria nas instrucoes, para responder a pensar nela. No modo amigos nao recebe.
- No maximo 60 coisas, cada uma com 200 letras.
- Ainda NAO esta encriptada (proximo passo: encriptar com uma chave que so o PIN abre).
"""

import re

import assistente

TABELAS = """
CREATE TABLE IF NOT EXISTS memoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    texto TEXT NOT NULL,
    criada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""
MAXIMO = 60


def listar(con):
    return [dict(r) for r in con.execute("SELECT * FROM memoria ORDER BY id")]


def guardar(con, texto):
    texto = " ".join(texto.split()).strip(" .")[:200]
    if len(texto) < 3:
        raise ValueError("isso é muito curto para eu me lembrar")
    if any(assistente.simples(m["texto"]) == assistente.simples(texto) for m in listar(con)):
        return False
    if con.execute("SELECT COUNT(*) FROM memoria").fetchone()[0] >= MAXIMO:
        raise ValueError(f"já me lembro de {MAXIMO} coisas: apaga algumas no ecrã da aprendizagem")
    con.execute("INSERT INTO memoria (texto) VALUES (?)", (texto[:1].upper() + texto[1:],))
    return True


def esquecer(con, texto):
    """procura as memorias com todas as palavras importantes do texto (palavras inteiras).
    So apaga se for exatamente uma; devolve as encontradas."""
    palavras = [p for p in re.findall(r"\w{3,}", assistente.simples(texto)) if p not in ("que", "isso", "sobre", "aquilo", "disse", "tinha")]
    if not palavras:
        return []
    apagar = [m for m in listar(con) if all(re.search(rf"\b{re.escape(p)}\b", assistente.simples(m["texto"])) for p in palavras)]
    if len(apagar) == 1:         # mais do que uma: nao apaga as cegas (apagam-se no ecra da aprendizagem)
        con.execute("DELETE FROM memoria WHERE id = ?", (apagar[0]["id"],))
    return apagar


def para_o_claude(con):
    ms = listar(con)
    if not ms:
        return ""
    return "\n\nO que ele te pediu para te lembrares (usa quando for útil, não repitas sem razão):\n" + "\n".join(f"- {m['texto']}" for m in ms)

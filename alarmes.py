"""
Despertador da central. Corre dentro do servidor (que esta sempre ligado no Termux), por isso toca
mesmo com o ecra apagado. O som sai pelo tablet com a app Termux:API (pkg install termux-api).

- alarmes normais: repetem-se em certos dias da semana (dias = "01234" e segunda a sexta)
- alarmes especiais: so num dia (data = AAAA-MM-DD). Nesse dia substituem os normais.
- saltar: um alarme normal pode ser saltado numa data (ex.: amanha nao ha escola)
"""

import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

SOM = Path(__file__).resolve().parent / "static" / "sons" / "alarme.wav"
TOCAR_NO_MAXIMO = 10 * 60       # para sozinho ao fim de 10 minutos
ADIAR_MINUTOS = 5

TABELAS = """
CREATE TABLE IF NOT EXISTS alarmes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hora TEXT NOT NULL,                 -- HH:MM
    dias TEXT NOT NULL DEFAULT '',      -- "01234" = segunda a sexta (vazio se for so num dia)
    data TEXT,                          -- AAAA-MM-DD para alarmes especiais
    nome TEXT,
    ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS alarmes_saltar (
    alarme_id INTEGER NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (alarme_id, data)
);
"""

_lock = threading.Lock()
_estado = {"tocar": None}   # {"id", "nome", "hora", "desde", "adiado_ate"} enquanto toca ou esta adiado
_disparados = set()
ultimo = {}                 # o ultimo alarme que tocou: {"nome", "hora", "quando"} (para "porque me acordaste?")


def som_no_tablet():
    return bool(shutil.which("termux-media-player"))


def alarmes_do_dia(con, dia):
    """os alarmes que tocam numa data, por ordem de hora"""
    iso = dia.isoformat()
    especiais = con.execute("SELECT * FROM alarmes WHERE ativo = 1 AND data = ?", (iso,)).fetchall()
    if especiais:  # um alarme especial (viagem...) substitui os normais nesse dia
        return sorted([dict(a) for a in especiais], key=lambda a: a["hora"])
    saltar = {r[0] for r in con.execute("SELECT alarme_id FROM alarmes_saltar WHERE data = ?", (iso,))}
    normais = con.execute("SELECT * FROM alarmes WHERE ativo = 1 AND data IS NULL AND instr(dias, ?) > 0",
                          (str(dia.weekday()),)).fetchall()
    return sorted([dict(a) for a in normais if a["id"] not in saltar], key=lambda a: a["hora"])


def proximo(con, agora=None):
    agora = agora or datetime.now()
    for i in range(8):
        dia = agora.date() + timedelta(days=i)
        for a in alarmes_do_dia(con, dia):
            if i > 0 or a["hora"] > agora.strftime("%H:%M"):
                return {"id": a["id"], "hora": a["hora"], "data": dia.isoformat(), "nome": a["nome"] or "",
                        "especial": bool(a["data"])}
    return None


def listar(con):
    saltos = {}
    for r in con.execute("SELECT * FROM alarmes_saltar WHERE data >= date('now','localtime')"):
        saltos.setdefault(r["alarme_id"], []).append(r["data"])
    rows = con.execute("SELECT * FROM alarmes WHERE data IS NULL OR data >= date('now','localtime') ORDER BY data IS NOT NULL, hora").fetchall()
    return {"alarmes": [dict(a, saltar=sorted(saltos.get(a["id"], []))) for a in rows],
            "proximo": proximo(con), "som_no_tablet": som_no_tablet()}


def criar(con, hora, dias="", data=None, nome=None):
    dias = "".join(sorted(set(c for c in str(dias) if c in "0123456")))
    if not dias and not data:
        raise ValueError("escolhe os dias da semana ou uma data")
    con.execute("INSERT INTO alarmes (hora, dias, data, nome) VALUES (?,?,?,?)",
                (hora, "" if data else dias, data, (nome or "").strip()[:60] or None))


def saltar(con, alarme_id, data):
    """liga/desliga o salto de um alarme normal numa data"""
    if con.execute("SELECT 1 FROM alarmes_saltar WHERE alarme_id = ? AND data = ?", (alarme_id, data)).fetchone():
        con.execute("DELETE FROM alarmes_saltar WHERE alarme_id = ? AND data = ?", (alarme_id, data))
        return False
    con.execute("INSERT INTO alarmes_saltar (alarme_id, data) VALUES (?,?)", (alarme_id, data))
    return True


def sem_alarme_no_dia(con, dia):
    """'amanha nao me acordes': salta os normais e desliga os especiais dessa data. Devolve quantos."""
    n = 0
    for a in alarmes_do_dia(con, dia):
        if a["data"]:
            con.execute("UPDATE alarmes SET ativo = 0 WHERE id = ?", (a["id"],))
        else:
            con.execute("INSERT OR IGNORE INTO alarmes_saltar (alarme_id, data) VALUES (?,?)", (a["id"], dia.isoformat()))
        n += 1
    return n


# ---------- tocar ----------

def _correr(*cmd, espera=15):
    try:
        subprocess.run(cmd, capture_output=True, timeout=espera)
    except Exception:
        pass


def _som():
    if som_no_tablet() and SOM.exists():
        _correr("termux-media-player", "play", str(SOM))


def _falar(texto):
    """voz do tablet (fica a falar ate acabar). Devolve 0: nao e preciso esperar mais."""
    if shutil.which("termux-tts-speak") and texto:
        _correr("termux-tts-speak", "-l", "pt", "-n", "PT", "-s", "ALARM", "-r", "1.05", texto, espera=60)
    return 0


def tocar_ficheiro(caminho):
    """toca um som (ex.: a voz neural) pelo tablet"""
    if som_no_tablet():
        _correr("termux-media-player", "play", str(caminho))


falar = _falar  # o servidor troca isto pela voz neural, se estiver ligada


def estado():
    with _lock:
        t = dict(_estado["tocar"]) if _estado["tocar"] else None
    if not t:
        return {"tocando": False}
    adiado = t.get("adiado_ate")
    return {"tocando": not adiado, "nome": t["nome"], "hora": t["hora"],
            "adiado_ate": adiado.strftime("%H:%M") if adiado else None, "som_no_tablet": som_no_tablet()}


def tocar(alarme, texto_bom_dia=None):
    ultimo.update(nome=alarme.get("nome") or "Alarme", hora=alarme.get("hora") or datetime.now().strftime("%H:%M"), quando=time.time())
    with _lock:
        desde = time.time()
        _estado["tocar"] = {"id": alarme.get("id"), "nome": alarme.get("nome") or "Alarme",
                            "hora": alarme.get("hora") or datetime.now().strftime("%H:%M"), "desde": desde, "adiado_ate": None}
    threading.Thread(target=_ciclo_toque, args=(desde, texto_bom_dia), daemon=True).start()


def _ciclo_toque(desde, texto_bom_dia):
    falou = False
    while True:
        with _lock:
            t = _estado["tocar"]
            if not t or t["desde"] != desde or t["adiado_ate"]:
                return
        if time.time() - desde > TOCAR_NO_MAXIMO:
            parar()
            return
        _som()
        if not falou and time.time() - desde > 12 and texto_bom_dia:
            falou = True
            espera = falar(texto_bom_dia()) or 0
            time.sleep(espera)  # deixa acabar de falar antes de voltar a tocar
        time.sleep(4)


def parar():
    with _lock:
        _estado["tocar"] = None
    if som_no_tablet():
        _correr("termux-media-player", "stop")


def adiar():
    with _lock:
        if not _estado["tocar"]:
            return None
        _estado["tocar"]["adiado_ate"] = datetime.now() + timedelta(minutes=ADIAR_MINUTOS)
        ate = _estado["tocar"]["adiado_ate"]
    if som_no_tablet():
        _correr("termux-media-player", "stop")
    return ate.strftime("%H:%M")


def vigiar(db, texto_bom_dia):
    """thread que corre para sempre: ve a cada 5 segundos se ha um alarme para tocar"""
    def ciclo():
        while True:
            try:
                agora = datetime.now()
                with _lock:
                    t = _estado["tocar"]
                    voltar = t and t["adiado_ate"] and agora >= t["adiado_ate"]
                if voltar:
                    tocar(t, texto_bom_dia)
                hm, hoje = agora.strftime("%H:%M"), agora.date()
                with db() as con:
                    for a in alarmes_do_dia(con, hoje):
                        chave = (a["id"], hoje.isoformat(), a["hora"])
                        if a["hora"] == hm and chave not in _disparados:
                            _disparados.add(chave)
                            if a["data"]:  # os especiais so tocam uma vez
                                con.execute("UPDATE alarmes SET ativo = 0 WHERE id = ?", (a["id"],))
                            tocar(a, texto_bom_dia)
            except Exception as e:
                print("alarme:", e)
            time.sleep(5)
    threading.Thread(target=ciclo, daemon=True).start()

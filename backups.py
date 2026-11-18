"""
Copias de seguranca do vida.db.

Todas as noites (e ao arrancar, se a ultima tiver mais de um dia) faz uma copia com a API de backup do SQLite,
que funciona mesmo com a central a escrever na base de dados. Depois confirma a copia com PRAGMA integrity_check:
uma copia que nao passa e apagada, para nunca haver uma copia estragada a fingir que esta boa.

Guarda as ultimas 14 copias diarias e a primeira de cada mes dos ultimos 6 meses, na pasta backups/ (fora do GitHub).

Copia fora da Termux (opcional, config "backup_fora" = "1"): se a Termux for desinstalada, a pasta ~/central
vai com ela. Com esta opcao, a ultima copia tambem vai para ~/storage/shared/Central/ (precisa de
termux-setup-storage). Atencao: ai qualquer app com acesso aos ficheiros a consegue ler, e o vida.db tem
os dados da familia. Por isso vem desligada.
"""

import os
import shutil
import sqlite3
import threading
import time
from datetime import date, datetime
from pathlib import Path

PASTA = Path(__file__).resolve().parent / "backups"
FORA = Path(os.path.expanduser("~/storage/shared/Central"))
DIARIAS = 14
MENSAIS = 6
HORA = 4  # 04:00, quando ninguem esta a usar a central

_trinco = threading.Lock()


def _ficheiros():
    return sorted(PASTA.glob("vida-????-??-??.db"))


def _data(f):
    return date.fromisoformat(f.stem[5:])


def listar():
    fs = _ficheiros()
    return [{"ficheiro": f.name, "data": _data(f).isoformat(), "kb": round(f.stat().st_size / 1024)} for f in reversed(fs)]


def ultima():
    fs = _ficheiros()
    if not fs:
        return None
    f = fs[-1]
    return {"ficheiro": f.name, "data": _data(f).isoformat(),
            "quando": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="minutes")}


def _limpar(hoje):
    fs = _ficheiros()
    manter = {f for f in fs if (hoje - _data(f)).days < DIARIAS}
    meses = {}
    for f in fs:  # a mais antiga de cada mes
        d = _data(f)
        meses.setdefault((d.year, d.month), f)
    agora = hoje.year * 12 + hoje.month - 1
    manter |= {f for (a, m), f in meses.items() if agora - (a * 12 + m - 1) < MENSAIS}
    for f in fs:
        if f not in manter:
            f.unlink()


def fazer(db_path, fora=False, hoje=None):
    """faz a copia de hoje (substitui a de hoje se ja existir). Devolve {ok, ficheiro, kb} ou {ok: False, erro}."""
    hoje = hoje or date.today()
    with _trinco:
        PASTA.mkdir(exist_ok=True)
        destino = PASTA / f"vida-{hoje.isoformat()}.db"
        tmp = destino.with_suffix(".tmp")
        try:
            origem = sqlite3.connect(db_path)
            copia = sqlite3.connect(tmp)
            with copia:
                origem.backup(copia)
            ok = copia.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            copia.close()
            origem.close()
            if not ok:
                tmp.unlink(missing_ok=True)
                return {"ok": False, "erro": "a copia nao passou na verificacao do SQLite"}
            os.replace(tmp, destino)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            return {"ok": False, "erro": str(e)}
        _limpar(hoje)
        r = {"ok": True, "ficheiro": destino.name, "kb": round(destino.stat().st_size / 1024)}
        if fora:
            if FORA.parent.exists():
                try:
                    FORA.mkdir(exist_ok=True)
                    shutil.copy2(destino, FORA / "vida-ultima.db")
                    r["fora"] = True
                except Exception as e:
                    r["fora_erro"] = str(e)
            else:
                r["fora_erro"] = "sem acesso aos ficheiros do tablet (corre termux-setup-storage)"
        return r


def vigiar(db_path, ler_fora, avisar):
    """thread: copia ao arrancar se a ultima tiver mais de um dia, e depois todos os dias as 04:00.
    Se uma copia falhar, avisa (uma vez por dia) em vez de ficar calado."""
    def ciclo():
        time.sleep(30)
        falhou = None
        while True:
            try:
                u = ultima()
                hoje = date.today()
                atrasada = not u or (hoje - date.fromisoformat(u["data"])).days >= 1
                if atrasada and (datetime.now().hour >= HORA or not u or (hoje - date.fromisoformat(u["data"])).days >= 2):
                    r = fazer(db_path, fora=ler_fora())
                    if r["ok"]:
                        falhou = None
                        if r.get("fora_erro"):
                            print("backup fora:", r["fora_erro"])
                    elif falhou != hoje:
                        falhou = hoje
                        avisar(f"A cópia de segurança de hoje falhou: {r['erro']}.")
            except Exception as e:
                print("backups:", e)
            time.sleep(600)
    threading.Thread(target=ciclo, daemon=True).start()

"""
Copias de seguranca do vida.db (tarefas, testes, estudo, diario, roupa, familia...).

- Uma copia por dia, feita com a API de backup do SQLite (e segura com o servidor a escrever ao mesmo tempo).
- Cada copia e verificada (PRAGMA integrity_check) antes de contar como boa, e fica comprimida (.db.gz).
- Ficam as 14 ultimas e a primeira de cada mes dos ultimos 6 meses.
- Se o Termux tiver acesso ao armazenamento (termux-setup-storage), a copia vai tambem para
  Armazenamento interno/Central/backups. Essa pasta sobrevive a desinstalar o Termux; a pasta
  backups/ dentro da central nao. Nenhuma das duas sobrevive a perder o tablet: para isso,
  copia de vez em quando um ficheiro dessa pasta para o computador ou para a nuvem.

Restaurar: parar a central, gunzip -c backups/vida-AAAA-MM-DD.db.gz > vida.db, voltar a iniciar.
"""

import gzip
import os
import re
import shutil
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
PASTA = Path(os.environ.get("VIDA_BACKUPS", BASE / "backups"))
ESPELHO = Path(os.environ.get("VIDA_BACKUPS_ESPELHO", Path.home() / "storage" / "shared" / "Central" / "backups"))
GUARDAR_DIAS = 14
GUARDAR_MESES = 6
NOME = re.compile(r"^vida-(\d{4}-\d{2}-\d{2})\.db\.gz$")

_trinco = threading.Lock()
_ultimo_erro = None


def _copias(pasta):
    if not pasta.is_dir():
        return []
    return sorted((m[1], p) for p in pasta.iterdir() if (m := NOME.match(p.name)))


def _espelho_ok():
    # so usa o armazenamento partilhado se o termux-setup-storage ja foi feito (a pasta storage/shared existe)
    return ESPELHO.parent.parent.is_dir()


def _limpar(pasta):
    cs = _copias(pasta)
    manter = {d for d, _ in cs[-GUARDAR_DIAS:]}
    meses = {}
    for d, _ in cs:
        meses.setdefault(d[:7], d)                       # a primeira copia de cada mes
    manter |= set(sorted(meses.values())[-GUARDAR_MESES:])
    for d, p in cs:
        if d not in manter:
            p.unlink(missing_ok=True)


def fazer(db_path):
    """Faz a copia de hoje (substitui a de hoje se ja existir). Devolve o estado()."""
    global _ultimo_erro
    with _trinco:
        PASTA.mkdir(parents=True, exist_ok=True)
        hoje = datetime.now().strftime("%Y-%m-%d")
        tmp = PASTA / f".tmp-{hoje}.db"
        final = PASTA / f"vida-{hoje}.db.gz"
        try:
            src = sqlite3.connect(db_path)
            dst = sqlite3.connect(tmp)
            try:
                src.backup(dst)
                ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                dst.close(); src.close()
            if ok != "ok":
                raise RuntimeError(f"a copia nao passou na verificacao: {ok}")
            with open(tmp, "rb") as f, gzip.open(PASTA / f".tmp-{hoje}.db.gz", "wb") as g:
                shutil.copyfileobj(f, g)
            os.replace(PASTA / f".tmp-{hoje}.db.gz", final)
            _limpar(PASTA)
            if _espelho_ok():
                ESPELHO.mkdir(parents=True, exist_ok=True)
                shutil.copy2(final, ESPELHO / final.name)
                _limpar(ESPELHO)
            _ultimo_erro = None
        except Exception as e:
            _ultimo_erro = f"{e.__class__.__name__}: {e}"
            print("backups:", _ultimo_erro)
        finally:
            tmp.unlink(missing_ok=True)
            (PASTA / f".tmp-{hoje}.db.gz").unlink(missing_ok=True)   # se falhou a meio (disco cheio...), nao fica lixo
    return estado()


def estado():
    cs = _copias(PASTA)
    ult = cs[-1][1] if cs else None
    return {
        "ultima": datetime.fromtimestamp(ult.stat().st_mtime).strftime("%Y-%m-%d %H:%M") if ult else None,
        "tamanho_kb": round(ult.stat().st_size / 1024) if ult else None,
        "quantas": len(cs),
        "espelho": len(_copias(ESPELHO)) if _espelho_ok() else None,   # None = sem termux-setup-storage
        "erro": _ultimo_erro,
    }


def frase(e=None):
    e = e or estado()
    if e["erro"]:
        return f"A última cópia de segurança falhou ({e['erro']})."
    if not e["ultima"]:
        return "Ainda não há nenhuma cópia de segurança."
    f = f"A última cópia de segurança é de {e['ultima']}. Tenho {e['quantas']} {'guardada' if e['quantas'] == 1 else 'guardadas'}."
    if e["espelho"] is None:
        f += " Estão só dentro do Termux: corre termux-setup-storage para ficarem também no armazenamento do tablet."
    return f


def vigiar(db_path):
    """Confere de hora a hora; faz uma copia se a ultima tiver mais de 24 horas (ou nao houver nenhuma)."""
    def ciclo():
        time.sleep(60)                                   # deixa o servidor arrancar primeiro
        while True:
            cs = _copias(PASTA)
            if not cs or time.time() - cs[-1][1].stat().st_mtime > 24 * 3600:
                fazer(db_path)
            time.sleep(3600)
    threading.Thread(target=ciclo, daemon=True).start()

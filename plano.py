"""
Plano de estudo automatico: quando marcas um teste, a central poe sessoes de estudo na agenda nos dias antes dele.

- Ate 5 sessoes, nos ultimos dias antes do teste (nunca no proprio dia): 30 minutos, e 45 na vespera.
- Hora: 18h00 em dias de semana e 11h00 ao fim de semana; se chocar com uma aula do horario ou com um
  evento, anda de meia em meia hora ate as 21h00. Se o dia estiver cheio, salta esse dia.
- As sessoes sao eventos normais da agenda (aparecem no "O teu dia", no Jarvis e no Iron Man).
  Ficam ligadas ao teste (tabela plano_estudo): se apagares o teste, o plano vai com ele.
- "Faz-me um plano de estudo para Matematica" refaz o plano desse teste.
"""

from datetime import date, datetime, timedelta

TABELAS = """
CREATE TABLE IF NOT EXISTS plano_estudo (
    evento_id INTEGER NOT NULL,
    teste_id INTEGER NOT NULL
);
"""
MAX_SESSOES = 5
FIM_DO_DIA = "21:00"


def _min(h):
    return int(h[:2]) * 60 + int(h[3:5])


def _hora(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def _livre(con, dia, inicio, duracao):
    """True se [inicio, inicio + duracao) nao choca com aulas nem com eventos desse dia"""
    a, b = _min(inicio), _min(inicio) + duracao
    for r in con.execute("SELECT inicio, fim FROM horario WHERE dia = ?", (dia.weekday(),)):
        if a < _min(r["fim"]) and _min(r["inicio"]) < b:
            return False
    for r in con.execute("SELECT hora FROM eventos WHERE data = ? AND hora IS NOT NULL AND hora != ''", (dia.isoformat(),)):
        e = _min(r["hora"])
        if a < e + 60 and e < b:           # um evento conta como uma hora
            return False
    return True


def _hora_livre(con, dia, duracao, agora=None):
    base = 11 * 60 if dia.weekday() >= 5 else 18 * 60
    if agora and dia == agora.date():      # hoje: nunca antes de agora (mais uma margem)
        base = max(base, ((agora.hour * 60 + agora.minute) // 30 + 1) * 30)
    m = base
    while m + duracao <= _min(FIM_DO_DIA):
        if _livre(con, dia, _hora(m), duracao):
            return _hora(m)
        m += 30
    return None


def apagar(con, teste_id, desde=None):
    """apaga as sessoes do plano. Com 'desde' (ao refazer), so as de hoje para a frente: as passadas ficam no historico."""
    for ev in [r[0] for r in con.execute("SELECT evento_id FROM plano_estudo WHERE teste_id = ?", (teste_id,))]:
        e = con.execute("SELECT data FROM eventos WHERE id = ?", (ev,)).fetchone()
        if desde and e and e["data"] < desde.isoformat():
            continue
        con.execute("DELETE FROM eventos WHERE id = ?", (ev,))
        con.execute("DELETE FROM plano_estudo WHERE evento_id = ?", (ev,))


def gerar(con, teste_id, agora=None):
    """(re)faz o plano de um teste. Devolve [(data, hora, minutos)] das sessoes marcadas."""
    agora = agora or datetime.now()
    hoje = agora.date()
    t = con.execute("SELECT * FROM testes WHERE id = ?", (teste_id,)).fetchone()
    if not t:
        return []
    apagar(con, teste_id, desde=hoje)
    dt = date.fromisoformat(t["data"])
    if dt <= hoje:
        return []
    dias = [dt - timedelta(days=i) for i in range(1, MAX_SESSOES + 1) if dt - timedelta(days=i) >= hoje]
    marcadas = []
    for dia in sorted(dias):
        duracao = 45 if dia == dt - timedelta(days=1) else 30
        h = _hora_livre(con, dia, duracao, agora)
        if not h:
            continue
        titulo = f"Estudar {t['disciplina']} ({duracao} min)" + (f": {t['materia']}" if t["materia"] else "")
        ev = con.execute("INSERT INTO eventos (titulo, data, hora) VALUES (?,?,?)", (titulo[:120], dia.isoformat(), h)).lastrowid
        con.execute("INSERT INTO plano_estudo (evento_id, teste_id) VALUES (?,?)", (ev, teste_id))
        marcadas.append((dia, h, duracao))
    return marcadas


def frase(marcadas, disciplina):
    if not marcadas:
        return f"Não consegui marcar sessões de estudo de {disciplina}: ou o teste é já, ou os dias estão cheios."
    dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    lista = ", ".join(f"{dias[d.weekday()]} às {h.replace(':00', 'h').replace(':30', 'h30')}" for d, h, _ in marcadas)
    total = sum(m for _, _, m in marcadas)
    return f"Fiz-te um plano para {disciplina}: {len(marcadas)} sessões, {total} minutos no total ({lista}). Está na agenda."

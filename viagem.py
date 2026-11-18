"""
Modo viagem: a mala feita com a roupa que tens na central, o tempo no destino, a hora e o cambio,
e a casa em pausa (alarmes normais e rotinas) enquanto estas fora.

Tudo o que e da viagem (destino, datas, notas, link) fica no vida.db, nunca no codigo:
o repositorio e publico e as datas em que a casa fica vazia nao devem estar na internet.

Fontes:
- local e fuso: Open-Meteo Geocoding
- tempo: Open-Meteo Forecast (ate 16 dias antes); mais cedo, o que fez nas mesmas datas
  do ano passado (Open-Meteo Historical, ERA5). Nunca e "previsao" quando nao e.
- cambio: taxas de referencia do BCE, via frankfurter.app
"""

import json
import math
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

TABELAS = """
CREATE TABLE IF NOT EXISTS viagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destino TEXT NOT NULL,
    pais TEXT, pais_codigo TEXT,
    lat REAL, lon REAL,
    inicio TEXT NOT NULL,                 -- AAAA-MM-DD (dia em que sais de casa)
    fim TEXT NOT NULL,                    -- AAAA-MM-DD (dia em que voltas)
    moeda TEXT,                           -- ex.: THB (opcional)
    link TEXT,                            -- ex.: o artefacto da viagem
    notas TEXT,
    pausar_casa INTEGER NOT NULL DEFAULT 1,
    criada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS viagem_itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    viagem_id INTEGER NOT NULL,
    grupo TEXT NOT NULL,                  -- roupa, documentos, saude, eletronica, outros
    texto TEXT NOT NULL,
    roupa_id INTEGER,                     -- peca da tabela roupa (se for uma peca tua)
    feito INTEGER NOT NULL DEFAULT 0,
    auto INTEGER NOT NULL DEFAULT 1       -- 1 = gerado pela central, 0 = posto por ti
);
"""

GRUPOS = ["roupa", "documentos", "saude", "eletronica", "outros"]

# UE + Islandia, Liechtenstein, Noruega e Suica: onde vale o Cartao Europeu de Seguro de Doenca
CESD = set("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE IS LI NO CH".split())
# paises da UE com tomadas diferentes das portuguesas (tipo G)
TOMADA_G = {"IE", "MT", "CY"}

# moeda de cada pais (ISO 4217), so para os destinos mais comuns; nos outros escreve-se a mao
MOEDAS = {"GB": "GBP", "US": "USD", "CH": "CHF", "TH": "THB", "BR": "BRL", "JP": "JPY", "CN": "CNY", "CA": "CAD",
          "AU": "AUD", "NO": "NOK", "SE": "SEK", "DK": "DKK", "PL": "PLN", "CZ": "CZK", "HU": "HUF", "TR": "TRY",
          "MX": "MXN", "IN": "INR", "KR": "KRW", "ZA": "ZAR", "IS": "ISK", "RO": "RON", "BG": "BGN", "SG": "SGD",
          "ID": "IDR", "MY": "MYR", "PH": "PHP", "NZ": "NZD", "IL": "ILS", "HK": "HKD"}

_cache = {}


def _json(url, ttl=1800):
    agora = datetime.now().timestamp()
    if url in _cache and agora - _cache[url][0] < ttl:
        return _cache[url][1]
    req = urllib.request.Request(url, headers={"User-Agent": "central-do-quarto"})
    with urllib.request.urlopen(req, timeout=8) as r:
        d = json.loads(r.read().decode())
    _cache[url] = (agora, d)
    return d


# ---------- viagens ----------

def geocodificar(nome):
    q = urllib.parse.quote(nome)
    r = _json(f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=pt&format=json", 86400)
    if not r.get("results"):
        return None
    x = r["results"][0]
    return {"destino": x["name"], "pais": x.get("country"), "pais_codigo": x.get("country_code"),
            "lat": x["latitude"], "lon": x["longitude"]}


def listar(con):
    return [dict(r) for r in con.execute("SELECT * FROM viagens ORDER BY inicio")]


def atual(con, hoje=None):
    """a viagem que esta a decorrer, ou a proxima. None se nao houver."""
    hoje = (hoje or date.today()).isoformat()
    r = con.execute("SELECT * FROM viagens WHERE fim >= ? ORDER BY inicio LIMIT 1", (hoje,)).fetchone()
    return dict(r) if r else None


def em_viagem(con, dia):
    """True se nesse dia a casa esta em pausa (estas fora)"""
    iso = dia.isoformat()
    try:
        return bool(con.execute("SELECT 1 FROM viagens WHERE pausar_casa = 1 AND inicio <= ? AND fim >= ?", (iso, iso)).fetchone())
    except Exception:          # a tabela ainda nao existe
        return False


def criar(con, destino, inicio, fim, moeda=None, link=None, notas=None, pausar_casa=True):
    g = geocodificar(destino)
    if not g:
        raise ValueError(f"não encontrei '{destino}' no mapa (Open-Meteo)")
    cur = con.execute(
        "INSERT INTO viagens (destino, pais, pais_codigo, lat, lon, inicio, fim, moeda, link, notas, pausar_casa) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (g["destino"], g["pais"], g["pais_codigo"], g["lat"], g["lon"], inicio.isoformat(), fim.isoformat(),
         moeda, link, notas, 1 if pausar_casa else 0))
    vid = cur.lastrowid
    if not moeda and g["pais_codigo"] in MOEDAS:
        con.execute("UPDATE viagens SET moeda = ? WHERE id = ?", (MOEDAS[g["pais_codigo"]], vid))
    gerar_mala(con, vid)
    return vid


def apagar(con, vid):
    con.execute("DELETE FROM viagem_itens WHERE viagem_id = ?", (vid,))
    con.execute("DELETE FROM viagens WHERE id = ?", (vid,))


# ---------- tempo, hora e cambio (sempre com fonte) ----------

def tempo(v, hoje=None):
    """{fonte, tipo: previsao|ano_passado, tmax, tmin, chuva (% de dias com chuva), utc_offset} ou {erro}"""
    hoje = hoje or date.today()
    ini, fim = date.fromisoformat(v["inicio"]), date.fromisoformat(v["fim"])
    try:
        if (fim - hoje).days <= 15:                      # a previsao so conta se cobrir a viagem toda
            d = _json(f"https://api.open-meteo.com/v1/forecast?latitude={v['lat']}&longitude={v['lon']}"
                      "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto&forecast_days=16")
            dd = d["daily"]
            idx = [i for i, x in enumerate(dd["time"]) if ini.isoformat() <= x <= fim.isoformat()]
            if len(idx) == (fim - max(ini, hoje)).days + 1:
                chuva = [dd["precipitation_probability_max"][i] or 0 for i in idx]
                return {"tipo": "previsao", "fonte": "Open-Meteo (previsão)", "dias": len(idx),
                        "tmax": round(max(dd["temperature_2m_max"][i] for i in idx)),
                        "tmin": round(min(dd["temperature_2m_min"][i] for i in idx)),
                        "chuva": round(max(chuva)), "chuva_txt": f"até {round(max(chuva))}% de probabilidade",
                        "utc_offset": d.get("utc_offset_seconds")}
        # longe demais para previsao: o que fez nas mesmas datas do ano passado
        a_ini, a_fim = _ano_antes(ini), _ano_antes(fim)
        d = _json(f"https://archive-api.open-meteo.com/v1/archive?latitude={v['lat']}&longitude={v['lon']}"
                  f"&start_date={a_ini}&end_date={a_fim}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto", 86400)
        dd = d["daily"]
        mx = [x for x in dd["temperature_2m_max"] if x is not None]
        mn = [x for x in dd["temperature_2m_min"] if x is not None]
        pr = [x for x in dd["precipitation_sum"] if x is not None]
        if not mx:
            return {"erro": "sem dados"}
        com_chuva = sum(1 for x in pr if x >= 1)
        return {"tipo": "ano_passado", "fonte": f"Open-Meteo (histórico de {a_ini.year}, não é previsão)", "dias": len(mx),
                "tmax": round(max(mx)), "tmin": round(min(mn)),
                "chuva": round(100 * com_chuva / max(1, len(pr))), "chuva_txt": f"choveu em {com_chuva} de {len(pr)} dias",
                "utc_offset": d.get("utc_offset_seconds")}
    except Exception as e:
        return {"erro": "sem dados", "detalhe": e.__class__.__name__}


def _ano_antes(d):
    try:
        return d.replace(year=d.year - 1)
    except ValueError:         # 29 de fevereiro
        return d.replace(year=d.year - 1, day=28)


def cambio(moeda):
    if not moeda:
        return None
    try:
        d = _json(f"https://api.frankfurter.app/latest?from=EUR&to={urllib.parse.quote(moeda)}", 6 * 3600)
        return {"moeda": moeda, "taxa": d["rates"][moeda], "data": d["date"], "fonte": "BCE (frankfurter.app)"}
    except Exception:
        return {"moeda": moeda, "erro": "sem dados"}


def hora_local(utc_offset):
    if utc_offset is None:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=utc_offset)).strftime("%H:%M")


# ---------- a mala ----------

def _pecas(roupa, tipos, quantos, ja):
    arrumadas = [p for p in roupa if p["tipo"] in tipos and p["estado"] == "arrumada" and p["id"] not in ja]
    sujas = [p for p in roupa if p["tipo"] in tipos and p["estado"] == "para lavar" and p["id"] not in ja]
    escolha = (arrumadas + sujas)[:quantos]       # se faltar, entra a que esta para lavar (com aviso)
    ja.update(p["id"] for p in escolha)
    return escolha


def gerar_mala(con, vid, clima=None):
    """(re)faz a parte automatica da lista. Mantem o que puseste a mao e o que ja tinhas marcado."""
    v = dict(con.execute("SELECT * FROM viagens WHERE id = ?", (vid,)).fetchone())
    clima = clima or tempo(v)
    feitos = {(r["texto"], r["roupa_id"]) for r in con.execute("SELECT texto, roupa_id FROM viagem_itens WHERE viagem_id = ? AND feito = 1", (vid,))}
    con.execute("DELETE FROM viagem_itens WHERE viagem_id = ? AND auto = 1", (vid,))
    roupa = [dict(r) for r in con.execute("SELECT * FROM roupa WHERE estado != 'emprestada'")]
    n = (date.fromisoformat(v["fim"]) - date.fromisoformat(v["inicio"])).days + 1
    tmax, tmin, chuva = clima.get("tmax"), clima.get("tmin"), clima.get("chuva") or 0
    calor = tmax is not None and tmax >= 24
    frio = tmin is not None and tmin < 12
    tropical = v["lat"] is not None and abs(v["lat"]) < 23.5
    fora = (v["pais_codigo"] or "PT") != "PT"
    itens, ja = [], set()

    def roupa_(rotulo, tipos, quantos):
        if quantos <= 0:
            return
        pecas = _pecas(roupa, tipos, quantos, ja)
        for p in pecas:
            itens.append(("roupa", p["nome"] + (f" ({p['local']})" if p.get("local") else ""), p["id"]))
        if len(pecas) < quantos:
            itens.append(("roupa", f"{quantos - len(pecas)}× {rotulo} (não tens mais na central)", None))

    lavar = min(n, 10)                              # mais de 10 dias: conta com lavar la
    roupa_("t-shirt", ["t-shirt"], lavar)
    if calor:
        roupa_("calções", ["calcoes"], max(2, math.ceil(lavar / 2)))
        roupa_("calças", ["calcas"], 1)
    else:
        roupa_("calças", ["calcas"], max(1, math.ceil(lavar / 3)))
    if tmin is None or tmin < 17:
        roupa_("sweat ou camisola", ["sweat", "camisola"], 1 if n <= 4 else 2)
    else:
        roupa_("sweat leve (avião e ar condicionado)", ["sweat", "camisola"], 1)
    if frio or chuva >= 40:
        roupa_("casaco", ["casaco"], 1)
    roupa_("calçado", ["calcado"], 2 if calor or n > 4 else 1)
    itens.append(("roupa", f"{min(n + 1, 11)}× roupa interior e meias", None))
    itens.append(("roupa", "Pijama", None))
    if calor:
        itens += [("roupa", "Fato de banho", None), ("roupa", "Chinelos", None), ("roupa", "Chapéu ou boné", None)]

    if fora:
        itens.append(("documentos", "Passaporte (confirma a validade exigida pelo país)", None))
        if v["pais_codigo"] in CESD:
            itens.append(("documentos", "Cartão Europeu de Seguro de Doença", None))
        else:
            itens.append(("documentos", "Seguro de viagem (o Cartão Europeu de Seguro de Doença não vale neste país)", None))
    itens.append(("documentos", "Cartão de Cidadão", None))
    itens.append(("documentos", "Cartão bancário e algum dinheiro", None))

    itens += [("saude", "Escova e pasta de dentes", None), ("saude", "Gel de banho e desodorizante", None),
              ("saude", "Medicamentos que tomas sempre", None)]
    if calor:
        itens.append(("saude", "Protetor solar", None))
    if tropical:
        itens.append(("saude", "Repelente de mosquitos", None))

    itens += [("eletronica", "Carregador do telemóvel", None),
              ("eletronica", "Powerbank (na bagagem de mão: no porão não é permitido)", None),
              ("eletronica", "Auriculares", None)]
    if fora and (v["pais_codigo"] not in CESD or v["pais_codigo"] in TOMADA_G):
        itens.append(("eletronica", "Adaptador de tomada (confirma o tipo de tomada do país)", None))
    if chuva >= 40:
        itens.append(("outros", "Guarda-chuva ou impermeável", None))

    con.executemany("INSERT INTO viagem_itens (viagem_id, grupo, texto, roupa_id, feito, auto) VALUES (?,?,?,?,?,1)",
                    [(vid, g, t, r, 1 if (t, r) in feitos else 0) for g, t, r in itens])


def itens(con, vid):
    rs = con.execute("""SELECT i.*, r.estado AS estado_roupa, r.imagem FROM viagem_itens i
                        LEFT JOIN roupa r ON r.id = i.roupa_id WHERE i.viagem_id = ? ORDER BY i.id""", (vid,))
    return [dict(r) for r in rs]


def resumo(con, v=None, hoje=None, com_fontes=True):
    """tudo o que o ecra precisa da viagem atual"""
    hoje = hoje or date.today()
    v = v or atual(con, hoje)
    if not v:
        return None
    its = itens(con, v["id"])
    ini, fim = date.fromisoformat(v["inicio"]), date.fromisoformat(v["fim"])
    r = dict(v, itens=its, feitos=sum(i["feito"] for i in its), total=len(its),
             faltam_dias=(ini - hoje).days, em_viagem=ini <= hoje <= fim, dias=(fim - ini).days + 1,
             para_lavar=[i["texto"] for i in its if i["estado_roupa"] == "para lavar" and not i["feito"]])
    if com_fontes:
        r["tempo"] = tempo(v, hoje)
        r["hora_local"] = hora_local(r["tempo"].get("utc_offset"))
        r["cambio"] = cambio(v["moeda"])
    return r


def frase(r):
    if not r:
        return "Não tens nenhuma viagem marcada. Diz por exemplo: nova viagem para Madrid de 3 a 7 de março."
    if r["em_viagem"]:
        f = f"Estás em viagem: {r['destino']}, até {_dm(r['fim'])}."
    elif r["faltam_dias"] == 1:
        f = f"A viagem para {r['destino']} é amanhã."
    else:
        f = f"Faltam {r['faltam_dias']} dias para {r['destino']}."
    falta = r["total"] - r["feitos"]
    f += " A mala está feita." if not falta else f" Na mala faltam {falta} de {r['total']} coisas."
    if r["para_lavar"]:
        f += f" Para lavar antes de ir: {', '.join(r['para_lavar'][:3])}."
    t = r.get("tempo") or {}
    if t.get("tmax") is not None:
        f += (f" Previsão lá: entre {t['tmin']} e {t['tmax']} graus." if t["tipo"] == "previsao"
              else f" O ano passado, nestas datas, esteve entre {t['tmin']} e {t['tmax']} graus.")
    return f


def _dm(iso):
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    d = date.fromisoformat(iso)
    return f"{d.day} de {meses[d.month - 1]}"

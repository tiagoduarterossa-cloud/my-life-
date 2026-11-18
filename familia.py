"""
A familia: avos, tios, primos... com aniversarios, o tempo onde vivem, ha quanto tempo nao falas com eles,
e os perigos reais perto da casa deles (avisos do IPMA, incendios, sismos).

Os dados da familia ficam so no tablet (vida.db, fora do GitHub).
"""

import json
import threading
import time
import urllib.parse
from datetime import date

import avisos

TABELAS = """
CREATE TABLE IF NOT EXISTS familia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    relacao TEXT NOT NULL DEFAULT '',     -- avó, avô, tia, primo...
    aniversario TEXT,                     -- AAAA-MM-DD (ou 0000-MM-DD se nao souberes o ano)
    cidade TEXT,
    lat REAL, lon REAL,
    ultimo_contacto TEXT                  -- AAAA-MM-DD
);
"""


def geocodificar(cidade):
    q = urllib.parse.quote(cidade)
    r = avisos._json(f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=pt&format=json", 86400)
    if not r.get("results"):
        return None
    x = r["results"][0]
    return x["name"], x["latitude"], x["longitude"]


def _dias_ate_aniversario(aniv, hoje):
    try:
        m, d = int(aniv[5:7]), int(aniv[8:10])
        proximo = date(hoje.year, m, d)
        if proximo < hoje:
            proximo = date(hoje.year + 1, m, d)
        return (proximo - hoje).days, (proximo.year - int(aniv[:4])) if aniv[:4] != "0000" else None
    except (ValueError, TypeError):
        return None, None


def listar(con, hoje=None):
    hoje = hoje or date.today()
    out = []
    for r in con.execute("SELECT * FROM familia ORDER BY id"):
        p = dict(r)
        p["dias_aniversario"], p["faz_anos"] = _dias_ate_aniversario(p.get("aniversario"), hoje)
        p["dias_sem_falar"] = (hoje - date.fromisoformat(p["ultimo_contacto"])).days if p.get("ultimo_contacto") else None
        out.append(p)
    return out


def perigos(lat, lon):
    """perigos reais perto de um sitio. Cada fonte pode falhar sozinha: ai diz 'sem dados', nunca inventa."""
    r = {"avisos": None, "fogos": None, "sismos": None}
    try:
        r["avisos"] = [a for a in avisos.avisos_ipma(lat, lon)["avisos"]]
    except Exception:
        pass
    try:
        r["fogos"] = [f for f in avisos.incendios(lat, lon)["perto"] if f["km"] <= 25]
    except Exception:
        pass
    try:
        r["sismos"] = [s for s in avisos.sismos(lat, lon)["perto"] if s["km"] <= 300 and s["mag"] >= 3]
    except Exception:
        pass
    return r


def tempo(lat, lon):
    try:
        m = avisos._json(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&timezone=auto", 900)
        return round(m["current"]["temperature_2m"])
    except Exception:
        return None


def feminino(p):
    r = (p.get("relacao") or "").lower()
    return r.endswith("a") or r in ("avó", "mãe", "bisavó")


def com_artigo(p):
    """'a avó Maria', 'o tio Rui', ou so 'Maria' se nao houver relacao"""
    quem = f"{p['relacao']} {p['nome']}".strip()
    return (("a " if feminino(p) else "o ") + quem) if p.get("relacao") else quem


def frase_pessoa(p, pg, graus):
    partes = [f"Na casa d{com_artigo(p)}" +
              (f", em {p['cidade']}" if p.get("cidade") else "") + (f", estão {graus} graus." if graus is not None else ".")]
    if pg["avisos"] is None:
        partes.append("Não consegui ver os avisos do IPMA.")
    elif pg["avisos"]:
        a = pg["avisos"][0]
        partes.append(f"Segundo o IPMA, há aviso {a['nivel']} de {a['tipo'].lower()}.")
    else:
        partes.append("Sem avisos do IPMA.")
    if pg["fogos"]:
        partes.append(f"Atenção: há um incêndio ativo a {pg['fogos'][0]['km']} quilómetros, segundo a Proteção Civil.")
    elif pg["fogos"] is not None:
        partes.append("Sem incêndios perto.")
    if pg["sismos"]:
        partes.append(f"Segundo o USGS, houve um sismo de {pg['sismos'][0]['mag']} a {pg['sismos'][0]['km']} quilómetros.")
    return " ".join(partes)


def procurar(con, texto_simples):
    """encontra familiares mencionados numa frase ('avó', 'avós', 'tia Ana', o nome)"""
    import assistente
    ps = listar(con)
    achados = [p for p in ps if assistente.simples(p["nome"]) in texto_simples or
               (p["relacao"] and assistente.simples(p["relacao"]) in texto_simples)]
    if not achados and "familia" in texto_simples:
        achados = ps
    elif not achados and "avos" in texto_simples:
        achados = [p for p in ps if assistente.simples(p["relacao"]).startswith("av")] or ps
    return achados


def mapa(con, cfg):
    """tudo o que o mapa precisa: a tua casa, a familia e os perigos reais por perto"""
    pontos = [{"tipo": "casa", "nome": "Casa", "lat": float(cfg["lat"]), "lon": float(cfg["lon"])}] if cfg.get("lat") else []
    for p in listar(con):
        if p.get("lat") is not None:
            pg = perigos(p["lat"], p["lon"])
            alerta = bool(pg["fogos"] or pg["sismos"] or any(a["nivel"] in ("laranja", "vermelho") for a in (pg["avisos"] or [])))
            pontos.append({"tipo": "familia", "id": p["id"], "nome": f"{p['relacao']} {p['nome']}".strip(), "lat": p["lat"], "lon": p["lon"], "alerta": alerta})
    fogos, sismos, fogos_erro = [], [], None
    try:
        d = avisos._json(avisos.FOGOS, 300)
        for f in d.get("data", d if isinstance(d, list) else []):
            try:
                fogos.append({"lat": float(f["lat"]), "lon": float(f["lng"]), "onde": f.get("location", "")})
            except (KeyError, TypeError, ValueError):
                pass
    except avisos.SemChave as e:
        fogos, fogos_erro = None, str(e)
    except Exception:
        fogos = None
    try:
        for f in avisos._json(avisos.USGS).get("features", []):
            x, y = f["geometry"]["coordinates"][:2]
            if 30 < y < 44 and -33 < x < -5:   # Portugal continental, Madeira e Acores
                sismos.append({"lat": y, "lon": x, "mag": f["properties"].get("mag") or 0})
    except Exception:
        sismos = None
    try:
        distritos = avisos.avisos_distritos()
    except Exception:
        distritos = None
    try:
        vento = avisos.vento()
    except Exception:
        vento = None
    # apagao: so sabemos o da TUA casa (o tablet deixou de carregar). Para outras casas nao ha dados abertos fiaveis.
    en = avisos.estado_energia()
    for p in pontos:
        if p["tipo"] == "casa":
            p["sem_luz"] = en["sem_luz"]; p["sem_luz_desde"] = en["desde"]; p["sem_internet"] = en["sem_internet"]
    return {"pontos": pontos, "fogos": fogos, "fogos_erro": fogos_erro, "sismos": sismos, "distritos": distritos, "vento": vento}


def vigiar(db, avisar):
    """thread: de 15 em 15 minutos ve se apareceu algum perigo novo perto da casa de algum familiar"""
    ja = set()

    def ciclo():
        time.sleep(60)
        while True:
            try:
                with db() as con:
                    ps = [p for p in listar(con) if p.get("lat") is not None]
                for p in ps:
                    pg = perigos(p["lat"], p["lon"])
                    quem, de = f"{p['relacao']} {p['nome']}".strip(), "d" + com_artigo(p)
                    for f in pg["fogos"] or []:
                        k = ("fogo", p["id"], f["onde"])
                        if k not in ja:
                            ja.add(k); avisar(f"Incêndio a {f['km']} km da casa {de} ({f['onde']}).",
                                              f"Atenção: segundo a Proteção Civil, há um incêndio a {f['km']} quilómetros da casa {de}.")
                    for a in pg["avisos"] or []:
                        k = ("aviso", p["id"], a["tipo"], a["nivel"], date.today().isoformat())
                        if a["nivel"] in ("laranja", "vermelho") and k not in ja:
                            ja.add(k); avisar(f"Aviso {a['nivel']} de {a['tipo'].lower()} na zona {de}.",
                                              f"Segundo o IPMA, há aviso {a['nivel']} de {a['tipo'].lower()} na zona {de}.")
                    for s in pg["sismos"] or []:
                        k = ("sismo", p["id"], s["hora"], s["mag"])
                        if s["mag"] >= 4 and s["km"] <= 150 and k not in ja:
                            ja.add(k); avisar(f"Sismo de {s['mag']} a {s['km']} km {de}.", f"Segundo o USGS, houve um sismo de {s['mag']} a {s['km']} quilómetros da casa {de}.")
            except Exception as e:
                print("familia:", e)
            time.sleep(15 * 60)
    threading.Thread(target=ciclo, daemon=True).start()


def _noticias_locais(cidade, n=5):
    """noticias recentes que falam da terra (Google Noticias); cada uma com o nome do jornal que a escreveu"""
    import re
    import xml.etree.ElementTree as ET
    import noticias
    q = urllib.parse.quote(f'"{cidade}"')
    raiz = ET.fromstring(noticias._buscar(f"https://news.google.com/rss/search?q={q}+when:3d&hl=pt-PT&gl=PT&ceid=PT:pt-150"))
    out = []
    for it in raiz.findall(".//item")[:n]:
        fonte = (it.findtext("source") or "").strip()
        titulo = (it.findtext("title") or "").strip()
        if fonte and titulo.endswith(" - " + fonte):
            titulo = titulo[: -len(fonte) - 3]
        out.append({"titulo": re.sub(r"\s+", " ", titulo), "fonte": fonte or "Google Notícias", "link": it.findtext("link") or "",
                    "quando": (it.findtext("pubDate") or "")[5:16]})
    return out


def detalhe(con, pid):
    """tudo o que se passa agora na terra de um familiar, cada parte com a fonte. Se uma fonte falhar, fica None."""
    p = next((x for x in listar(con) if x["id"] == pid), None)
    if not p:
        return None
    r = {"pessoa": p}
    if p.get("lat") is None:
        return r
    lat, lon = p["lat"], p["lon"]
    try:
        m = avisos._json(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                         "&current=temperature_2m,apparent_temperature,weather_code,is_day,wind_speed_10m,wind_gusts_10m,wind_direction_10m,precipitation"
                         "&hourly=temperature_2m,precipitation_probability,weather_code&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"
                         "&timezone=auto&forecast_days=2", 900)
        agora = m["current"]["time"][:13]
        k = next((i for i, t in enumerate(m["hourly"]["time"]) if t[:13] >= agora), 0)
        r["tempo"] = {"atual": m["current"], "horas": [{"h": m["hourly"]["time"][i][11:13], "temp": m["hourly"]["temperature_2m"][i],
                                                        "chuva": m["hourly"]["precipitation_probability"][i], "codigo": m["hourly"]["weather_code"][i]}
                                                       for i in range(k, min(k + 12, len(m["hourly"]["time"])))],
                      "dias": [{"max": m["daily"]["temperature_2m_max"][i], "min": m["daily"]["temperature_2m_min"][i],
                                "chuva": m["daily"]["precipitation_probability_max"][i], "nascer": m["daily"]["sunrise"][i][11:16],
                                "por": m["daily"]["sunset"][i][11:16]} for i in range(len(m["daily"]["time"]))]}
    except Exception:
        r["tempo"] = None
    try:
        r["avisos"] = avisos.avisos_ipma(lat, lon)
    except Exception:
        r["avisos"] = None
    try:
        f = avisos.incendios(lat, lon)
        r["fogos"] = f["perto"]
    except avisos.SemChave as e:
        r["fogos"], r["fogos_erro"] = None, str(e)
    except Exception:
        r["fogos"] = None
    try:
        r["sismos"] = [x for x in avisos.sismos(lat, lon)["perto"] if x["km"] <= 300]
    except Exception:
        r["sismos"] = None
    try:
        r["noticias"] = _noticias_locais(p["cidade"]) if p.get("cidade") else []
    except Exception:
        r["noticias"] = None
    try:
        c = {k: v for k, v in con.execute("SELECT chave, valor FROM config WHERE chave IN ('lat', 'lon')")}
        r["km_de_casa"] = round(avisos.km(float(c["lat"]), float(c["lon"]), lat, lon))
    except Exception:
        r["km_de_casa"] = None
    return r


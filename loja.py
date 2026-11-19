"""
A loja Shopify na central: vendas, encomendas por enviar e LUCRO REAL (vendas - reembolsos - custo dos
produtos - taxas - anuncios e outras despesas).

- Usa a Admin API (GraphQL) com permissoes SO DE LEITURA (read_orders, read_products, read_inventory).
- Duas formas de ligar:
  * app do Dev Dashboard (a unica possivel desde 1/1/2026): Client ID + Client secret. A central pede sozinha
    uma chave com o "client credentials grant" (POST /admin/oauth/access_token), que dura 24 h, e pede outra antes de acabar.
    So funciona se a app e a loja forem da mesma organizacao na Shopify.
  * app personalizada antiga (criada antes de 2026 no admin da loja): a chave shpat_ continua a funcionar.
- Nao pede nomes, emails nem moradas dos clientes: so numeros e produtos.
- A chave fica em loja_token.json (fora do GitHub, so o Termux a le).
- O custo de cada produto vem do campo "Custo por artigo" da Shopify. Se nao estiver preenchido, avisa.
- As despesas (anuncios, apps, mensalidade) metem-se a mao ou por voz: "gastei 15 euros em anuncios".
"""

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

TOKEN = Path(__file__).resolve().parent / "loja_token.json"
VERSAO = os.environ.get("SHOPIFY_VERSAO", "2026-10")   # a Shopify suporta cada versao cerca de 12 meses: atualizar 1 vez por ano
BASE = os.environ.get("SHOPIFY_BASE")   # so para testes: substitui https://LOJA.myshopify.com

TABELAS = """
CREATE TABLE IF NOT EXISTS despesas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    descricao TEXT NOT NULL,
    valor REAL NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'anuncios'      -- anuncios, apps, mensalidade, outro
);
"""


class ErroLoja(Exception):
    pass


def configurada():
    return TOKEN.exists()


_chave = {"token": None, "expira": 0}   # a chave de 24 h do Dev Dashboard (so em memoria)
_lock = threading.Lock()


def guardar(dominio, token="", taxa_pct=2.9, taxa_fixa=0.30, client_id="", client_secret=""):
    dominio = dominio.strip().lower().replace("https://", "").replace("http://", "").strip("/")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", dominio):
        raise ErroLoja("o domínio tem de ser do tipo a-tua-loja.myshopify.com")
    token, client_id, client_secret = token.strip(), client_id.strip(), client_secret.strip()
    d = {"dominio": dominio, "taxa_pct": float(taxa_pct), "taxa_fixa": float(taxa_fixa)}
    if client_id or client_secret:
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", client_id):
            raise ErroLoja("o Client ID não parece certo (copia-o do Dev Dashboard > a tua app > Settings)")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,200}", client_secret):
            raise ErroLoja("o Client secret não parece certo (no mesmo sítio que o Client ID)")
        d.update(client_id=client_id, client_secret=client_secret)
    elif re.fullmatch(r"shpat_[A-Za-z0-9]{20,}", token):
        d["token"] = token
    else:
        raise ErroLoja("mete o Client ID e o Client secret da app do Dev Dashboard (ou a chave antiga shpat_)")
    with _lock:
        _chave.update(token=None, expira=0)
    TOKEN.write_text(json.dumps(d))
    try:
        os.chmod(TOKEN, 0o600)
    except OSError:
        pass


def apagar():
    TOKEN.unlink(missing_ok=True)
    with _lock:
        _chave.update(token=None, expira=0)


def _chave_acesso(c, nova=False):
    """a chave que vai no cabecalho X-Shopify-Access-Token"""
    if c.get("token"):                       # app antiga: chave fixa
        return c["token"]
    with _lock:
        if not nova and _chave["token"] and time.time() < _chave["expira"]:
            return _chave["token"]
        url = f"{BASE or 'https://' + c['dominio']}/admin/oauth/access_token"
        corpo = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": c["client_id"], "client_secret": c["client_secret"]}).encode()
        req = urllib.request.Request(url, data=corpo, headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read())
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "ignore")
            if "shop_not_permitted" in txt:
                raise ErroLoja("a Shopify não deixa esta app ligar-se a esta loja: a app tem de ser criada na mesma organização da loja (Dev Dashboard)")
            if e.code in (400, 401, 403):
                raise ErroLoja("a Shopify recusou o Client ID e o Client secret (estão certos? a app está instalada na loja?)")
            raise ErroLoja(f"a Shopify deu erro {e.code} ao pedir a chave")
        except urllib.error.URLError:
            raise ErroLoja("sem ligação à Shopify")
        if not d.get("access_token"):
            raise ErroLoja("a Shopify não deu a chave")
        _chave.update(token=d["access_token"], expira=time.time() + int(d.get("expires_in", 86399)) - 120)   # pede outra 2 min antes
        return _chave["token"]


def _cfg():
    if not TOKEN.exists():
        raise ErroLoja("ainda não ligaste a loja (modo Iron Man > painel Loja)")
    return json.loads(TOKEN.read_text())


def _gql(query, variaveis=None, outra_vez=True):
    c = _cfg()
    url = f"{BASE or 'https://' + c['dominio']}/admin/api/{VERSAO}/graphql.json"
    req = urllib.request.Request(url, data=json.dumps({"query": query, "variables": variaveis or {}}).encode(),
                                 headers={"Content-Type": "application/json", "X-Shopify-Access-Token": _chave_acesso(c)})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 401 and outra_vez and not c.get("token"):   # a chave de 24 h acabou antes do previsto: pede outra
            _chave_acesso(c, nova=True)
            return _gql(query, variaveis, outra_vez=False)
        if e.code in (401, 403):
            raise ErroLoja("a Shopify recusou a chave (está certa? tem as permissões read_orders e read_products?)")
        raise ErroLoja(f"a Shopify deu erro {e.code}")
    except urllib.error.URLError:
        raise ErroLoja("sem ligação à Shopify")
    if d.get("errors"):
        msg = str(d["errors"])[:200]
        if "access" in msg.lower() or "scope" in msg.lower():
            raise ErroLoja("falta uma permissão à chave da Shopify (read_orders, read_products, read_inventory)")
        raise ErroLoja("a Shopify não percebeu o pedido")
    return d["data"]


Q_ENCOMENDAS = """
query($q: String!, $depois: String) {
  orders(first: 100, after: $depois, query: $q, sortKey: CREATED_AT, reverse: true) {
    pageInfo { hasNextPage endCursor }
    nodes {
      name createdAt cancelledAt displayFinancialStatus displayFulfillmentStatus
      totalPriceSet { shopMoney { amount currencyCode } }
      totalRefundedSet { shopMoney { amount } }
      lineItems(first: 30) { nodes { title quantity variant { inventoryItem { unitCost { amount } } } } }
    }
  }
}"""


def encomendas(desde):
    out, depois = [], None
    for _ in range(10):  # no maximo 1000 encomendas
        d = _gql(Q_ENCOMENDAS, {"q": f"created_at:>={desde.isoformat()}", "depois": depois})["orders"]
        out += d["nodes"]
        if not d["pageInfo"]["hasNextPage"]:
            break
        depois = d["pageInfo"]["endCursor"]
    return out


def _periodo(nome):
    hoje = date.today()
    if nome == "hoje":
        return hoje, "hoje"
    if nome == "ontem":
        return hoje - timedelta(days=1), "ontem"
    if nome == "semana":
        return hoje - timedelta(days=hoje.weekday()), "esta semana"
    return hoje.replace(day=1), "este mês"


def resumo(con, periodo="hoje"):
    c = _cfg()
    desde, nome = _periodo(periodo)
    ate = desde if periodo == "ontem" else None
    ords = [o for o in encomendas(desde) if not o.get("cancelledAt")]
    if ate:
        ords = [o for o in ords if o["createdAt"][:10] == ate.isoformat()]
    moeda = ords[0]["totalPriceSet"]["shopMoney"]["currencyCode"] if ords else "EUR"
    receita = sum(float(o["totalPriceSet"]["shopMoney"]["amount"]) for o in ords)
    reembolsos = sum(float(o["totalRefundedSet"]["shopMoney"]["amount"]) for o in ords)
    custo, sem_custo, vendidos = 0.0, set(), {}
    for o in ords:
        for li in o["lineItems"]["nodes"]:
            vendidos[li["title"]] = vendidos.get(li["title"], 0) + li["quantity"]
            uc = (((li.get("variant") or {}).get("inventoryItem") or {}).get("unitCost") or {}).get("amount")
            if uc is None:
                sem_custo.add(li["title"])
            else:
                custo += float(uc) * li["quantity"]
    taxas = sum(float(o["totalPriceSet"]["shopMoney"]["amount"]) * c["taxa_pct"] / 100 + c["taxa_fixa"] for o in ords)
    q = "SELECT COALESCE(SUM(valor), 0) FROM despesas WHERE data >= ?" + (" AND data <= ?" if ate else "")
    despesas = con.execute(q, (desde.isoformat(),) + ((ate.isoformat(),) if ate else ())).fetchone()[0]
    lucro = receita - reembolsos - custo - taxas - despesas
    por_enviar = [o["name"] for o in ords if o["displayFulfillmentStatus"] in ("UNFULFILLED", "PARTIALLY_FULFILLED")]
    return {"periodo": nome, "moeda": moeda, "encomendas": len(ords), "receita": round(receita, 2), "reembolsos": round(reembolsos, 2),
            "custo_produtos": round(custo, 2), "taxas": round(taxas, 2), "despesas": round(despesas, 2), "lucro": round(lucro, 2),
            "sem_custo": sorted(sem_custo), "por_enviar": por_enviar,
            "mais_vendidos": sorted(vendidos.items(), key=lambda x: -x[1])[:3]}


def euros(v):
    inteiro, dec = f"{abs(v):.2f}".split(".")
    return ("menos " if v < 0 else "") + (f"{inteiro} euros" if dec == "00" else f"{inteiro} euros e {int(dec)} cêntimos")


def frase(r):
    if r["encomendas"] == 0:
        f = f"{r['periodo'].capitalize()} ainda não houve encomendas."
        if r["despesas"]:
            f += f" Gastaste {euros(r['despesas'])} em despesas, por isso estás a {euros(-r['despesas'])}."
        return f
    f = (f"{r['periodo'].capitalize()}: {r['encomendas']} encomenda{'s' if r['encomendas'] > 1 else ''}, "
         f"{euros(r['receita'])} em vendas, e o lucro real é de {euros(r['lucro'])}.")
    if r["lucro"] < 0:
        f += " Estás a perder dinheiro: vê os anúncios e o custo dos produtos."
    if r["por_enviar"]:
        f += f" Tens {len(r['por_enviar'])} por enviar."
    if r["sem_custo"]:
        f += " Atenção: há produtos sem custo preenchido na Shopify, por isso o lucro está a contar por cima."
    return f


# ---------- avisar de encomendas novas ----------

def vigiar(avisar):
    """thread: de 2 em 2 minutos ve se ha encomendas novas"""
    vistas = {"nomes": None}   # as encomendas que ja vimos (pelo numero, ex.: #1003)

    def ciclo():
        while True:
            try:
                if configurada():
                    ords = encomendas(date.today() - timedelta(days=2))
                    nomes = {o["name"] for o in ords}
                    if vistas["nomes"] is None:
                        vistas["nomes"] = nomes                     # ao arrancar nao avisa das antigas
                    else:
                        for o in reversed([o for o in ords if o["name"] not in vistas["nomes"]]):
                            valor = float(o["totalPriceSet"]["shopMoney"]["amount"])
                            avisar(f"Nova encomenda {o['name']}: {valor:.2f} €".replace(".", ","), f"Nova encomenda! {euros(valor)}.")
                        vistas["nomes"] |= nomes
            except Exception as e:
                print("loja:", e)
            time.sleep(float(os.environ.get("LOJA_INTERVALO", 120)))
    threading.Thread(target=ciclo, daemon=True).start()

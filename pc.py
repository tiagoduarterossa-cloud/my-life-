"""
"Jarvis, abre o YouTube" / "abre o Spotify" / "pesquisa gatos no YouTube": abre programas e sites no PC.

So funciona com a central a correr num PC com Windows, e so para pedidos feitos NO PROPRIO PC (127.0.0.1):
um telemovel ou outra pessoa na rede nao abre nada no teu PC.
So abre o que esta nesta lista (e sites com endereco, ex.: "abre o site wikipedia.org"): nunca corre comandos
inventados, nem fecha, apaga ou instala nada.
Os programas abrem-se pelos "protocolos" do Windows (spotify:, msteams:, ms-word:...): se o programa nao estiver
instalado, o Windows diz que nao sabe abrir. Quando a central for para o PC velho, isto precisa de um pequeno
programa no teu PC (o servidor ja nao esta ao pe de ti).
"""

import os
import re
import urllib.parse
import webbrowser

# nome (como se diz, sem acentos) -> (nome bonito, o que abrir)
APPS = {
    "spotify": ("Spotify", "spotify:"),
    "teams": ("Teams", "msteams:"),
    "discord": ("Discord", "discord:"),
    "steam": ("Steam", "steam://open/main"),
    "whatsapp": ("WhatsApp", "whatsapp:"),
    "word": ("Word", "ms-word:"),
    "excel": ("Excel", "ms-excel:"),
    "powerpoint": ("PowerPoint", "ms-powerpoint:"),
    "calculadora": ("Calculadora", "calculator:"),
    "definicoes do windows": ("Definições do Windows", "ms-settings:"),
    "camara do windows": ("Câmara", "microsoft.windows.camera:"),
    "paint": ("Paint", "ms-paint:"),
    "loja do windows": ("Microsoft Store", "ms-windows-store:"),
    "vs code": ("VS Code", "vscode:"),
    "visual studio code": ("VS Code", "vscode:"),
    "bloco de notas": ("Bloco de Notas", "notepad.exe"),
    "explorador": ("Explorador de Ficheiros", "explorer.exe"),
    "ficheiros": ("Explorador de Ficheiros", "explorer.exe"),
}
SITES = {
    "youtube": ("YouTube", "https://www.youtube.com"),
    "google": ("Google", "https://www.google.com"),
    "gmail": ("Gmail", "https://mail.google.com"),
    "email": ("Gmail", "https://mail.google.com"),
    "mail": ("Gmail", "https://mail.google.com"),
    "tiktok": ("TikTok", "https://www.tiktok.com"),
    "instagram": ("Instagram", "https://www.instagram.com"),
    "github": ("GitHub", "https://github.com"),
    "claude": ("Claude", "https://claude.ai"),
    "shopify": ("Shopify", "https://admin.shopify.com"),
    "loja online": ("Shopify", "https://admin.shopify.com"),
    "whatsapp web": ("WhatsApp Web", "https://web.whatsapp.com"),
    "netflix": ("Netflix", "https://www.netflix.com"),
    "wikipedia": ("Wikipédia", "https://pt.wikipedia.org"),
    "google maps": ("Google Maps", "https://www.google.com/maps"),
    "maps": ("Google Maps", "https://www.google.com/maps"),
    "tradutor": ("Google Tradutor", "https://translate.google.com/?sl=auto&tl=pt"),
    "drive": ("Google Drive", "https://drive.google.com"),
    "teams web": ("Teams", "https://teams.microsoft.com"),
    "outlook": ("Outlook", "https://outlook.live.com"),
    "twitch": ("Twitch", "https://www.twitch.tv"),
}
PESQUISAS = {
    "youtube": ("YouTube", "https://www.youtube.com/results?search_query={}"),
    "google": ("Google", "https://www.google.com/search?q={}"),
    "spotify": ("Spotify", "spotify:search:{}"),
    "wikipedia": ("Wikipédia", "https://pt.wikipedia.org/w/index.php?search={}"),
    "maps": ("Google Maps", "https://www.google.com/maps/search/{}"),
    "google maps": ("Google Maps", "https://www.google.com/maps/search/{}"),
    "amazon": ("Amazon", "https://www.amazon.es/s?k={}"),
}
DOMINIO = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.(pt|com|org|net|io|ai|eu|gov|edu|tv|app|dev|me|co)(/\S*)?$")


def alvo_de(nome):
    """'o youtube' -> ('YouTube', url) ou None. Aceita tambem 'o site x.pt'."""
    n = re.sub(r"^(o|a|os|as|me|-me)\s+", "", nome.strip(" .!?")).strip()
    n = re.sub(r"\s+(por favor|pf|se faz favor|no pc|no computador|aqui)$", "", n).strip()
    n = re.sub(r"^(app|aplicacao|programa|site|pagina)\s+(do |da |de )?", "", n).strip()
    for tab in (APPS, SITES):
        if n in tab:
            return tab[n]
    d = n.replace(" ponto ", ".").replace(" ", "")
    if DOMINIO.match(d):
        return d, "https://" + d
    return None


def pesquisa_de(onde, termo):
    onde = onde.strip()
    if onde not in PESQUISAS or not termo.strip():
        return None
    nome, url = PESQUISAS[onde]
    return nome, url.format(urllib.parse.quote(termo.strip()))


def disponivel():
    return os.name == "nt"


def abrir(url):
    """abre no PC (so Windows). Devolve (ok, mensagem de erro)"""
    if not disponivel():
        return False, "Abrir programas e sites só funciona com o Jarvis a correr no PC com Windows."
    try:
        if url.startswith(("http://", "https://")):
            webbrowser.open(url)
        else:
            os.startfile(url)      # protocolos do Windows (spotify:, ms-word:...) e programas do sistema
        return True, ""
    except OSError:
        return False, "O Windows não conseguiu abrir isso. Se calhar o programa não está instalado."

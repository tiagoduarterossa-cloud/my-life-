#!/data/data/com.termux/files/usr/bin/bash
# Instala (ou repara) tudo o que a central precisa no Termux. Pode correr-se as vezes que quiseres.
# Uso:  cd ~/central && ./instalar.sh
cd "$(dirname "$0")"
PASTA="$(pwd)"
ok()   { echo "  ✔ $1"; }
aviso(){ echo "  ⚠ $1"; }

echo "1/7 Pacotes do Termux (pode demorar uns minutos)..."
pkg install -y python git python-numpy python-pillow termux-api >/dev/null 2>&1 && ok "pacotes instalados" || aviso "alguns pacotes falharam: corre 'pkg update' e repete"
git config --global core.pager cat

echo "2/7 Voz neural (Duarte/Raquel)..."
if python -c "import edge_tts" 2>/dev/null; then ok "já estava instalada"
elif pip install --quiet edge-tts 2>/dev/null; then ok "instalada"
elif pkg install -y python-aiohttp >/dev/null 2>&1 && pip install --quiet edge-tts 2>/dev/null; then ok "instalada"
else aviso "não instalou. A central usa a voz do tablet."; fi

echo "3/7 Termux:API (som do alarme com o ecrã apagado)..."
if command -v termux-media-player >/dev/null && timeout 8 termux-battery-status >/dev/null 2>&1; then ok "a funcionar"
else aviso "falta a app Termux:API do F-Droid (e dar-lhe bateria 'Não restringida')"; fi

echo "4/7 Acesso aos ficheiros do tablet..."
if [ -d "$HOME/storage" ]; then ok "já tinha acesso"; else termux-setup-storage; aviso "carrega em Permitir no ecrã"; fi

echo "5/7 Arranque automático..."
mkdir -p "$HOME/.termux/boot"
printf '#!/data/data/com.termux/files/usr/bin/bash\n%s/iniciar.sh\n' "$PASTA" > "$HOME/.termux/boot/central.sh"
chmod +x "$HOME/.termux/boot/central.sh" iniciar.sh atualizar.sh instalar.sh 2>/dev/null
ok "a central arranca sozinha quando o tablet liga (abre a app Termux:Boot uma vez)"

echo "6/7 Horário das aulas..."
python importar_horario.py | sed 's/^/  /'

echo "7/7 A arrancar a central..."
pkill -f "python server.py" 2>/dev/null; sleep 1
echo
echo "Pronto. Para parar: Ctrl+C. Para atualizar no futuro: ./atualizar.sh"
echo
exec ./iniciar.sh

#!/data/data/com.termux/files/usr/bin/bash
# Vai buscar a versao mais recente da central ao GitHub e reinicia o servidor.
# Uso:  cd ~/central && ./atualizar.sh
cd "$(dirname "$0")"
git config --global core.pager cat
echo "A atualizar..."
if ! git pull; then
  echo "O git pull falhou. Se o repositorio for privado, confirma o token."; exit 1
fi
chmod +x iniciar.sh atualizar.sh instalar.sh 2>/dev/null
python -c "import edge_tts" 2>/dev/null || pip install --quiet edge-tts 2>/dev/null
pkill -f "python server.py" 2>/dev/null; sleep 1
echo "A reiniciar a central..."
exec ./iniciar.sh

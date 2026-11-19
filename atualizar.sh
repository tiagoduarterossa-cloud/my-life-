#!/data/data/com.termux/files/usr/bin/bash
# Vai buscar a versao mais recente da central ao GitHub e reinicia o servidor.
# Uso:  cd ~/central && ./atualizar.sh
cd "$(dirname "$0")"
git config --global core.pager cat
echo "A atualizar..."
if ! git pull; then
  echo "O git pull falhou. Se o repositorio for privado, confirma o token."; exit 1
fi
chmod +x iniciar.sh atualizar.sh instalar.sh instalar_claude.sh 2>/dev/null
python -c "import edge_tts" 2>/dev/null || pip install --quiet edge-tts 2>/dev/null
# a pesquisa na web do Claude precisa do SDK 1.1.0 ou mais recente (retoma sozinho as pesquisas longas)
if python -c "import anthropic" 2>/dev/null; then pip install --quiet --upgrade "anthropic>=1.1.0" 2>/dev/null; fi
pkill -f "python server.py" 2>/dev/null; sleep 1
echo "A reiniciar a central..."
exec ./iniciar.sh

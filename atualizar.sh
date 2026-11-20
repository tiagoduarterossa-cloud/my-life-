#!/data/data/com.termux/files/usr/bin/bash
# Vai buscar a versao mais recente da central ao GitHub e reinicia o servidor.
# Uso:  cd ~/central && ./atualizar.sh
# tudo dentro de { }: o bash le o script inteiro antes de comecar, porque o git pull pode muda-lo a meio
{
cd "$(dirname "$0")"
git config --global core.pager cat
echo "A atualizar..."
ANTES=$(git rev-parse HEAD)
if ! git pull; then
  echo "O git pull falhou. Se o repositorio for privado, confirma o token."; exit 1
fi
# testes do Jarvis: se a versao nova estragar alguma frase, volta a versao que estava a funcionar
if ! python testes/correr.py; then
  if [ "$(git rev-parse HEAD)" != "$ANTES" ]; then
    echo "Os testes falharam: volto a versao que estava a funcionar. Manda uma foto deste ecra."
    git reset --hard "$ANTES"
  else
    echo "Os testes falharam nesta versao. Manda uma foto deste ecra."
  fi
fi
chmod +x iniciar.sh atualizar.sh instalar.sh instalar_claude.sh 2>/dev/null
python -c "import edge_tts" 2>/dev/null || pip install --quiet edge-tts 2>/dev/null
# a pesquisa na web do Claude precisa do SDK 1.1.0 ou mais recente (retoma sozinho as pesquisas longas)
if python -c "import anthropic" 2>/dev/null; then pip install --quiet --upgrade "anthropic>=1.1.0" 2>/dev/null; fi
pkill -f "python server.py" 2>/dev/null; sleep 1
echo "A reiniciar a central..."
exec ./iniciar.sh
exit
}

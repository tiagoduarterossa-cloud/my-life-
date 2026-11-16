#!/data/data/com.termux/files/usr/bin/bash
# Instala a biblioteca oficial do Claude no Termux. Algumas partes tem de ser compiladas no tablet,
# por isso pode demorar 10 a 30 minutos na primeira vez. Deixa o tablet ligado a corrente.
cd "$(dirname "$0")"
if python -c "import anthropic" 2>/dev/null; then echo "Já está instalada."; exit 0; fi
echo "1/2 A tentar instalar diretamente..."
if pip install anthropic; then echo "Instalada!"; exit 0; fi
echo "2/2 Faltam ferramentas para compilar. A instalar o Rust (demora)..."
pkg install -y rust binutils clang make
if pip install anthropic; then echo "Instalada! Corre ./atualizar.sh para reiniciar a central."
else echo "Não consegui. Manda um print do erro."; exit 1; fi

#!/data/data/com.termux/files/usr/bin/bash
# Arranca a central e impede o Android de adormecer o Termux.
cd "$(dirname "$0")"
termux-wake-lock 2>/dev/null
python server.py

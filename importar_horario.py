#!/usr/bin/env python3
"""
Mete o horario das aulas do 8.o ano na central, de uma so vez.
Correr uma vez no Termux:  python importar_horario.py
Se correres outra vez, nao duplica as aulas que ja la estao.
"""
import server

# (dia, inicio, fim, disciplina)   dia: 0 segunda ... 4 sexta
AULAS = [
    (0, "08:50", "10:30", "História"),
    (0, "10:50", "12:30", "Inglês"),
    (0, "12:40", "13:30", "Matemática"),
    (0, "14:30", "16:10", "Físico-Química"),

    (1, "08:50", "10:30", "Educação Visual"),
    (1, "10:50", "12:30", "Português"),
    (1, "12:40", "13:30", "Ciências Naturais"),
    (1, "14:30", "16:10", "Espanhol"),

    (2, "08:50", "09:40", "TIC"),
    (2, "09:40", "10:30", "Físico-Química"),
    (2, "10:50", "12:30", "Educação Física"),
    (2, "12:40", "13:30", "Português"),

    (3, "08:50", "10:30", "Matemática"),
    (3, "10:50", "12:30", "Português"),
    (3, "12:40", "13:30", "AD"),
    (3, "14:30", "16:10", "Geografia"),

    (4, "08:50", "09:40", "Inglês"),
    (4, "09:40", "10:30", "Educação Física"),
    (4, "10:50", "12:30", "Ciências Naturais"),
    (4, "12:40", "13:30", "Cidadania e Desenvolvimento"),
    (4, "14:30", "16:10", "Matemática"),
]

server.init_db()
novas = 0
with server.db() as con:
    for dia, ini, fim, nome in AULAS:
        existe = con.execute("SELECT 1 FROM horario WHERE dia=? AND inicio=? AND titulo=?", (dia, ini, nome)).fetchone()
        if not existe:
            con.execute("INSERT INTO horario (dia, inicio, fim, titulo, area) VALUES (?,?,?,?, 'escola')", (dia, ini, fim, nome))
            novas += 1
print(f"Pronto: {novas} aulas novas no horario ({len(AULAS) - novas} ja estavam).")

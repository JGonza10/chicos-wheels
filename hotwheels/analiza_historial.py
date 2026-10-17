# -*- coding: utf-8 -*-
"""
Reporte del historial del monitor de Hot Wheels.

Contesta con datos tuyos las preguntas que de verdad importan:
  - Que dia y a que hora caen los drops (no lo que se supone, lo que pasa).
  - Que autos se agotan mas rapido.
  - Cuales se resurten seguido (esos si se alcanzan en el segundo intento).
  - Cuales dejaron mas ganancia estimada.

Uso:
    python3 analiza_historial.py            # ultimos 90 dias
    python3 analiza_historial.py 30         # ultimos 30 dias
"""

import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta

DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_DB = os.path.join(DIR, "historial.db")

DIAS_NOMBRE = {0: "Lunes", 1: "Martes", 2: "Miercoles", 3: "Jueves",
               4: "Viernes", 5: "Sabado", 6: "Domingo"}


def titulo(texto):
    print()
    print(texto)
    print("-" * len(texto))


def main():
    dias = int(sys.argv[1]) if len(sys.argv) > 1 else 90

    if not os.path.exists(RUTA_DB):
        print("Todavia no hay historial (%s no existe)." % RUTA_DB)
        print("Se va llenando solo conforme el monitor manda avisos.")
        return

    conn = sqlite3.connect(RUTA_DB)
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()

    total = conn.execute("SELECT COUNT(*) FROM eventos WHERE ts_utc >= ?",
                         (desde,)).fetchone()[0]

    print("=" * 62)
    print("  HISTORIAL DEL MONITOR — ultimos %d dias" % dias)
    print("  %d eventos registrados" % total)
    print("=" * 62)

    if total == 0:
        print("\nSin datos en ese periodo. Prueba con mas dias:")
        print("    python3 analiza_historial.py 365")
        return

    titulo("Que tanto pasa de cada cosa")
    for tipo, n in conn.execute(
            "SELECT tipo, COUNT(*) FROM eventos WHERE ts_utc >= ? "
            "GROUP BY tipo ORDER BY COUNT(*) DESC", (desde,)):
        print("  %-24s %4d" % (tipo, n))

    titulo("Que dia caen los productos nuevos")
    filas = conn.execute(
        "SELECT dia_semana, COUNT(*) FROM eventos WHERE ts_utc >= ? "
        "AND tipo IN ('nuevo','proximamente') GROUP BY dia_semana "
        "ORDER BY COUNT(*) DESC", (desde,)).fetchall()
    if filas:
        mayor = filas[0][1]
        for dia, n in filas:
            barra = "#" * int(round(20.0 * n / mayor))
            print("  %-10s %-21s %3d" % (DIAS_NOMBRE.get(dia, dia), barra, n))
    else:
        print("  (aun sin datos)")

    titulo("A que hora caen (hora de Mexico)")
    filas = conn.execute(
        "SELECT hora_mx, COUNT(*) FROM eventos WHERE ts_utc >= ? "
        "AND tipo IN ('nuevo','proximamente') GROUP BY hora_mx "
        "ORDER BY COUNT(*) DESC LIMIT 8", (desde,)).fetchall()
    if filas:
        mayor = filas[0][1]
        for hora, n in filas:
            barra = "#" * int(round(20.0 * n / mayor))
            print("  %02d:00      %-21s %3d" % (hora, barra, n))
    else:
        print("  (aun sin datos)")

    titulo("Los que se agotaron mas rapido")
    filas = conn.execute(
        "SELECT titulo, minutos_agotamiento FROM eventos WHERE ts_utc >= ? "
        "AND minutos_agotamiento IS NOT NULL AND minutos_agotamiento > 0 "
        "ORDER BY minutos_agotamiento ASC LIMIT 15", (desde,)).fetchall()
    if filas:
        for t, m in filas:
            print("  %4d min  %s" % (m, (t or "")[:48]))
    else:
        print("  (aun sin datos)")

    titulo("Los que mas se resurten (esos si se alcanzan)")
    filas = conn.execute(
        "SELECT titulo, COUNT(*) FROM eventos WHERE ts_utc >= ? AND tipo = 'restock' "
        "GROUP BY producto_id ORDER BY COUNT(*) DESC LIMIT 12", (desde,)).fetchall()
    if filas:
        for t, n in filas:
            print("  %2d veces  %s" % (n, (t or "")[:48]))
    else:
        print("  (aun sin datos)")

    titulo("De tu lista de deseados")
    filas = conn.execute(
        "SELECT titulo, tipo, fecha_mx FROM eventos WHERE ts_utc >= ? AND deseado = 1 "
        "ORDER BY ts_utc DESC LIMIT 15", (desde,)).fetchall()
    if filas:
        for t, tipo, fecha in filas:
            print("  %s  %-14s %s" % (fecha, tipo, (t or "")[:40]))
    else:
        print("  (no ha aparecido nada de tu lista, o no has puesto deseados.txt)")

    titulo("Cuanto tarda en agotarse, por nivel de impacto")
    filas = conn.execute(
        "SELECT e2.impacto, COUNT(*), AVG(e1.minutos_agotamiento) "
        "FROM eventos e1 JOIN eventos e2 ON e1.producto_id = e2.producto_id "
        "WHERE e1.ts_utc >= ? AND e1.minutos_agotamiento > 0 "
        "AND e2.impacto IS NOT NULL GROUP BY e2.impacto "
        "ORDER BY AVG(e1.minutos_agotamiento) ASC", (desde,)).fetchall()
    if filas:
        for imp, n, prom in filas:
            print("  %-16s %4d casos  promedio %6.0f min" % (imp, n, prom or 0))
    else:
        print("  (aun sin datos)")

    print()
    print("Lectura rapida: el dia y la hora de arriba son tu calendario real de")
    print("drops. Si coinciden con lo que ya sabias, el monitor lo confirma; si")
    print("no, ahi tienes el ajuste que te faltaba.")
    conn.close()


if __name__ == "__main__":
    main()

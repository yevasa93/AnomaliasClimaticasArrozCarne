# -*- coding: utf-8 -*-
"""
Web scraping de la UPME - "Estructura de precio de los combustibles en las principales
ciudades". Descarga todos los archivos del botón "Consultar" entre ENERO 2013 y
SEPTIEMBRE 2026 (PDF los más antiguos, XLS/XLSX los más recientes).

Cómo funciona la página: el listado no está en el HTML como enlaces, sino en un arreglo
JavaScript embebido (`const proyectos = [ {TITULO, ANO, NOMBRE_ARCHIVO, URL}, ... ]`) que
el navegador pinta con paginación. El script lee ese arreglo directamente.

Requisitos:  pip install requests
Uso:         python descargar_estructura_precios_upme.py
             python descargar_estructura_precios_upme.py --forzar   # re-descarga todo

Salida (carpeta DESTINO):
    <nombre original del archivo>.pdf/.xls/.xlsx
    indice_descargas.csv  -> título, año, mes, archivo, URL y estado de cada informe
"""

import argparse
import csv
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote, unquote

import requests

# ----------------------------------------------------------------------------------
# CONFIGURACIÓN
# ----------------------------------------------------------------------------------
DESTINO = Path(
    r"C:\Users\yvs93\OneDrive\ESTUDIO\10. Maestria Ciencia de Datos"
    r"\Proyecto Aplicado\Proyecto Aplicado - Compartida\Data\raw_data\Precio ACPM-UPME"
)
URL_PAGINA = (
    "https://www.upme.gov.co/simec/hidrocarburos/combustibles-liquidos/"
    "estructura-de-precio-de-los-combustibles-en-las-principales-ciudades/"
)
DESDE = (2013, 1)   # (año, mes) inclusive
HASTA = (2026, 9)   # (año, mes) inclusive

HEADERS = {"User-Agent": "Mozilla/5.0 (descarga academica de datos publicos)"}
PAUSA_SEG = 1.0
REINTENTOS = 3

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


# ----------------------------------------------------------------------------------
def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def mes_desde_titulo(titulo: str):
    """'Enero - Agosto 2014' -> 1 ; 'Julio 6 2017' -> 7 ; 'Junio 2024 - Actualización' -> 6."""
    t = sin_tildes(titulo).lower()
    posiciones = [(t.find(n), m) for n, m in MESES.items() if re.search(rf"\b{n}\b", t)]
    return min(posiciones)[1] if posiciones else None


def leer_listado(sesion):
    """Descarga la página y extrae el arreglo JavaScript `proyectos`."""
    r = sesion.get(URL_PAGINA, timeout=60)
    r.raise_for_status()
    r.encoding = "utf-8"
    m = re.search(r"proyectos\s*=\s*(\[.*?\])\s*;", r.text, re.S)
    if not m:
        raise RuntimeError("No se encontró el arreglo 'proyectos' en la página; "
                           "es posible que la UPME haya cambiado su estructura.")
    texto = re.sub(r",\s*\]", "]", m.group(1))       # quita la coma final del JS
    return json.loads(texto)


def descargar(sesion, url, ruta):
    url_codificada = quote(url, safe=":/%?=&")         # los nombres traen espacios
    for intento in range(1, REINTENTOS + 1):
        try:
            r = sesion.get(url_codificada, timeout=120)
            if r.status_code == 200 and r.content and "text/html" not in r.headers.get("Content-Type", ""):
                ruta.write_bytes(r.content)
                return f"descargado ({len(r.content) / 1024:.0f} KB)"
            estado = f"HTTP {r.status_code} / {r.headers.get('Content-Type', '')}"
        except requests.RequestException as e:
            estado = f"error de red: {type(e).__name__}"
        time.sleep(2 * intento)
    return f"FALLÓ: {estado}"


def main(forzar=False):
    DESTINO.mkdir(parents=True, exist_ok=True)
    sesion = requests.Session()
    sesion.headers.update(HEADERS)

    listado = leer_listado(sesion)
    print(f"[pagina] {len(listado)} informes publicados en total.")

    seleccion = []
    for item in listado:
        anio, mes = int(item["ANO"]), mes_desde_titulo(item["TITULO"])
        if mes is None:
            print(f"  [aviso] no se pudo leer el mes de '{item['TITULO']}', se omite.")
            continue
        if DESDE <= (anio, mes) <= HASTA:
            seleccion.append((anio, mes, item))
    seleccion.sort(key=lambda x: (x[0], x[1], x[2]["NOMBRE_ARCHIVO"]))
    print(f"[filtro] {len(seleccion)} archivos entre {DESDE[1]:02d}/{DESDE[0]} "
          f"y {HASTA[1]:02d}/{HASTA[0]}.\n")

    registro = []
    for anio, mes, item in seleccion:
        # El nombre se toma de la URL: el campo NOMBRE_ARCHIVO de la UPME a veces está
        # mal (p. ej. 'Julio 2026' figura como 'Estructura_precios_junio_2026.xlsx').
        ruta = DESTINO / unquote(item["URL"].rstrip("/").rsplit("/", 1)[-1])
        if ruta.exists() and ruta.stat().st_size > 0 and not forzar:
            estado = "ya existía"
        else:
            estado = descargar(sesion, item["URL"], ruta)
            time.sleep(PAUSA_SEG)
        print(f"  {anio}-{mes:02d}  {item['TITULO']:<28} {ruta.name:<50} {estado}")
        registro.append({"anio": anio, "mes": mes, "titulo": item["TITULO"],
                         "archivo": ruta.name, "formato": ruta.suffix.lower().lstrip("."),
                         "url": item["URL"], "estado": estado})

    # Meses del rango sin ningún informe publicado (p. ej. 2014 viene agrupado)
    publicados = {(r["anio"], r["mes"]) for r in registro}
    faltantes = [f"{a}-{m:02d}" for a in range(DESDE[0], HASTA[0] + 1) for m in range(1, 13)
                 if DESDE <= (a, m) <= HASTA and (a, m) not in publicados]

    with open(DESTINO / "indice_descargas.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(registro[0].keys()))
        w.writeheader()
        w.writerows(registro)

    fallos = [r for r in registro if r["estado"].startswith("FALLÓ")]
    print(f"\n[resumen] {len(registro) - len(fallos)} OK, {len(fallos)} fallidos.")
    print(f"[resumen] meses sin informe propio en la página: {', '.join(faltantes) or 'ninguno'}")
    print(f"[resumen] índice -> {DESTINO / 'indice_descargas.csv'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--forzar", action="store_true", help="Re-descarga aunque el archivo exista.")
    main(ap.parse_args().forzar)

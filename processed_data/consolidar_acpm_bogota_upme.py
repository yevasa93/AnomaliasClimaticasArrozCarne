# -*- coding: utf-8 -*-
"""
Consolida la serie mensual del precio de referencia del ACPM por ciudad (con énfasis en
BOGOTÁ) a partir de los informes UPME "Estructura de precios de los combustibles en las
principales ciudades", guardados en raw_data/Precio ACPM-UPME.

Variable extraída
-----------------
Tabla "PRECIOS DE REFERENCIA ACPM EN ALGUNAS CIUDADES DEL PAÍS [$/Galón]", ÚLTIMA fila de
la tabla = precio máximo de venta al público por galón, con sobretasa incluida:
  * 2013 - 2014: la tabla trae "PRECIO MÁXIMO DE VENTA PÚBLICO ESTACIÓN" (SIN sobretasa),
    luego "SOBRETASA" y al final "PRECIO MÁXIMO DE VENTA POR GALÓN INCLUIDA SOBRETASA".
    Se toma esta última.
  * 2015 en adelante: la sobretasa se suma antes y la última fila se llama
    "PRECIO MÁXIMO DE VENTA PÚBLICO ESTACIÓN" (en 2015 a veces coexiste con una fila
    "INCLUIDA SOBRETASA" de igual valor).
  => Regla única: la última fila cuyo rótulo empieza por "PRECIO MÁXIMO DE VENTA" dentro
     del bloque ACPM.

Orden de procesamiento
----------------------
  1. 2013:                 PDF, uno por mes (lectura por coordenadas con pdfplumber).
  2. Ene-ago 2014:         un solo .xls, una hoja por mes.
  3. Oct-2014 en adelante: un .xls/.xlsx por mes.

Meses con más de una versión (se usa la que rige la mayor parte del mes)
  * jul-2017: archivos "1al4" (1-4 jul) y "_6" (desde 6 jul)        -> "_6"
  * feb-2019: hoja original y modificación del 25-feb                -> original
  * abr-2019: original y modificaciones del 4-abr (NAL / IMP)        -> MOD_4Abr_NAL
  * sep-2019: VIG1 (desde 1-sep) y VIG21 (desde 21-sep)              -> VIG1
  * mar-2020: HOJA 1 (11-16 mar) y HOJA 2 (desde 17-mar)             -> HOJA 2
  * jun-2024: original y "actualizacion"                             -> actualizacion
Meses que la UPME no publicó (sep-2014, jun-2017, oct-2017) quedan vacíos.

Rendimiento: los .xlsx recientes declaran ~16.000 columnas vacías con formato y openpyxl
tarda ~5 s por archivo; aquí se lee el XML directamente y sólo las primeras 30 columnas
y 250 filas (todo el contenido útil).

Requisitos:  pip install pandas xlrd pdfplumber
Uso:         python consolidar_acpm_bogota_upme.py
Salidas (processed_data/):
  * precio_acpm_bogota_upme.csv     -> Fecha, Precio_ACPM_Bogota
  * precio_acpm_ciudades_upme.csv   -> Fecha + una columna por ciudad
"""

import io
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import pdfplumber

# ----------------------------------------------------------------------------------
# CONFIGURACIÓN
# ----------------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent.parent          # .../Data
CARPETA_RAW = BASE / "raw_data" / "Precio ACPM-UPME"
SALIDA_BOGOTA = BASE / "processed_data" / "precio_acpm_bogota_upme.csv"
SALIDA_CIUDADES = BASE / "processed_data" / "precio_acpm_ciudades_upme.csv"

RANGO_VALIDO = (4000, 25000)                            # $/galón plausible 2013-2026
MAX_FILAS, MAX_COLS = 250, 30

# Archivos descartados porque existe otra versión del mismo mes que rige más días
DESCARTAR = {
    "Estructura_Precios_Julio_2017_1al4.xlsx",
    "Estructura_precios_junio_2024.xlsx",
}
# Archivos con varias hojas de un mismo mes: índice de la hoja que se usa
HOJA_PREFERIDA = {
    "Estructura_precios_feb_2019.xlsx": 0,
    "Estructura_precios_abril_2019.xlsx": 1,
    "Estructura_precios_sep_2019.xlsx": 0,
    "Estructura_Precios_Marzo_2020.xlsx": 1,
}
ARCHIVO_MULTIMES_2014 = "Estructura de Precios Enero-Agosto 2014.xls"

MESES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7,
    "AGOSTO": 8, "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8,
    "AGOST": 8, "AGT": 8, "SEP": 9, "SEPT": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}
CIUDADES_COMPUESTAS = ("SANTA MARTA",)                  # nombres de dos palabras en los PDF


# ----------------------------------------------------------------------------------
# UTILIDADES
# ----------------------------------------------------------------------------------
def norm(x) -> str:
    """Mayúsculas, sin tildes y sin espacios repetidos ('Bogotá ' -> 'BOGOTA')."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    s = "".join(c for c in unicodedata.normalize("NFD", str(x)) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().upper()


def es_titulo_acpm(texto) -> bool:
    t = norm(texto)
    return "REFERENCIA ACPM" in t and "CIUDADES" in t


def es_fila_precio(texto) -> bool:
    return norm(texto).startswith("PRECIO MAXIMO DE VENTA")


def fin_de_bloque(texto) -> bool:
    return norm(texto).startswith("PRECIOS DE REFERENCIA")


def periodo_desde_texto(texto):
    """(año, mes) desde textos como 'Est_Prec_Agt_2013', 'Abril2015', '$ REF_AGOST_14'."""
    t = norm(texto).replace("_", " ").replace("-", " ")
    anio = re.search(r"(20\d{2})", t)
    if anio:
        anio = int(anio.group(1))
    else:
        corto = re.search(r"(?<!\d)(1\d|2\d)(?!\d)", t)
        anio = 2000 + int(corto.group(1)) if corto else None
    for nombre in sorted(MESES, key=len, reverse=True):
        if re.search(rf"(?<![A-Z]){nombre}(?![A-Z])", t):
            return anio, MESES[nombre]
    return anio, None


def numero_pdf(s: str):
    """'8.156,00' -> 8156.0 (formato colombiano de los PDF)."""
    s = s.strip()
    if not re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d+)?", s):
        return None
    return float(s.replace(".", "").replace(",", "."))


# ----------------------------------------------------------------------------------
# LECTURA DE EXCEL
# ----------------------------------------------------------------------------------
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _col_idx(ref: str) -> int:
    """'AB12' -> 27 (base 0)."""
    n = 0
    for c in ref:
        if not c.isalpha():
            break
        n = n * 26 + (ord(c.upper()) - 64)
    return n - 1


def leer_xlsx(ruta: Path):
    """Devuelve [(nombre_hoja, filas)] leyendo sólo MAX_FILAS x MAX_COLS de cada hoja."""
    with zipfile.ZipFile(ruta) as z:
        compartidos = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{_NS}si"):
                compartidos.append("".join(t.text or "" for t in si.iter(f"{_NS}t")))
        rels = {r.get("Id"): r.get("Target") for r in
                ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        hojas = []
        for sh in ET.fromstring(z.read("xl/workbook.xml")).iter(f"{_NS}sheet"):
            destino = rels[sh.get(f"{_NS_R}id")].lstrip("/")
            destino = destino if destino.startswith("xl/") else "xl/" + destino
            filas = [[None] * MAX_COLS for _ in range(MAX_FILAS)]
            # Las celdas vacías con formato (<c r="XFD1" s="5"/>) son cientos de miles por
            # hoja; se eliminan con una regex antes de parsear (de ~5 s a <0,5 s por archivo)
            xml = re.sub(rb'<c r="[A-Z]+\d+"[^>]*/>', b"", z.read(destino))
            with io.BytesIO(xml) as f:
                for _, el in ET.iterparse(f, events=("end",)):
                    if el.tag == f"{_NS}row":
                        if int(el.get("r", 0)) >= MAX_FILAS:
                            break
                        el.clear()                       # libera las celdas ya leídas
                        continue
                    if el.tag != f"{_NS}c":
                        continue
                    ref = el.get("r")
                    fila, col = int(re.sub(r"\D", "", ref)) - 1, _col_idx(ref)
                    if col < MAX_COLS and fila < MAX_FILAS:
                        tipo = el.get("t")
                        v = el.find(f"{_NS}v")
                        if tipo == "inlineStr":
                            valor = "".join(t.text or "" for t in el.iter(f"{_NS}t"))
                        elif v is None or v.text is None:
                            valor = None
                        elif tipo == "s":
                            valor = compartidos[int(v.text)]
                        elif tipo in ("str", "e", "b"):
                            valor = v.text
                        else:
                            valor = float(v.text)
                        filas[fila][col] = valor
            hojas.append((sh.get("name"), filas))
    return hojas


def leer_xls(ruta: Path):
    hojas = pd.read_excel(ruta, sheet_name=None, header=None)
    salida = []
    for nombre, df in hojas.items():
        df = df.iloc[:MAX_FILAS, :MAX_COLS].astype(object)
        salida.append((nombre, df.where(df.notna(), None).values.tolist()))
    return salida


def extraer_hoja(filas):
    """Bloque ACPM de una hoja -> ({ciudad: precio}, rótulo de la fila usada) o (None, None)."""
    col0 = [f[0] if f else None for f in filas]
    inicio = next((i for i, v in enumerate(col0) if es_titulo_acpm(v)), None)
    if inicio is None:
        return None, None

    # Fila de encabezado con los nombres de ciudad (la que contiene BOGOTÁ)
    cab = next((i for i in range(inicio + 1, min(inicio + 6, len(filas)))
                if any(norm(v).startswith("BOGOTA") for v in filas[i])), None)
    if cab is None:
        return None, None
    ciudades = {j: norm(v) for j, v in enumerate(filas[cab])
                if j > 0 and isinstance(v, str) and norm(v) not in ("", "CIUDAD")}

    # Última fila "PRECIO MÁXIMO DE VENTA..." antes del siguiente bloque
    objetivo = None
    for i in range(cab + 1, len(filas)):
        if fin_de_bloque(col0[i]):
            break
        if es_fila_precio(col0[i]):
            objetivo = i
    if objetivo is None:
        return None, None
    precios = {}
    for j, ciudad in ciudades.items():
        v = pd.to_numeric(filas[objetivo][j], errors="coerce")
        if pd.notna(v):
            precios[ciudad] = float(v)
    return precios, norm(col0[objetivo])


# ----------------------------------------------------------------------------------
# LECTURA DE PDF (2013)
# ----------------------------------------------------------------------------------
def lineas_pdf(page):
    """Agrupa las palabras de la página en líneas según su coordenada vertical."""
    lineas = []
    for w in sorted(page.extract_words(), key=lambda w: (round(w["top"]), w["x0"])):
        if lineas and abs(lineas[-1][0]["top"] - w["top"]) < 3:
            lineas[-1].append(w)
        else:
            lineas.append([w])
    return lineas


def columnas_ciudad(linea):
    """Palabras del encabezado -> [(ciudad, x_centro)], uniendo nombres de dos palabras."""
    palabras = [w for w in linea if norm(w["text"]) not in ("CIUDAD", ",")]
    salida, k = [], 0
    while k < len(palabras):
        w = palabras[k]
        nombre, x0, x1 = norm(w["text"]), w["x0"], w["x1"]
        if k + 1 < len(palabras):
            compuesto = f"{nombre} {norm(palabras[k + 1]['text'])}"
            if compuesto in CIUDADES_COMPUESTAS:
                nombre, x1 = compuesto, palabras[k + 1]["x1"]
                k += 1
        salida.append((nombre, (x0 + x1) / 2))
        k += 1
    return salida


def extraer_pdf(ruta: Path):
    """[(página, {ciudad: precio}, rótulo)] del bloque ACPM del PDF."""
    with pdfplumber.open(ruta) as pdf:
        for page in pdf.pages:
            lineas = lineas_pdf(page)
            textos = [" ".join(w["text"] for w in l) for l in lineas]
            inicio = next((k for k, t in enumerate(textos) if es_titulo_acpm(t)), None)
            if inicio is None:
                continue
            cab = next((k for k in range(inicio + 1, min(inicio + 5, len(lineas)))
                        if any(norm(w["text"]).startswith("BOGOT") for w in lineas[k])), None)
            if cab is None:
                continue
            ciudades = columnas_ciudad(lineas[cab])

            # En los PDF el título del bloque siguiente puede venir precedido de restos de
            # otras celdas ('8% 10% PRECIOS DE REFERENCIA EN PASTO'), por eso 'in' y no startswith
            objetivo = None
            for k in range(cab + 1, len(lineas)):
                if "PRECIOS DE REFERENCIA" in norm(textos[k]):
                    break
                if es_fila_precio(textos[k]):
                    objetivo = k
            if objetivo is None:
                continue

            # Cada número se asigna a la ciudad cuyo encabezado está más cerca en x
            precios, rotulo = {}, []
            for w in lineas[objetivo]:
                v = numero_pdf(w["text"])
                if v is None:
                    rotulo.append(w["text"])
                    continue
                xc = (w["x0"] + w["x1"]) / 2
                ciudad, xcab = min(ciudades, key=lambda c: abs(c[1] - xc))
                if abs(xcab - xc) < 40 and ciudad not in precios:
                    precios[ciudad] = v
            return [(f"pag {page.page_number}", precios, norm(" ".join(rotulo)))]
    return []


# ----------------------------------------------------------------------------------
# CONSOLIDACIÓN
# ----------------------------------------------------------------------------------
def procesar_archivo(ruta: Path):
    """[(año, mes, hoja, {ciudad: precio}, rótulo)] para un archivo."""
    nombre = ruta.name
    if ruta.suffix.lower() == ".pdf":
        anio, mes = periodo_desde_texto(ruta.stem)
        return [(anio, mes, h, p, r) for h, p, r in extraer_pdf(ruta)]

    hojas = leer_xls(ruta) if ruta.suffix.lower() == ".xls" else leer_xlsx(ruta)

    if nombre == ARCHIVO_MULTIMES_2014:                 # una hoja por mes (ene-ago 2014)
        salida = []
        for hoja, filas in hojas:
            precios, rotulo = extraer_hoja(filas)
            if precios:
                anio, mes = periodo_desde_texto(hoja)
                salida.append((anio, mes, hoja.strip(), precios, rotulo))
        return salida

    anio, mes = periodo_desde_texto(ruta.stem)
    validas = [(h, *extraer_hoja(f)) for h, f in hojas]
    validas = [(h, p, r) for h, p, r in validas if p]
    if not validas:
        return []
    if len(validas) > 1 and nombre not in HOJA_PREFERIDA:
        print(f"  [aviso] {nombre}: {len(validas)} hojas con bloque ACPM; se usa la primera.")
    h, p, r = validas[HOJA_PREFERIDA.get(nombre, 0)]
    return [(anio, mes, h, p, r)]


def main():
    archivos = sorted(
        (p for p in CARPETA_RAW.iterdir()
         if p.suffix.lower() in (".pdf", ".xls", ".xlsx") and p.name not in DESCARTAR),
        key=lambda p: (p.suffix.lower() != ".pdf",            # 1) PDF 2013
                       p.name != ARCHIVO_MULTIMES_2014,        # 2) ene-ago 2014
                       periodo_desde_texto(p.stem)[0] or 0,    # 3) resto, cronológico
                       periodo_desde_texto(p.stem)[1] or 0),
    )

    registros, detalle = [], []
    for ruta in archivos:
        try:
            filas = procesar_archivo(ruta)
        except Exception as e:                                # noqa: BLE001
            print(f"  [error] {ruta.name}: {e}")
            continue
        if not filas:
            print(f"  [sin datos] {ruta.name}: no se encontró el bloque ACPM")
            continue
        for anio, mes, hoja, precios, rotulo in filas:
            if not (anio and mes):
                print(f"  [sin fecha] {ruta.name} / {hoja}")
                continue
            fecha = pd.Timestamp(anio, mes, 1)
            detalle.append({"Fecha": fecha, "archivo": ruta.name, "hoja": hoja,
                            "rotulo": rotulo, "n_ciudades": len(precios)})
            for ciudad, v in precios.items():
                if not RANGO_VALIDO[0] <= v <= RANGO_VALIDO[1]:
                    print(f"  [revisar] {fecha:%Y-%m} {ciudad}: {v} fuera de rango ({ruta.name})")
                    continue
                registros.append({"Fecha": fecha, "Ciudad": ciudad, "Precio": round(v, 2)})

    det = pd.DataFrame(detalle)
    dup = det[det.duplicated("Fecha", keep=False)]
    if not dup.empty:
        print("  [duplicado] meses con más de un archivo:\n", dup.to_string(index=False))

    largo = pd.DataFrame(registros).drop_duplicates(["Fecha", "Ciudad"], keep="last")
    ancho = largo.pivot(index="Fecha", columns="Ciudad", values="Precio")
    rango = pd.date_range(ancho.index.min(), ancho.index.max(), freq="MS")
    ancho = ancho.reindex(rango).rename_axis("Fecha")

    # Bogotá primero, luego el resto de ciudades en orden alfabético
    orden = ["BOGOTA"] + sorted(c for c in ancho.columns if c != "BOGOTA")
    ancho = ancho[orden]

    bogota = ancho[["BOGOTA"]].rename(columns={"BOGOTA": "Precio_ACPM_Bogota"}).reset_index()
    bogota.to_csv(SALIDA_BOGOTA, index=False, date_format="%Y-%m-%d", encoding="utf-8")
    ancho.reset_index().to_csv(SALIDA_CIUDADES, index=False, date_format="%Y-%m-%d",
                               encoding="utf-8")

    faltan = bogota.loc[bogota["Precio_ACPM_Bogota"].isna(), "Fecha"].dt.strftime("%Y-%m")
    print(f"\n[ok] {len(det)} meses procesados de {len(archivos)} archivos "
          f"({rango[0]:%Y-%m} a {rango[-1]:%Y-%m}).")
    print(f"[ok] Bogotá: {bogota['Precio_ACPM_Bogota'].notna().sum()} meses con dato; "
          f"sin dato: {', '.join(faltan) or 'ninguno'}")
    print(f"[ok] Rótulos usados: {det['rotulo'].value_counts().to_dict()}")
    print(f"[ok] Ciudades por mes: {det['n_ciudades'].value_counts().sort_index().to_dict()}")
    print(f"[ok] -> {SALIDA_BOGOTA}")
    print(f"[ok] -> {SALIDA_CIUDADES}")


if __name__ == "__main__":
    main()

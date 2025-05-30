import pandas as pd
import os
import unicodedata

columnas_base = [
    "nombre",
    "marca",
    "precio",
    "precio_anterior",
    "descuento",
    "cuotas",
    "envio_gratis",
    "imagen_url",
    "link",
    "id_producto",
    "sku",
    "categoria",
    "clase_de_producto",
    "tags",
    "talles",
    "nombre_pagina",
    "tipo_de_producto",
    "variante",
    "disponible",
    "no_disponible",
    "modelo_id"
]

COLORES = [
    "negro", "blanco", "gris", "rojo", "azul", "verde", "amarillo",
    "rosa", "marron", "naranja", "purpura", "violeta", "celeste", "beige"
]

def normalizar_columnas(df: pd.DataFrame, columnas: list = None, valor_defecto="N/A") -> pd.DataFrame:
    if columnas is None:
        columnas = columnas_base
    for col in columnas:
        if col not in df.columns:
            df[col] = valor_defecto
    df = df[columnas]
    return df.fillna(valor_defecto)



def combinar_excels_en_directorio(directorio: str, columnas: list = None, valor_defecto="N/A") -> pd.DataFrame:
    if columnas is None:
        columnas = columnas_base

    archivos = [f for f in os.listdir(directorio) if f.endswith(".xlsx")]
    dataframes = []

    for archivo in archivos:
        path = os.path.join(directorio, archivo)
        df = pd.read_excel(path)
        df = normalizar_columnas(df, columnas, valor_defecto)
        dataframes.append(df)

    if dataframes:
        combinado = pd.concat(dataframes, ignore_index=True)
        return combinado
    else:
        return pd.DataFrame(columns=columnas)



def limpiar_texto(texto: str) -> str:
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')
    return texto.lower()

def inferir_categoria(nombre: str) -> str:
    nombre = limpiar_texto(nombre)

    if any(palabra in nombre for palabra in ["zapatilla", "botin", "sandalia", "calzado", "zapato"]):
        return "Calzado"
    elif any(palabra in nombre for palabra in ["remera", "short", "campera", "buzo", "pantalon", "top", "camiseta", "chaqueta", "jogger", "musculosa", "pantalon", "calza", "canguro"]):
        return "Indumentaria"
    elif any(palabra in nombre for palabra in ["pelota", "mochila", "gorra", "bolso", "media", "accesorio", "guante", "riñonera", "silbatos", "guantes"]):
        return "Accesorios"
    else:
        return "Otros"


def inferir_tipo_producto(nombre: str) -> str:
    if not nombre:
        return "N/A"
    return nombre.split()[0]

def inferir_variante(nombre: str) -> str:
    texto = limpiar_texto(nombre)
    for color in COLORES:
        if color in texto:
            return color
    return "N/A"
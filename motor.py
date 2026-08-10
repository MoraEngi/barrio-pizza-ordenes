"""
Motor de revisión de órdenes de compra - Barrio Pizza
=====================================================
Lógica de negocio pura. No depende de Streamlit ni de ninguna interfaz.
Puede reutilizarse desde una API, un job programado o un módulo de Odoo.

Flujo:
  1. cargar_datos()      -> lee los CSV y normaliza
  2. proyectar_consumo() -> estima el consumo de la próxima semana
  3. construir_analisis()-> cruza proyección + inventario + orden
  4. generar_alertas()   -> traduce números a alertas accionables
"""

from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Parámetros de negocio (ajustables desde la interfaz)
# ---------------------------------------------------------------------------

UMBRAL_QUIEBRE = 0.90      # cobertura < 0.90 semanas -> riesgo de quiebre
UMBRAL_AJUSTADO = 1.00     # entre 0.90 y 1.00 -> justo, vigilar
UMBRAL_EXCESO = 1.25       # cobertura > 1.25 semanas -> sobre-pedido
UMBRAL_EXCESO_PERECEDERO = 1.15   # los perecederos toleran menos excedente

SENSIBILIDAD_OUTLIER = 3.5  # cuántas desviaciones robustas para marcar atípico
TOPE_CRECIMIENTO = 1.30     # la proyección no puede superar 130% del promedio limpio
PISO_CAIDA = 0.80           # ni bajar de 80%


# ---------------------------------------------------------------------------
# 1. Carga de datos
# ---------------------------------------------------------------------------

def cargar_datos(carpeta=None):
    """Lee los 4 CSV. utf-8-sig limpia el BOM que traen los archivos.

    La ruta se resuelve contra la ubicación de este archivo, no contra el
    directorio de trabajo. Así funciona igual en local y en Streamlit Cloud,
    sin importar desde donde se lance el proceso.
    """
    base = Path(carpeta) if carpeta else Path(__file__).resolve().parent / "datos"
    leer = lambda n: pd.read_csv(base / n, encoding="utf-8-sig")
    return {
        "ingredientes": leer("ingredientes.csv"),
        "consumo": leer("consumo_historico.csv"),
        "inventario": leer("inventario_actual.csv"),
        "orden": leer("orden_compra_semana.csv"),
    }


# ---------------------------------------------------------------------------
# 2. Proyección del consumo
# ---------------------------------------------------------------------------

def _proyectar_serie(valores, sensibilidad=SENSIBILIDAD_OUTLIER):
    """
    Proyecta la próxima semana a partir del histórico de una serie.

    Estrategia en tres pasos:
      a) Detecta semanas atípicas con MAD (mediana de desviaciones absolutas).
         Es robusto: un solo valor extremo no mueve la mediana, a diferencia
         del promedio. Caso real del dataset: Marbella pepperoni S3 = 150 kg
         cuando el resto ronda 30. Un promedio simple proyectaría 50 kg.
      b) Sobre las semanas limpias ajusta una regresión lineal para capturar
         tendencia. Caso real: Costa del Este harina crece 240 -> 316 kg.
      c) Acota el resultado para que la extrapolación no se dispare.

    Devuelve: (proyección, semanas_atipicas, tendencia_pct)
    """
    v = np.asarray(valores, dtype=float)
    v = v[~np.isnan(v)]
    if len(v) == 0:
        return np.nan, [], 0.0
    if len(v) == 1:
        return float(v[0]), [], 0.0

    # (a) detección robusta de atípicos
    mediana = np.median(v)
    mad = np.median(np.abs(v - mediana))
    escala = mad * 1.4826 if mad > 0 else mediana * 0.20
    if escala <= 0:
        escala = 1e-9
    limpio = np.abs(v - mediana) <= sensibilidad * escala
    atipicos = [i for i, ok in enumerate(limpio) if not ok]

    x = np.arange(len(v))[limpio]
    y = v[limpio]
    if len(y) < 3:                      # muy pocos datos limpios: usa la mediana
        return float(mediana), atipicos, 0.0

    # (b) tendencia lineal sobre datos limpios
    pendiente, intercepto = np.polyfit(x, y, 1)
    proyeccion = intercepto + pendiente * len(v)

    # (c) acotar
    base = y.mean()
    proyeccion = float(np.clip(proyeccion, base * PISO_CAIDA, base * TOPE_CRECIMIENTO))
    proyeccion = max(proyeccion, 0.0)

    tendencia = (pendiente * len(v)) / base if base > 0 else 0.0
    return proyeccion, atipicos, float(tendencia)


def proyectar_consumo(consumo, sensibilidad=SENSIBILIDAD_OUTLIER):
    """Aplica la proyección a cada par (sucursal, ingrediente)."""
    tabla = consumo.pivot_table(
        index=["sucursal", "ingrediente_id"],
        columns="semana",
        values="consumo_unidad_base",
    )
    semanas = sorted(tabla.columns)
    tabla = tabla[semanas]

    filas = []
    for (suc, ing), serie in tabla.iterrows():
        proy, atipicos, tend = _proyectar_serie(serie.values, sensibilidad)
        filas.append({
            "sucursal": suc,
            "ingrediente_id": ing,
            "consumo_proyectado": proy,
            "promedio_simple": float(np.nanmean(serie.values)),
            "semanas_atipicas": ", ".join(semanas[i] for i in atipicos),
            "tendencia_pct": tend,
            "historico": list(serie.values),
        })
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# 3. Análisis: cruzar proyección, inventario y orden
# ---------------------------------------------------------------------------

def construir_analisis(datos, sensibilidad=SENSIBILIDAD_OUTLIER, colchon=0.0):
    """
    Une todo en una sola tabla. Usa merges de tipo 'outer' a propósito:
    si un ingrediente está en el catálogo pero no en la orden, la fila debe
    sobrevivir (así detectamos olvidos). Si está en la orden pero no en el
    catálogo, también (así detectamos productos desconocidos).

    colchón: margen de seguridad sobre el consumo proyectado (0.10 = 10% extra).
    """
    ing = datos["ingredientes"]
    proy = proyectar_consumo(datos["consumo"], sensibilidad)

    # Universo completo: todo par sucursal x ingrediente que aparezca en cualquier fuente
    sucursales = sorted(set(datos["inventario"].sucursal) |
                        set(datos["orden"].sucursal) |
                        set(datos["consumo"].sucursal))
    ids = sorted(set(ing.ingrediente_id) |
                 set(datos["orden"].ingrediente_id) |
                 set(datos["inventario"].ingrediente_id))
    base = pd.MultiIndex.from_product([sucursales, ids],
                                      names=["sucursal", "ingrediente_id"]).to_frame(index=False)

    df = (base
          .merge(proy, on=["sucursal", "ingrediente_id"], how="left")
          .merge(datos["inventario"], on=["sucursal", "ingrediente_id"], how="left")
          .merge(datos["orden"], on=["sucursal", "ingrediente_id"], how="left")
          .merge(ing, on="ingrediente_id", how="left"))

    # Un par sin histórico, sin stock y sin pedido no aporta nada: se descarta
    relevante = (df.consumo_proyectado.notna() |
                 df.stock_actual_unidad_base.notna() |
                 df.cantidad_formatos.notna())
    df = df[relevante].copy()

    df["en_catalogo"] = df.unidad_base_por_formato.notna()
    df["pedido_formatos"] = df.cantidad_formatos.fillna(0)
    df["stock"] = df.stock_actual_unidad_base.fillna(0)
    df["consumo_proyectado"] = df.consumo_proyectado.fillna(0)

    # Conversión de formatos a unidad base: el corazón del reto
    df["pedido_ub"] = df.pedido_formatos * df.unidad_base_por_formato

    df["demanda"] = df.consumo_proyectado * (1 + colchon)
    df["necesidad_ub"] = (df.demanda - df.stock).clip(lower=0)
    df["formatos_sugeridos"] = np.ceil(df.necesidad_ub / df.unidad_base_por_formato)
    df["diferencia_formatos"] = df.pedido_formatos - df.formatos_sugeridos
    df["disponible_ub"] = df.stock + df.pedido_ub

    # Cobertura = cuántas semanas de consumo cubre lo que va a tener en mano.
    # Es la métrica central: intuitiva para quien aprueba las órdenes.
    df["cobertura"] = np.where(df.demanda > 0, df.disponible_ub / df.demanda, np.nan)

    df["faltante_ub"] = (df.necesidad_ub - df.pedido_ub).clip(lower=0)
    df["excedente_ub"] = (df.pedido_ub - df.necesidad_ub).clip(lower=0)
    df["es_perecedero"] = df.es_perecedero.fillna("No").astype(str).str.strip().str.lower().eq("si")

    df["estado"] = df.apply(_clasificar, axis=1)
    df["severidad"] = df.apply(_severidad, axis=1)
    return df


def _clasificar(r):
    """Traduce los números a un estado de negocio."""
    if not r.en_catalogo:
        return "SIN_CATALOGO"

    if r.demanda <= 0:
        # No hay consumo esperado. Si igual pidieron, es compra innecesaria.
        return "EXCESO" if r.pedido_formatos > 0 else "OK"

    if r.pedido_formatos == 0 and r.necesidad_ub > 0:
        return "OLVIDO"

    cob = r.cobertura
    if cob < UMBRAL_QUIEBRE:
        return "QUIEBRE"
    if cob < UMBRAL_AJUSTADO:
        return "AJUSTADO"

    tope = UMBRAL_EXCESO_PERECEDERO if r.es_perecedero else UMBRAL_EXCESO
    # Regla del README: un excedente menor a un formato completo es redondeo normal.
    if cob > tope and r.excedente_ub >= r.unidad_base_por_formato:
        return "EXCESO"
    return "OK"


def _severidad(r):
    """0 a 100. Ordena las alertas para que lo grave aparezca primero."""
    e = r.estado
    if e == "OLVIDO":
        return 100.0
    if e == "SIN_CATALOGO":
        return 55.0
    if e == "QUIEBRE":
        faltante = 1 - (r.cobertura if pd.notna(r.cobertura) else 1)
        return float(min(95, 55 + faltante * 60))
    if e == "EXCESO":
        veces = r.cobertura if pd.notna(r.cobertura) else 1
        base = min(70, 25 + (veces - 1) * 18)
        return float(base + (12 if r.es_perecedero else 0))
    if e == "AJUSTADO":
        return 25.0
    return 0.0


# ---------------------------------------------------------------------------
# 4. Alertas en lenguaje de negocio
# ---------------------------------------------------------------------------

def _fmt(x, dec=1):
    if pd.isna(x):
        return "-"
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:,.{dec}f}"


def generar_alertas(df):
    """Convierte las filas problemáticas en mensajes accionables."""
    alertas = []
    for _, r in df[df.estado != "OK"].iterrows():
        nombre = r.nombre if pd.notna(r.nombre) else r.ingrediente_id
        unidad = r.unidad_base if pd.notna(r.unidad_base) else "und"

        if r.estado == "SIN_CATALOGO":
            titulo = (f"{r.sucursal} pidió {int(r.pedido_formatos)} formatos de "
                      f"'{r.ingrediente_id}', que no existe en el catálogo")
            detalle = "Sin proveedor ni factor de conversión. No se puede validar ni cotizar."
            accion = "Dar de alta el ingrediente o corregir el código en la orden."

        elif r.estado == "OLVIDO":
            titulo = f"{r.sucursal} NO pidió {nombre}"
            detalle = (f"Proyección {_fmt(r.consumo_proyectado)} {unidad} contra un stock de "
                       f"{_fmt(r.stock)} {unidad}. Cubre {_fmt(r.cobertura, 2)} semanas.")
            accion = f"Agregar {int(r.formatos_sugeridos)} x {r.formato_compra}."

        elif r.estado == "QUIEBRE":
            titulo = (f"{r.sucursal} pide {_fmt(r.faltante_ub)} {unidad} menos de "
                      f"{nombre} que lo proyectado")
            detalle = (f"Pide {int(r.pedido_formatos)} y necesita {int(r.formatos_sugeridos)} "
                       f"x {r.formato_compra}. Cubre {_fmt(r.cobertura, 2)} semanas.")
            accion = f"Subir a {int(r.formatos_sugeridos)} formatos (+{int(-r.diferencia_formatos)})."

        elif r.estado == "EXCESO":
            titulo = (f"{r.sucursal} pide {_fmt(r.excedente_ub)} {unidad} de más "
                      f"de {nombre}")
            detalle = (f"Pide {int(r.pedido_formatos)} y necesita {int(r.formatos_sugeridos)} "
                       f"x {r.formato_compra}. Cubre {_fmt(r.cobertura, 2)} semanas.")
            if r.es_perecedero:
                detalle += " Es perecedero: riesgo de merma."
            accion = f"Bajar a {int(r.formatos_sugeridos)} formatos (-{int(r.diferencia_formatos)})."

        else:  # AJUSTADO
            titulo = f"{r.sucursal} queda justo en {nombre}"
            detalle = f"Cubre {_fmt(r.cobertura, 2)} semanas. Sin margen ante cualquier repunte."
            accion = "Revisar si conviene un formato adicional."

        alertas.append({
            "sucursal": r.sucursal,
            "ingrediente_id": r.ingrediente_id,
            "ingrediente": nombre,
            "proveedor": r.proveedor if pd.notna(r.proveedor) else "Sin asignar",
            "estado": r.estado,
            "severidad": r.severidad,
            "titulo": titulo,
            "detalle": detalle,
            "accion": accion,
            "semanas_atipicas": r.semanas_atipicas if pd.notna(r.semanas_atipicas) else "",
            "tendencia_pct": r.tendencia_pct,
        })

    res = pd.DataFrame(alertas)
    if not res.empty:
        res = res.sort_values("severidad", ascending=False).reset_index(drop=True)
    return res


# ---------------------------------------------------------------------------
# 5. Orden corregida, lista para enviar a cada proveedor
# ---------------------------------------------------------------------------

def orden_corregida(df):
    """Versión sugerida de la orden, agrupable por proveedor."""
    cols = ["sucursal", "proveedor", "ingrediente_id", "nombre", "formato_compra",
            "pedido_formatos", "formatos_sugeridos", "diferencia_formatos", "estado"]
    out = df[df.en_catalogo][cols].copy()
    out = out[(out.formatos_sugeridos > 0) | (out.pedido_formatos > 0)]
    out.columns = ["Sucursal", "Proveedor", "ID", "Ingrediente", "Formato",
                   "Pedido original", "Pedido sugerido", "Diferencia", "Estado"]
    return out.sort_values(["Proveedor", "Sucursal", "Ingrediente"]).reset_index(drop=True)


def resumen(df):
    """Números de cabecera para el dashboard."""
    d = df[df.estado != "OK"]
    return {
        "alertas": int(len(d)),
        "quiebres": int((df.estado.isin(["QUIEBRE", "OLVIDO"])).sum()),
        "excesos": int((df.estado == "EXCESO").sum()),
        "datos": int((df.estado == "SIN_CATALOGO").sum()),
        "formatos_de_mas": int(df.loc[df.estado == "EXCESO", "diferencia_formatos"].sum()),
        "formatos_faltantes": int(-df.loc[df.estado.isin(["QUIEBRE", "OLVIDO"]),
                                          "diferencia_formatos"].sum()),
        "lineas": int(len(df)),
    }

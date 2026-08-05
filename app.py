"""
Dashboard de revision de ordenes de compra - Barrio Pizza
Interfaz Streamlit. Toda la logica de negocio vive en motor.py.
"""

import io

import pandas as pd
import streamlit as st

import motor

st.set_page_config(page_title="Barrio Pizza · Revision de ordenes",
                   page_icon="🍕", layout="wide")

COLOR = {
    "OLVIDO": "#A32D2D", "QUIEBRE": "#D85A30", "EXCESO": "#BA7517",
    "SIN_CATALOGO": "#185FA5", "AJUSTADO": "#5F5E5A",
}
ETIQUETA = {
    "OLVIDO": "Olvido", "QUIEBRE": "Riesgo de quiebre", "EXCESO": "Sobre-pedido",
    "SIN_CATALOGO": "Dato incompleto", "AJUSTADO": "Justo",
}

st.markdown("""
<style>
  .alerta {border-left:5px solid #999; background:rgba(128,128,128,.06);
           padding:.7rem 1rem; margin-bottom:.55rem; border-radius:0 6px 6px 0;}
  .alerta .t {font-weight:600; font-size:.97rem; margin-bottom:.2rem;}
  .alerta .d {font-size:.85rem; opacity:.78;}
  .alerta .a {font-size:.85rem; margin-top:.35rem; font-weight:600;}
  .chip {display:inline-block; font-size:.7rem; padding:.12rem .5rem;
         border-radius:10px; color:#fff; margin-right:.4rem;}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------

@st.cache_data
def datos_base():
    return motor.cargar_datos()


st.sidebar.title("🍕 Barrio Pizza")
st.sidebar.caption("Revision automatica de ordenes de compra")

datos = dict(datos_base())

st.sidebar.subheader("Cargar orden de la semana")
subido = st.sidebar.file_uploader(
    "CSV con columnas: sucursal, ingrediente_id, cantidad_formatos", type="csv")
if subido is not None:
    try:
        nueva = pd.read_csv(subido, encoding="utf-8-sig")
        faltan = {"sucursal", "ingrediente_id", "cantidad_formatos"} - set(nueva.columns)
        if faltan:
            st.sidebar.error(f"Faltan columnas: {', '.join(faltan)}")
        else:
            datos["orden"] = nueva
            st.sidebar.success(f"Orden cargada: {len(nueva)} lineas")
    except Exception as e:
        st.sidebar.error(f"No se pudo leer el archivo: {e}")

st.sidebar.subheader("Parametros")
colchon = st.sidebar.slider(
    "Margen de seguridad", 0, 30, 0, 5,
    help="Porcentaje extra sobre el consumo proyectado, como colchon.") / 100
sensibilidad = st.sidebar.slider(
    "Sensibilidad a semanas atipicas", 2.0, 6.0, 3.5, 0.5,
    help="Mas bajo = descarta mas semanas raras del historico.")

df = motor.construir_analisis(datos, sensibilidad=sensibilidad, colchon=colchon)
alertas = motor.generar_alertas(df)
res = motor.resumen(df)


# ---------------------------------------------------------------------------
# Cabecera
# ---------------------------------------------------------------------------

st.title("Revision de ordenes de compra")
st.caption(f"{df.sucursal.nunique()} sucursales · {df.ingrediente_id.nunique()} ingredientes · "
           f"{res['lineas']} lineas revisadas")

c = st.columns(5)
c[0].metric("Alertas activas", res["alertas"])
c[1].metric("Riesgo de quiebre", res["quiebres"])
c[2].metric("Sobre-pedido", res["excesos"])
c[3].metric("Formatos de mas", res["formatos_de_mas"])
c[4].metric("Formatos faltantes", res["formatos_faltantes"])

st.divider()


# ---------------------------------------------------------------------------
# Semaforo por sucursal
# ---------------------------------------------------------------------------

graves = ["OLVIDO", "QUIEBRE", "SIN_CATALOGO"]
cols = st.columns(df.sucursal.nunique())
for col, suc in zip(cols, sorted(df.sucursal.unique())):
    sub = df[df.sucursal == suc]
    n_grave = int(sub.estado.isin(graves).sum())
    n_exceso = int((sub.estado == "EXCESO").sum())
    if n_grave:
        icono, texto = "🔴", f"{n_grave} criticas"
    elif n_exceso:
        icono, texto = "🟡", f"{n_exceso} de sobre-pedido"
    else:
        icono, texto = "🟢", "sin alertas"
    col.markdown(f"**{icono} {suc}**  \n{texto}")

st.divider()

tab1, tab2, tab3 = st.tabs(["Alertas", "Detalle por sucursal", "Orden corregida"])


# ---------------------------------------------------------------------------
# Tab 1 — Alertas
# ---------------------------------------------------------------------------

with tab1:
    if alertas.empty:
        st.success("Ninguna orden presenta desviaciones. Todo listo para aprobar.")
    else:
        izq, der = st.columns([3, 1])
        f_suc = der.multiselect("Sucursal", sorted(alertas.sucursal.unique()))
        f_est = der.multiselect("Tipo", [ETIQUETA[e] for e in alertas.estado.unique()])
        ver_justos = der.checkbox("Mostrar casos 'justos'", value=False)

        vista = alertas.copy()
        if f_suc:
            vista = vista[vista.sucursal.isin(f_suc)]
        if f_est:
            vista = vista[vista.estado.map(ETIQUETA).isin(f_est)]
        if not ver_justos:
            vista = vista[vista.estado != "AJUSTADO"]

        izq.markdown(f"**{len(vista)} alertas**, ordenadas por gravedad")
        for _, a in vista.iterrows():
            color = COLOR.get(a.estado, "#888")
            nota = ""
            if a.semanas_atipicas:
                nota = (f"<br><span style='font-size:.78rem;opacity:.65'>"
                        f"Se ignoro la semana atipica {a.semanas_atipicas} al proyectar.</span>")
            elif a.tendencia_pct and abs(a.tendencia_pct) > 0.12:
                signo = "creciente" if a.tendencia_pct > 0 else "decreciente"
                nota = (f"<br><span style='font-size:.78rem;opacity:.65'>"
                        f"Tendencia {signo} de {a.tendencia_pct*100:+.0f}% en el historico.</span>")
            izq.markdown(
                f"""<div class="alerta" style="border-left-color:{color}">
                    <span class="chip" style="background:{color}">{ETIQUETA[a.estado]}</span>
                    <span style="font-size:.78rem;opacity:.6">{a.proveedor}</span>
                    <div class="t">{a.titulo}</div>
                    <div class="d">{a.detalle}{nota}</div>
                    <div class="a" style="color:{color}">→ {a.accion}</div>
                </div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tab 2 — Detalle por sucursal
# ---------------------------------------------------------------------------

with tab2:
    suc = st.selectbox("Sucursal", sorted(df.sucursal.unique()))
    sub = df[df.sucursal == suc].copy()

    tabla = sub[["nombre", "ingrediente_id", "consumo_proyectado", "promedio_simple",
                 "stock", "necesidad_ub", "pedido_formatos", "formatos_sugeridos",
                 "cobertura", "estado", "formato_compra", "proveedor"]]
    tabla.columns = ["Ingrediente", "ID", "Proyectado", "Prom. simple", "Stock",
                     "Necesidad", "Pide", "Sugerido", "Cobertura (sem)", "Estado",
                     "Formato", "Proveedor"]
    st.dataframe(
        tabla.sort_values("Estado").style.format({
            "Proyectado": "{:,.1f}", "Prom. simple": "{:,.1f}", "Stock": "{:,.1f}",
            "Necesidad": "{:,.1f}", "Pide": "{:,.0f}", "Sugerido": "{:,.0f}",
            "Cobertura (sem)": "{:,.2f}"}),
        use_container_width=True, hide_index=True)

    st.subheader("Historico y proyeccion")
    opciones = sub.dropna(subset=["nombre"]).sort_values("nombre")
    elegido = st.selectbox("Ingrediente", opciones.nombre.tolist())
    fila = opciones[opciones.nombre == elegido].iloc[0]
    hist = fila.historico if isinstance(fila.historico, list) else []
    if hist:
        serie = pd.DataFrame({
            "Semana": [f"S{i+1}" for i in range(len(hist))] + ["Proyec."],
            "Consumo": list(hist) + [fila.consumo_proyectado],
        }).set_index("Semana")
        st.bar_chart(serie)
        if fila.semanas_atipicas:
            st.info(f"La semana {fila.semanas_atipicas} se detecto como atipica y se excluyo. "
                    f"El promedio simple daria {fila.promedio_simple:,.1f}; "
                    f"la proyeccion robusta da {fila.consumo_proyectado:,.1f}.")


# ---------------------------------------------------------------------------
# Tab 3 — Orden corregida por proveedor
# ---------------------------------------------------------------------------

with tab3:
    st.caption("Cada proveedor recibe su orden por separado. Aca esta la version "
               "sugerida, ya agrupada y lista para enviar.")
    corr = motor.orden_corregida(df)
    solo_cambios = st.checkbox("Mostrar solo lineas que cambian", value=True)
    vista = corr[corr.Diferencia != 0] if solo_cambios else corr

    for prov in sorted(vista.Proveedor.unique()):
        bloque = vista[vista.Proveedor == prov]
        with st.expander(f"{prov} — {len(bloque)} lineas", expanded=True):
            st.dataframe(bloque.drop(columns=["Proveedor"]),
                         use_container_width=True, hide_index=True)

    buf = io.StringIO()
    corr.to_csv(buf, index=False)
    st.download_button("Descargar orden corregida (CSV)", buf.getvalue(),
                       "orden_corregida.csv", "text/csv")

"""
Dashboard de revision de ordenes de compra - Barrio Pizza
Interfaz Streamlit. Toda la logica de negocio vive en motor.py.
"""

import io

import altair as alt
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
# Grafico de serie historica
# ---------------------------------------------------------------------------

AZUL, GRIS, NARANJA = "#4C8DBF", "#8C8C8C", "#D97A29"


def diagnostico_serie(fila, hist):
    """Una linea en lenguaje llano que le da lectura al grafico.

    Un grafico de barras plano es informacion valida, pero sin esta frase el
    usuario no sabe si esta viendo estabilidad o un problema.
    """
    u = fila.unidad_base
    limpio = [v for i, v in enumerate(hist)
              if f"S{i+1}" != (fila.semanas_atipicas or "")]
    base = sum(limpio) / len(limpio) if limpio else 0
    disp = (max(limpio) - min(limpio)) / base if base and limpio else 0
    tend = fila.tendencia_pct or 0

    if fila.semanas_atipicas:
        return ("⚠️", f"La semana {fila.semanas_atipicas} se salio del patron y se excluyo. "
                f"Con promedio simple la proyeccion seria **{fila.promedio_simple:,.1f} {u}**; "
                f"descartandola queda en **{fila.consumo_proyectado:,.1f} {u}**.")
    if abs(tend) > 0.12:
        rumbo = "creciendo" if tend > 0 else "cayendo"
        return ("📈" if tend > 0 else "📉",
                f"El consumo viene {rumbo} **{abs(tend)*100:.0f}%** en las 6 semanas. "
                f"El promedio simple daria {fila.promedio_simple:,.1f} {u} y se quedaria corto: "
                f"la proyeccion sigue la tendencia hasta **{fila.consumo_proyectado:,.1f} {u}**.")
    if disp < 0.15:
        return ("✅", f"Serie estable: varia menos de {max(disp,0.01)*100:.0f}% entre semanas. "
                f"Se proyectan **{fila.consumo_proyectado:,.1f} {u}** con alta confianza.")
    return ("〰️", f"Serie irregular (varia {disp*100:.0f}% entre semanas) pero sin un patron "
            f"claro ni valores atipicos. Se proyectan **{fila.consumo_proyectado:,.1f} {u}**.")


def grafico_serie(fila, hist):
    """Barras cronologicas con la proyeccion destacada al final.

    Se usa Altair en vez de st.bar_chart para poder controlar el orden, el
    color por categoria, las etiquetas horizontales y la regla del promedio.
    """
    atipica = fila.semanas_atipicas or ""
    filas = []
    for i, v in enumerate(hist):
        s = f"S{i+1}"
        filas.append({"Semana": f"Sem {i+1}", "Consumo": float(v), "orden": i,
                      "Tipo": "Semana descartada" if s == atipica else "Historico"})
    filas.append({"Semana": "Proxima", "Consumo": float(fila.consumo_proyectado),
                  "orden": len(hist), "Tipo": "Proyeccion"})
    serie = pd.DataFrame(filas)

    icono, texto = diagnostico_serie(fila, hist)
    st.markdown(f"{icono} {texto}")

    escala = alt.Scale(domain=["Historico", "Semana descartada", "Proyeccion"],
                       range=[AZUL, GRIS, NARANJA])
    # El orden va explicito como lista: con sort por campo Altair reordena
    # alfabeticamente y "Proxima" termina antes que "Sem 1".
    orden_x = [f"Sem {i+1}" for i in range(len(hist))] + ["Proxima"]
    eje_x = alt.X("Semana:N", sort=orden_x, title=None,
                  axis=alt.Axis(labelAngle=0, labelFontSize=12))

    barras = alt.Chart(serie).mark_bar(size=42, cornerRadiusTopLeft=3,
                                       cornerRadiusTopRight=3).encode(
        x=eje_x,
        y=alt.Y("Consumo:Q", title=f"Consumo ({fila.unidad_base})",
                axis=alt.Axis(labelFontSize=11)),
        color=alt.Color("Tipo:N", scale=escala,
                        legend=alt.Legend(orient="top", title=None, direction="horizontal")),
        opacity=alt.condition(alt.datum.Tipo == "Semana descartada",
                              alt.value(0.35), alt.value(1.0)),
        tooltip=[alt.Tooltip("Semana:N"), alt.Tooltip("Consumo:Q", format=",.1f"),
                 alt.Tooltip("Tipo:N")],
    )

    valores = alt.Chart(serie).mark_text(dy=-8, fontSize=11, color="#9AA3AB").encode(
        x=eje_x, y="Consumo:Q", text=alt.Text("Consumo:Q", format=",.0f"))

    prom = alt.Chart(pd.DataFrame({"y": [float(fila.promedio_simple)]})).mark_rule(
        strokeDash=[5, 4], color="#B85C5C", size=1.5).encode(
        y="y:Q", tooltip=alt.Tooltip("y:Q", title="Promedio simple", format=",.1f"))

    st.altair_chart((barras + valores + prom).properties(height=330),
                    width="stretch")
    st.caption(f"Linea punteada = promedio simple ({fila.promedio_simple:,.1f} "
               f"{fila.unidad_base}), el metodo que estamos reemplazando.")


def grafico_comparativo(df, ingrediente_id, sucursal_activa):
    """Cobertura del mismo ingrediente en las 4 sucursales.

    La cobertura es comparable entre sucursales aunque tengan tamanos muy
    distintos, porque ya viene normalizada por el consumo propio de cada una.
    Sirve para ver de un golpe quien se sale del patron del grupo.
    """
    comp = df[(df.ingrediente_id == ingrediente_id) & df.cobertura.notna()].copy()
    if comp.empty or len(comp) < 2:
        return
    comp["Sucursal"] = comp.sucursal
    comp["Cobertura"] = comp.cobertura.clip(upper=5)   # recorta para que una
    comp["real"] = comp.cobertura                      # sucursal extrema no
    comp["Estado"] = comp.estado.map(ETIQUETA).fillna("OK")  # aplaste al resto

    barras = alt.Chart(comp).mark_bar(size=30, cornerRadiusEnd=3).encode(
        y=alt.Y("Sucursal:N", title=None, sort="-x",
                axis=alt.Axis(labelFontSize=12)),
        x=alt.X("Cobertura:Q", title="Semanas de cobertura",
                scale=alt.Scale(domainMin=0)),
        color=alt.Color("Estado:N", scale=alt.Scale(
            domain=["Olvido", "Riesgo de quiebre", "Sobre-pedido",
                    "Dato incompleto", "Justo", "OK"],
            range=[COLOR["OLVIDO"], COLOR["QUIEBRE"], COLOR["EXCESO"],
                   COLOR["SIN_CATALOGO"], COLOR["AJUSTADO"], "#3E7A4E"]),
            legend=alt.Legend(orient="top", title=None, direction="horizontal")),
        opacity=alt.condition(alt.datum.Sucursal == sucursal_activa,
                              alt.value(1.0), alt.value(0.45)),
        tooltip=[alt.Tooltip("Sucursal:N"), alt.Tooltip("real:Q", title="Cobertura", format=",.2f"),
                 alt.Tooltip("Estado:N")],
    )
    etiq = alt.Chart(comp).mark_text(dx=6, align="left", fontSize=11,
                                     color="#9AA3AB").encode(
        y=alt.Y("Sucursal:N", sort="-x"), x="Cobertura:Q",
        text=alt.Text("real:Q", format=",.2f"))

    bandas = alt.Chart(pd.DataFrame({"x": [0.90, 1.25]})).mark_rule(
        strokeDash=[4, 4], color="#7A7A7A", size=1).encode(x="x:Q")

    st.altair_chart((barras + etiq + bandas).properties(height=max(130, 42 * len(comp))),
                    width="stretch")
    st.caption("Cobertura = semanas que alcanza el stock mas el pedido. "
               "Las lineas marcan el rango sano (0.90 a 1.25). La sucursal "
               "seleccionada va resaltada; las demas, atenuadas.")


ESCALA_ESTADO = alt.Scale(
    domain=["Olvido", "Riesgo de quiebre", "Sobre-pedido", "Dato incompleto",
            "Justo", "OK"],
    range=[COLOR["OLVIDO"], COLOR["QUIEBRE"], COLOR["EXCESO"],
           COLOR["SIN_CATALOGO"], COLOR["AJUSTADO"], "#2F5D45"])


def mapa_calor(df):
    """Toda la red en una sola vista: ingredientes x sucursales.

    Cada celda es una linea de orden. El numero es la correccion sugerida en
    formatos, que es la unidad en la que la gerente realmente decide.
    """
    m = df.dropna(subset=["nombre"]).copy()
    m["Estado"] = m.estado.map(ETIQUETA).fillna("OK")
    m["Ajuste"] = (m.formatos_sugeridos - m.pedido_formatos).fillna(0)
    m["texto"] = m.Ajuste.apply(lambda v: f"{v:+.0f}" if abs(v) >= 1 else "")
    m["Cob"] = m.cobertura.round(2)

    # Los ingredientes con problemas suben al tope de la matriz.
    orden_ing = (m.groupby("nombre").severidad.max()
                  .sort_values(ascending=False).index.tolist())

    base = alt.Chart(m).encode(
        x=alt.X("sucursal:N", title=None,
                axis=alt.Axis(labelAngle=0, orient="top", labelFontSize=12,
                              labelPadding=8)),
        y=alt.Y("nombre:N", title=None, sort=orden_ing,
                axis=alt.Axis(labelFontSize=11, labelPadding=6)),
    )
    celdas = base.mark_rect(stroke="#0E1117", strokeWidth=3, cornerRadius=3).encode(
        color=alt.Color("Estado:N", scale=ESCALA_ESTADO,
                        legend=alt.Legend(orient="bottom", title=None,
                                          direction="horizontal", columns=6)),
        tooltip=[alt.Tooltip("sucursal:N", title="Sucursal"),
                 alt.Tooltip("nombre:N", title="Ingrediente"),
                 alt.Tooltip("Estado:N"),
                 alt.Tooltip("pedido_formatos:Q", title="Pide", format=",.0f"),
                 alt.Tooltip("formatos_sugeridos:Q", title="Sugerido", format=",.0f"),
                 alt.Tooltip("Cob:Q", title="Cobertura (sem)")],
    )
    numeros = base.mark_text(fontSize=11, fontWeight="bold", color="#FFFFFF").encode(
        text="texto:N")

    st.altair_chart((celdas + numeros).properties(
        height=max(320, 26 * m.nombre.nunique())), width="stretch")
    st.caption("Cada celda es una linea de la orden. El numero es el ajuste "
               "sugerido en formatos: +7 significa pedir 7 mas, -18 pedir 18 menos. "
               "Las celdas en blanco ya estan bien.")


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

df_total = motor.construir_analisis(datos, sensibilidad=sensibilidad, colchon=colchon)

# Filtro global. Se lee antes de dibujar nada para que la cabecera, el
# panorama y las alertas respondan todos al mismo foco.
if "foco" not in st.session_state:
    st.session_state.foco = None
if st.session_state.foco not in list(df_total.sucursal.unique()) + [None]:
    st.session_state.foco = None          # la sucursal ya no existe tras cargar otro CSV

foco = st.session_state.foco
df = df_total if foco is None else df_total[df_total.sucursal == foco]
alertas = motor.generar_alertas(df)
res = motor.resumen(df)


# ---------------------------------------------------------------------------
# Cabecera
# ---------------------------------------------------------------------------

st.title("Revision de ordenes de compra")
if foco:
    st.caption(f"Viendo solo **{foco}** · {res['lineas']} lineas · "
               f"pulsa la sucursal de nuevo para ver toda la red")
else:
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
# Semaforo por sucursal — cada uno filtra todo el tablero
# ---------------------------------------------------------------------------

GRAVES = ["OLVIDO", "QUIEBRE", "SIN_CATALOGO"]
cols = st.columns(df_total.sucursal.nunique())
for col, suc in zip(cols, sorted(df_total.sucursal.unique())):
    s = df_total[df_total.sucursal == suc]
    n_grave = int(s.estado.isin(GRAVES).sum())
    n_exceso = int((s.estado == "EXCESO").sum())
    if n_grave:
        icono, texto = "🔴", f"{n_grave} critica" + ("s" if n_grave > 1 else "")
    elif n_exceso:
        icono, texto = "🟡", f"{n_exceso} sobre-pedido" + ("s" if n_exceso > 1 else "")
    else:
        icono, texto = "🟢", "sin alertas"
    activo = (foco == suc)
    if col.button(f"{icono}  **{suc}** — {texto}", key=f"sem_{suc}",
                  width="stretch", type="primary" if activo else "secondary"):
        # Volver a pulsar la sucursal activa quita el filtro.
        st.session_state.foco = None if activo else suc
        st.rerun()

st.divider()

tab0, tab1, tab2, tab3 = st.tabs(
    ["Panorama", "Alertas", "Detalle por sucursal", "Orden corregida"])


# ---------------------------------------------------------------------------
# Tab 0 — Panorama de toda la red
# ---------------------------------------------------------------------------

with tab0:
    p1, p2 = st.columns([2.2, 1])
    with p1:
        mapa_calor(df)
    with p2:
        st.markdown("##### Donde duele mas")
        rank = (df[df.estado.isin(GRAVES + ["EXCESO"])]
                .groupby("sucursal")
                .agg(alertas=("estado", "size"),
                     gravedad=("severidad", "max"))
                .sort_values(["gravedad", "alertas"], ascending=False)
                .reset_index())
        if rank.empty:
            st.success("Ninguna sucursal presenta desviaciones.")
        else:
            for r in rank.itertuples():
                st.markdown(f"**{r.sucursal}** — {r.alertas} alertas")
                st.progress(min(r.gravedad / 100, 1.0))

        st.markdown("##### Impacto por proveedor")
        imp = (df.dropna(subset=["proveedor"])
                 .assign(ajuste=lambda d: (d.formatos_sugeridos - d.pedido_formatos).abs())
                 .groupby("proveedor").ajuste.sum()
                 .sort_values(ascending=False).head(5).reset_index())
        imp = imp[imp.ajuste > 0]
        if imp.empty:
            st.caption("Sin correcciones pendientes.")
        else:
            st.altair_chart(
                alt.Chart(imp).mark_bar(cornerRadiusEnd=3, color=AZUL).encode(
                    y=alt.Y("proveedor:N", title=None, sort="-x",
                            axis=alt.Axis(labelFontSize=11)),
                    x=alt.X("ajuste:Q", title="Formatos a corregir"),
                    tooltip=["proveedor:N", "ajuste:Q"],
                ).properties(height=max(120, 34 * len(imp))), width="stretch")


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
    # Los dos filtros viven juntos, arriba del contenido que controlan.
    # Antes la sucursal estaba al tope de la pestana y obligaba a subir cada vez.
    fc1, fc2 = st.columns([1, 1.4])
    suc = fc1.selectbox("Sucursal", sorted(df.sucursal.unique()))
    sub = df[df.sucursal == suc].copy()

    # El desplegable arranca por el ingrediente mas problematico de la sucursal:
    # abrir la pestana en un caso plano no le dice nada a quien aprueba ordenes.
    opciones = (sub.dropna(subset=["nombre"])
                   .sort_values(["severidad", "nombre"], ascending=[False, True]))
    etiquetas_sel = [
        f"{'●  ' if r.estado in ETIQUETA and r.estado != 'AJUSTADO' else ''}{r.nombre}"
        for r in opciones.itertuples()]
    mapa_sel = dict(zip(etiquetas_sel, opciones.nombre))
    elegido = mapa_sel[fc2.selectbox("Ingrediente  (● = tiene alerta)", etiquetas_sel)]
    fila = opciones[opciones.nombre == elegido].iloc[0]
    hist = fila.historico if isinstance(fila.historico, list) else []

    # Ficha del ingrediente: los numeros que sostienen la decision, sin tener
    # que buscarlos en la tabla.
    u = fila.unidad_base
    dif = int(fila.formatos_sugeridos - fila.pedido_formatos)
    k = st.columns(5)
    k[0].metric("Proyeccion", f"{fila.consumo_proyectado:,.1f} {u}",
                f"{fila.consumo_proyectado - fila.promedio_simple:+,.1f} vs prom. simple",
                delta_color="off")
    k[1].metric("Stock actual", f"{fila.stock:,.1f} {u}")
    k[2].metric("Pide", f"{fila.pedido_formatos:,.0f}", help=fila.formato_compra)
    k[3].metric("Sugerido", f"{fila.formatos_sugeridos:,.0f}",
                f"{dif:+d} formatos" if dif else "sin cambio",
                delta_color="inverse" if dif else "off")
    k[4].metric("Cobertura", f"{fila.cobertura:,.2f} sem" if pd.notna(fila.cobertura) else "—",
                ETIQUETA.get(fila.estado, "OK"), delta_color="off")

    if hist:
        grafico_serie(fila, hist)

    # Siempre contra la red completa: comparar contra un subconjunto filtrado
    # vaciaria el grafico justo cuando hay un foco activo.
    st.markdown(f"##### {elegido} en las demas sucursales")
    grafico_comparativo(df_total, fila.ingrediente_id, suc)

    # La tabla completa pasa al final y colapsada: es material de consulta,
    # no lo primero que uno necesita ver.
    with st.expander(f"Ver tabla completa de {suc}  ({len(sub)} lineas)"):
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
            width="stretch", hide_index=True)


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
                         width="stretch", hide_index=True)

    buf = io.StringIO()
    corr.to_csv(buf, index=False)
    st.download_button("Descargar orden corregida (CSV)", buf.getvalue(),
                       "orden_corregida.csv", "text/csv")

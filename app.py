"""
Dashboard de revisión de órdenes de compra - Barrio Pizza
Interfaz Streamlit. Toda la lógica de negocio vive en motor.py.
"""

import io

import altair as alt
import pandas as pd
import streamlit as st

import motor

st.set_page_config(page_title="Barrio Pizza · Revisión de órdenes",
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
# Gráfico de serie histórica
# ---------------------------------------------------------------------------

AZUL, GRIS, NARANJA = "#4C8DBF", "#8C8C8C", "#D97A29"


def diagnostico_serie(fila, hist):
    """Una línea en lenguaje llano que le da lectura al gráfico.

    Un gráfico de barras plano es información válida, pero sin esta frase el
    usuario no sabe si está viendo estabilidad o un problema.
    """
    u = fila.unidad_base
    limpio = [v for i, v in enumerate(hist)
              if f"S{i+1}" != (fila.semanas_atipicas or "")]
    base = sum(limpio) / len(limpio) if limpio else 0
    disp = (max(limpio) - min(limpio)) / base if base and limpio else 0
    tend = fila.tendencia_pct or 0

    if fila.semanas_atipicas:
        return ("⚠️", f"La semana {fila.semanas_atipicas} se salió del patrón y se excluyó. "
                f"Con promedio simple la proyección sería **{fila.promedio_simple:,.1f} {u}**; "
                f"descartándola queda en **{fila.consumo_proyectado:,.1f} {u}**.")
    if abs(tend) > 0.12:
        rumbo = "creciendo" if tend > 0 else "cayendo"
        return ("📈" if tend > 0 else "📉",
                f"El consumo viene {rumbo} **{abs(tend)*100:.0f}%** en las 6 semanas. "
                f"El promedio simple daría {fila.promedio_simple:,.1f} {u} y se quedaría corto: "
                f"la proyección sigue la tendencia hasta **{fila.consumo_proyectado:,.1f} {u}**.")
    if disp < 0.15:
        return ("✅", f"Serie estable: varía menos de {max(disp,0.01)*100:.0f}% entre semanas. "
                f"Se proyectan **{fila.consumo_proyectado:,.1f} {u}** con alta confianza.")
    return ("〰️", f"Serie irregular (varía {disp*100:.0f}% entre semanas) pero sin un patrón "
            f"claro ni valores atípicos. Se proyectan **{fila.consumo_proyectado:,.1f} {u}**.")


def grafico_serie(fila, hist):
    """Barras cronológicas con la proyección destacada al final.

    Se usa Altair en vez de st.bar_chart para poder controlar el orden, el
    color por categoría, las etiquetas horizontales y la regla del promedio.
    """
    atipica = fila.semanas_atipicas or ""
    filas = []
    for i, v in enumerate(hist):
        s = f"S{i+1}"
        filas.append({"Semana": f"Sem {i+1}", "Consumo": float(v), "orden": i,
                      "Tipo": "Semana descartada" if s == atipica else "Histórico"})
    filas.append({"Semana": "Próxima", "Consumo": float(fila.consumo_proyectado),
                  "orden": len(hist), "Tipo": "Proyección"})
    serie = pd.DataFrame(filas)

    icono, texto = diagnostico_serie(fila, hist)
    st.markdown(f"{icono} {texto}")

    escala = alt.Scale(domain=["Histórico", "Semana descartada", "Proyección"],
                       range=[AZUL, GRIS, NARANJA])
    # El orden va explícito como lista: con sort por campo Altair reordena
    # alfabéticamente y "Próxima" termina antes que "Sem 1".
    orden_x = [f"Sem {i+1}" for i in range(len(hist))] + ["Próxima"]
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
    st.caption(f"Línea punteada = promedio simple ({fila.promedio_simple:,.1f} "
               f"{fila.unidad_base}), el método que estamos reemplazando.")


def grafico_comparativo(df, ingrediente_id, sucursal_activa):
    """Cobertura del mismo ingrediente en las 4 sucursales.

    La cobertura es comparable entre sucursales aunque tengan tamaños muy
    distintos, porque ya viene normalizada por el consumo propio de cada una.
    Sirve para ver de un golpe quien se sale del patrón del grupo.
    """
    comp = df[(df.ingrediente_id == ingrediente_id) & df.cobertura.notna()].copy()
    if len(comp) < 2:
        st.caption("Solo una sucursal maneja este ingrediente: no hay con qué comparar.")
        return

    comp = comp.sort_values("cobertura", ascending=False)
    comp["Sucursal"] = comp.sucursal
    comp["Cobertura"] = comp.cobertura.clip(upper=4)   # recorta la barra para que
    comp["real"] = comp.cobertura                      # una sucursal extrema no
    comp["Estado"] = comp.estado.map(ETIQUETA).fillna("OK")  # aplaste al resto
    # Un único orden explícito para todas las capas: con sort="-x" en cada capa
    # por separado, Vega las ordena distinto y los números caen sobre la barra
    # equivocada.
    orden_y = comp.Sucursal.tolist()

    # Lectura del gráfico. Se compara contra la mediana de las otras sucursales,
    # que es lo que responde de verdad la pregunta "está pidiendo raro?".
    act = comp[comp.Sucursal == sucursal_activa]
    otras = comp[comp.Sucursal != sucursal_activa].real
    if not act.empty and len(otras):
        mia, tipica = float(act.real.iloc[0]), float(otras.median())
        desvio = (mia - tipica) / tipica if tipica else 0
        if abs(desvio) < 0.25:
            st.markdown(f"✅ **{sucursal_activa}** pide en línea con el resto de la red "
                        f"({mia:,.2f} contra {tipica:,.2f} semanas típicas).")
        else:
            lado = "por encima" if desvio > 0 else "por debajo"
            st.markdown(f"🔍 **{sucursal_activa}** se sale del patrón del grupo: "
                        f"cubre **{mia:,.2f} semanas**, un **{abs(desvio)*100:.0f}% {lado}** "
                        f"de las {tipica:,.2f} típicas en las demás sucursales.")

    eje_y = alt.Y("Sucursal:N", title=None, sort=orden_y,
                  axis=alt.Axis(labelFontSize=12, labelLimit=180,
                                labelOverlap=False))

    barras = alt.Chart(comp).mark_bar(cornerRadiusEnd=3, height=24).encode(
        y=eje_y,
        x=alt.X("Cobertura:Q", title="Semanas de cobertura",
                scale=alt.Scale(domainMin=0, nice=True)),
        color=alt.Color("Estado:N", scale=ESCALA_ESTADO, legend=None),
        opacity=alt.condition(alt.datum.Sucursal == sucursal_activa,
                              alt.value(1.0), alt.value(0.40)),
        tooltip=[alt.Tooltip("Sucursal:N"), alt.Tooltip("real:Q", title="Cobertura", format=",.2f"),
                 alt.Tooltip("Estado:N")],
    )
    etiq = alt.Chart(comp).mark_text(dx=7, align="left", fontSize=12,
                                     color="#C9D1D9").encode(
        y=eje_y, x="Cobertura:Q", text=alt.Text("real:Q", format=",.2f"))

    bandas = alt.Chart(pd.DataFrame({"x": [0.90, 1.25]})).mark_rule(
        strokeDash=[4, 4], color="#8B8B8B", size=1).encode(x="x:Q")

    st.altair_chart((barras + etiq + bandas).properties(height=46 * len(comp) + 30),
                    width="stretch")
    st.caption("Cobertura = semanas que alcanza el stock más lo pedido. Las dos "
               "líneas punteadas marcan el rango sano (0.90 a 1.25): a la izquierda "
               "se queda corto, a la derecha sobra. La sucursal seleccionada va "
               "resaltada y las demás atenuadas.")


ESCALA_ESTADO = alt.Scale(
    domain=["Olvido", "Riesgo de quiebre", "Sobre-pedido", "Dato incompleto",
            "Justo", "OK"],
    range=[COLOR["OLVIDO"], COLOR["QUIEBRE"], COLOR["EXCESO"],
           COLOR["SIN_CATALOGO"], COLOR["AJUSTADO"], "#2F5D45"])


def mapa_calor(df):
    """Toda la red en una sola vista: ingredientes x sucursales.

    Cada celda es una línea de orden. El número es la corrección sugerida en
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
                              labelPadding=8, labelOverlap=False)),
        y=alt.Y("nombre:N", title=None, sort=orden_ing,
                axis=alt.Axis(labelFontSize=11, labelPadding=6,
                              labelOverlap=False)),
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
    st.caption("Cada celda es una línea de la orden. El número es el ajuste "
               "sugerido en formatos: +7 significa pedir 7 más, -18 pedir 18 menos. "
               "Las celdas en blanco ya están bien.")


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------

@st.cache_data
def datos_base():
    return motor.cargar_datos()


st.sidebar.title("🍕 Barrio Pizza")
st.sidebar.caption("Revisión automática de órdenes de compra")

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
            st.sidebar.success(f"Orden cargada: {len(nueva)} líneas")
    except Exception as e:
        st.sidebar.error(f"No se pudo leer el archivo: {e}")

st.sidebar.subheader("Parámetros")
colchon = st.sidebar.slider(
    "Margen de seguridad", 0, 30, 0, 5,
    help="Porcentaje extra sobre el consumo proyectado, como colchón.") / 100
sensibilidad = st.sidebar.slider(
    "Sensibilidad a semanas atípicas", 2.0, 6.0, 3.5, 0.5,
    help="Más bajo = descarta más semanas raras del histórico.")

st.sidebar.subheader("Método de proyección")
ingenuo = st.sidebar.toggle(
    "Usar promedio simple",
    help="Apaga la detección de semanas atípicas y la tendencia. Sirve para "
         "comparar contra el método que se está reemplazando.")
modo = "promedio" if ingenuo else "robusto"
st.sidebar.caption("Promedio simple de las 6 semanas, sin filtrar nada."
                   if ingenuo else
                   "Descarta semanas atípicas y sigue la tendencia.")

df_total = motor.construir_analisis(datos, sensibilidad=sensibilidad,
                                    colchon=colchon, modo=modo)

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

st.title("Revisión de órdenes de compra")
if foco:
    st.caption(f"Viendo solo **{foco}** · {res['lineas']} líneas · "
               f"pulsa la sucursal de nuevo para ver toda la red")
else:
    st.caption(f"{df.sucursal.nunique()} sucursales · {df.ingrediente_id.nunique()} ingredientes · "
               f"{res['lineas']} líneas revisadas")

if ingenuo:
    st.warning("**Modo promedio simple activo.** Se apagaron la detección de "
               "semanas atípicas y la tendencia. Las cifras de abajo son las que "
               "daría el método que estamos reemplazando.", icon="⚠️")

c = st.columns(5)
c[0].metric("Alertas activas", res["alertas"])
c[1].metric("Riesgo de quiebre", res["quiebres"])
c[2].metric("Sobre-pedido", res["excesos"])
c[3].metric("Formatos de más", res["formatos_de_mas"])
c[4].metric("Formatos faltantes", res["formatos_faltantes"])

st.divider()


# ---------------------------------------------------------------------------
# Semáforo por sucursal - cada uno filtra todo el tablero
# ---------------------------------------------------------------------------

GRAVES = ["OLVIDO", "QUIEBRE", "SIN_CATALOGO"]
cols = st.columns(df_total.sucursal.nunique())
for col, suc in zip(cols, sorted(df_total.sucursal.unique())):
    s = df_total[df_total.sucursal == suc]
    n_grave = int(s.estado.isin(GRAVES).sum())
    n_exceso = int((s.estado == "EXCESO").sum())
    if n_grave:
        icono, texto = "🔴", f"{n_grave} crítica" + ("s" if n_grave > 1 else "")
    elif n_exceso:
        icono, texto = "🟡", f"{n_exceso} sobre-pedido" + ("s" if n_exceso > 1 else "")
    else:
        icono, texto = "🟢", "sin alertas"
    activo = (foco == suc)
    if col.button(f"{icono}  **{suc}** - {texto}", key=f"sem_{suc}",
                  width="stretch", type="primary" if activo else "secondary"):
        # Volver a pulsar la sucursal activa quita el filtro.
        st.session_state.foco = None if activo else suc
        st.rerun()

st.divider()

tab0, tab1, tab2, tab3 = st.tabs(
    ["Panorama", "Alertas", "Detalle por sucursal", "Orden corregida"])


# ---------------------------------------------------------------------------
# Tab 0 - Panorama de toda la red
# ---------------------------------------------------------------------------

with tab0:
    p1, p2 = st.columns([2.2, 1])
    with p1:
        mapa_calor(df)
    with p2:
        st.markdown("##### Donde duele más")
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
                st.markdown(f"**{r.sucursal}** - {r.alertas} alertas")
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
            # labelOverlap=False obliga a Vega a dibujar las etiquetas de todas
            # las barras; por defecto borra las que cree que se solapan y quedan
            # barras anonimas. La altura se calcula para que quepan de verdad.
            orden_prov = imp.proveedor.tolist()
            st.altair_chart(
                alt.Chart(imp).mark_bar(cornerRadiusEnd=3, color=AZUL, height=20).encode(
                    y=alt.Y("proveedor:N", title=None, sort=orden_prov,
                            axis=alt.Axis(labelFontSize=11, labelOverlap=False,
                                          labelLimit=150, labelPadding=6)),
                    x=alt.X("ajuste:Q", title="Formatos a corregir"),
                    tooltip=[alt.Tooltip("proveedor:N", title="Proveedor"),
                             alt.Tooltip("ajuste:Q", title="Formatos", format=",.0f")],
                ).properties(height=38 * len(imp) + 60), width="stretch")


# ---------------------------------------------------------------------------
# Tab 1 - Alertas
# ---------------------------------------------------------------------------

with tab1:
    if alertas.empty:
        st.success("Ninguna orden presenta desviaciones. Todo listo para aprobar.")
    else:
        izq, der = st.columns([3, 1])
        # Mismos keys atados al foco: al filtrar desde el semáforo cambian las
        # opciones y una seleccion vieja quedaría fuera de la lista.
        f_suc = der.multiselect("Sucursal", sorted(alertas.sucursal.unique()),
                                key=f"fsuc_{foco}")
        f_est = der.multiselect("Tipo", sorted({ETIQUETA[e] for e in alertas.estado}),
                                key=f"fest_{foco}")
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
                        f"Se ignoró la semana atípica {a.semanas_atipicas} al proyectar.</span>")
            elif a.tendencia_pct and abs(a.tendencia_pct) > 0.12:
                signo = "creciente" if a.tendencia_pct > 0 else "decreciente"
                nota = (f"<br><span style='font-size:.78rem;opacity:.65'>"
                        f"Tendencia {signo} de {a.tendencia_pct*100:+.0f}% en el histórico.</span>")
            izq.markdown(
                f"""<div class="alerta" style="border-left-color:{color}">
                    <span class="chip" style="background:{color}">{ETIQUETA[a.estado]}</span>
                    <span style="font-size:.78rem;opacity:.6">{a.proveedor}</span>
                    <div class="t">{a.titulo}</div>
                    <div class="d">{a.detalle}{nota}</div>
                    <div class="a" style="color:{color}">→ {a.accion}</div>
                </div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tab 2 - Detalle por sucursal
# ---------------------------------------------------------------------------

with tab2:
    # Los dos filtros viven juntos, arriba del contenido que controlan.
    # Antes la sucursal estaba al tope de la pestana y obligaba a subir cada vez.
    fc1, fc2 = st.columns([1, 1.4])
    if foco:
        # Con el filtro global activo no tiene sentido un segundo selector de
        # sucursal: quedaría con una sola opcion y Streamlit conserva el valor
        # anterior, que ya no esta en la lista, dejando el campo en rojo.
        suc = foco
        fc1.markdown("Sucursal")
        fc1.markdown(f"### {foco}")
        fc1.caption("Filtro activo desde el semáforo")
    else:
        suc = fc1.selectbox("Sucursal", sorted(df.sucursal.unique()))
    sub = df[df.sucursal == suc].copy()

    # El desplegable arranca por el ingrediente más problematico de la sucursal:
    # abrir la pestana en un caso plano no le dice nada a quien aprueba órdenes.
    opciones = (sub.dropna(subset=["nombre"])
                   .sort_values(["severidad", "nombre"], ascending=[False, True]))
    etiquetas_sel = [
        f"{'●  ' if r.estado in ETIQUETA and r.estado != 'AJUSTADO' else ''}{r.nombre}"
        for r in opciones.itertuples()]
    mapa_sel = dict(zip(etiquetas_sel, opciones.nombre))
    # key atado a la sucursal: al cambiarla la lista de ingredientes cambia y
    # sin esto Streamlit intenta conservar una seleccion que ya no existe.
    elegido = mapa_sel[fc2.selectbox("Ingrediente  (● = tiene alerta)",
                                     etiquetas_sel, key=f"ing_{suc}")]
    fila = opciones[opciones.nombre == elegido].iloc[0]
    hist = fila.historico if isinstance(fila.historico, list) else []

    # Ficha del ingrediente: los números que sostienen la decision, sin tener
    # que buscarlos en la tabla.
    u = fila.unidad_base
    dif = int(fila.formatos_sugeridos - fila.pedido_formatos)
    k = st.columns(5)
    k[0].metric("Proyección", f"{fila.consumo_proyectado:,.1f} {u}",
                f"{fila.consumo_proyectado - fila.promedio_simple:+,.1f} vs prom. simple",
                delta_color="off")
    k[1].metric("Stock actual", f"{fila.stock:,.1f} {u}")
    k[2].metric("Pide", f"{fila.pedido_formatos:,.0f}", help=fila.formato_compra)
    k[3].metric("Sugerido", f"{fila.formatos_sugeridos:,.0f}",
                f"{dif:+d} formatos" if dif else "sin cambio",
                delta_color="inverse" if dif else "off")
    k[4].metric("Cobertura", f"{fila.cobertura:,.2f} sem" if pd.notna(fila.cobertura) else "-",
                ETIQUETA.get(fila.estado, "OK"), delta_color="off")

    if hist:
        grafico_serie(fila, hist)

    # Siempre contra la red completa: comparar contra un subconjunto filtrado
    # vaciaria el gráfico justo cuando hay un foco activo.
    st.markdown(f"##### {elegido} en las demás sucursales")
    grafico_comparativo(df_total, fila.ingrediente_id, suc)

    # La tabla completa pasa al final y colapsada: es material de consulta,
    # no lo primero que uno necesita ver.
    with st.expander(f"Ver tabla completa de {suc}  ({len(sub)} líneas)"):
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
# Tab 3 - Orden corregida por proveedor
# ---------------------------------------------------------------------------

with tab3:
    st.caption("Cada proveedor recibe su orden por separado. Acá está la versión "
               "sugerida, ya agrupada y lista para enviar.")
    corr = motor.orden_corregida(df)
    solo_cambios = st.checkbox("Mostrar solo líneas que cambian", value=True)
    vista = corr[corr.Diferencia != 0] if solo_cambios else corr

    for prov in sorted(vista.Proveedor.unique()):
        bloque = vista[vista.Proveedor == prov]
        with st.expander(f"{prov} - {len(bloque)} líneas", expanded=True):
            st.dataframe(bloque.drop(columns=["Proveedor"]),
                         width="stretch", hide_index=True)

    buf = io.StringIO()
    corr.to_csv(buf, index=False)
    st.download_button("Descargar orden corregida (CSV)", buf.getvalue(),
                       "orden_corregida.csv", "text/csv")

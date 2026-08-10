# Revisión de órdenes de compra - Barrio Pizza

Una herramienta que revisa las órdenes semanales de las sucursales y avisa cuándo están
pidiendo de más, de menos, o se olvidaron de algo.

**App en vivo:** https://barrio-pizza-ord-mora.streamlit.app

**Video de demostración:** https://drive.google.com/drive/folders/1PJjStDNqEk-3VEMG04maw-ZWmg_MBdGk

---

## Qué problema resuelve

Cada semana las cuatro sucursales mandan su lista de compras y la gerente las aprueba a
ojo. Son 4 listas de 22 productos, o sea casi 90 líneas para revisar una por una. Es lento
y se escapan cosas en las dos direcciones: piden de más y se les vence el producto, o
piden de menos y se quedan sin queso un viernes en la noche.

Con los datos de esta semana, la herramienta encuentra 5 problemas reales entre esas 90
líneas, y para cada uno dice qué hacer.

## Para correrlo

```bash
pip install -r requirements.txt
streamlit run app.py
```

Los CSV están en `datos/`. Para revisar otra semana no hay que tocar archivos: se sube el
CSV de órdenes desde la barra lateral.

---

## Cómo funciona

### Primero: cuánto van a consumir la próxima semana

Todo arranca de acá. Si no sé cuánto va a gastar una sucursal, no puedo saber cuánto
debería comprar.

Lo obvio sería sacar el promedio de las 6 semanas. El problema es que el promedio falla
justo en los dos casos que importan, y los datos traen uno de cada uno.

Marbella consume pepperoni así: 28, 30, **150**, 27, 29, 31. Esa semana de 150 kg es un
error de captura o una fiesta, pero no es la nueva normalidad. El promedio la toma en
serio y proyecta 49 kg, cuando la verdad son 30.

Costa del Este consume harina así: 240, 255, 268, 284, 300, 316. Viene subiendo 33% en
seis semanas y no hay razón para pensar que va a parar el lunes. El promedio dice 277 y se
queda corto.

Una serie pide **ignorar** lo raro. La otra pide **seguir** el rumbo. Por eso el método
tiene tres pasos:

**1. Descartar semanas atípicas.** Uso MAD: mediana de las desviaciones absolutas. Mido
qué tan lejos está cada semana de la mediana, usando como vara la dispersión normal de esa
misma serie. Va con mediana y no con promedio a propósito, porque si midiera con el promedio, el
valor extremo contaminaría la vara con la que lo estoy midiendo.

**2. Trazar una tendencia** sobre las semanas que quedan, por mínimos cuadrados. Acá está
lo que el promedio no puede hacer: el promedio no sabe en qué orden llegaron los datos. Si
barajo las seis semanas, da idéntico. Pero en compras el orden lo es todo, porque no es lo mismo
una sucursal que viene subiendo que una que viene bajando, aunque hayan gastado el mismo
total.

**3. Acotar el resultado** entre 80% y 130% del promedio limpio, para que con series de
solo 6 puntos la extrapolación no se dispare.

Resultado en los dos casos:

| | Promedio simple | Este método |
|---|---|---|
| Marbella, pepperoni | 49.2 kg | **30.0 kg** |
| Costa del Este, harina | 277.2 kg | **330.3 kg** |

Dejé un interruptor en la barra lateral, **"Usar promedio simple"**, que apaga todo esto.
Sirve para ver el contraste en vivo: con el promedio aparece una alerta de quiebre falsa
en Marbella, y la alerta real de Costa del Este se queda 3 sacos corta.

### Después: cuánto le falta

```
necesidad = consumo proyectado - lo que tiene en bodega
```

Los dos en unidad base: kilos, litros o unidades.

### Y por último: cuántos bultos son

Acá está el detalle que define el problema. El consumo y el inventario vienen en kilos,
pero **las órdenes vienen en formatos**: sacos, cajas, latas, paquetes.

```
formatos sugeridos = techo( necesidad / lo que trae un formato )
```

Siempre hacia arriba, porque no existe medio saco y quedarse corto es peor que que sobre
un poco.

Y el rango de conversión es enorme: un paquete de albahaca trae 250 gramos, un paquete de
cajas de pizza trae 50 unidades. Son 200 veces de diferencia. Pedir "20" no significa nada
hasta saber de qué producto estamos hablando.

### La métrica que uso para comparar: cobertura

```
cobertura = (stock + pedido convertido a kilos) / consumo proyectado
```

O sea: **para cuántas semanas le alcanza lo que va a tener en mano**.

| Cobertura | Estado |
|---|---|
| menos de 0.90 | **QUIEBRE** - se queda sin producto |
| 0.90 a 1.00 | **JUSTO** - alcanza exacto, sin margen |
| 1.00 a 1.25 (1.15 si es perecedero) | **OK** - lo que sobra es redondeo |
| pasa el umbral **y** sobra al menos 1 formato entero | **EXCESO** - pidió de más de verdad |

Más dos casos especiales: **OLVIDO** cuando necesita algo y no lo pidió, y
**SIN CATÁLOGO** cuando pidió algo que no existe.

---

## Por qué 5 alertas y no 18

Esta fue la decisión que más cambió el proyecto, y vale la pena explicarla.

La primera versión comparaba lo pedido contra lo necesario y marcaba toda diferencia.
Salían 18 alertas. Cuando las revisé una por una, la mayoría eran por sobrantes de gramos
que la sucursal no podía evitar.

El caso típico: Marbella necesita 24.27 kg de cebolla y el saco trae 20. Tiene que llevar
2 sacos. Le van a sobrar 15.7 kg, pero no pidió de más, pidió lo mínimo que le alcanzaba.
Es como comprar huevos: si necesitas 13 y el cartón trae 12, compras 2 cartones y te
sobran 11. Nadie hizo nada mal.

Entonces cambié el criterio: solo aviso de sobre-pedido si la cobertura pasa el umbral
**y** lo que sobra llega a un bulto completo. Con eso quedan 5 alertas, y las 5 son
reales.

El contraste se ve claro con el mismo producto en dos sucursales:

| | Costa del Este | Brisas del Golf |
|---|---|---|
| Cobertura | 1.27 | 2.71 |
| Le sobra | 9.7 kg (medio saco) | 70.7 kg (3 sacos y medio) |
| Estado | OK | **EXCESO** |

Misma cebolla, mismo saco de 20 kg. La diferencia no es el umbral: es si el sobrante era
**inevitable** o **evitable**.

Los 11 casos que quedan en JUSTO no los borré, están detrás de un checkbox. Si la gerente
sabe que viene un feriado, querrá mirarlos. Pero no compiten por atención con lo urgente.
Una herramienta que grita por todo deja de usarse al tercer día.

---

## Qué encuentra en los datos de esta semana

| Gravedad | Qué pasa | Qué hacer |
|---|---|---|
| 100 | Brisas del Golf **no pidió mozzarella**. Consume 202 kg por semana y tiene 22 en bodega | Agregar 19 cajas |
| 82 | Costa del Este pide 150 kg menos de harina de lo que va a consumir | Subir a 13 sacos (+7) |
| 82 | Vía Argentina pide 4.5 kg de más de albahaca, y es perecedera | Bajar a 2 paquetes (-18) |
| 56 | Brisas del Golf pide 70.7 kg de más de cebolla | Bajar a 2 sacos (-3) |
| 55 | Costa del Este pidió `aji_chombo`, que no está en el catálogo | Darlo de alta o corregir el código |

Más 11 casos en JUSTO, ocultos por defecto.

### La mozzarella es el caso difícil, y vale explicar por qué

Un producto que **nadie pidió** no genera ninguna fila en el archivo de órdenes. Si uno
arma el análisis partiendo de la orden y le cruza el catálogo, esa línea simplemente no
existe y el problema queda invisible. No hay nada que mirar.

Por eso armo la tabla al revés: primero el cruce completo de todas las sucursales contra
todos los ingredientes, tomando el universo de las tres fuentes, y recién después le pego
los datos con `merge` de tipo `outer`. Así la fila sobrevive aunque no esté en la orden, y
ahí salta el olvido.

El mismo criterio, al revés, es lo que hace aparecer el `aji_chombo`: está en la orden pero
no en el catálogo, y también sobrevive al cruce.

---

## Qué hace cuando faltan datos

| Situación | Qué hace |
|---|---|
| Está en la orden pero no en el catálogo | Alerta de dato incompleto. No lo multiplica por un factor que no existe, que daría `NaN` y fallaría en silencio |
| Está en el catálogo pero no en la orden | Sobrevive al cruce. Si lo necesita, alerta de olvido |
| Sin stock registrado | Asume 0 |
| Sin histórico | Asume 0 y no proyecta |
| Menos de 3 semanas limpias | Usa la mediana en vez de la regresión |
| Sin histórico, sin stock y sin pedido | Descarta la fila, no aporta nada |
| CSV con BOM | Los lee con `encoding="utf-8-sig"` |
| CSV subido sin las columnas que van | Mensaje de error claro, no una excepción |

---

## Supuestos que hice

1. **Cubro una semana.** Los formatos sugeridos alcanzan para la semana que viene, no
   acumulan stock para varias.
2. **S1 a S6 van en orden**, S1 la más vieja y S6 la más reciente.
3. **No hay lead time ni stock de seguridad**, más allá del margen que se puede ajustar
   desde la barra lateral. En producción habría que sumar el tiempo de entrega de cada
   proveedor.
4. **Los formatos son indivisibles.** No se puede comprar medio saco.
5. **No modelo estacionalidad.** Con 6 puntos no hay con qué.
6. **Los perecederos toleran menos sobrante** (umbral 1.15 en vez de 1.25). Es criterio de
   negocio, se puede cambiar.
7. **El inventario está al día** cuando se arma la orden.
8. Dejé los nombres tal como vienen en los CSV, sin arreglarles los acentos, para no
   alterar los datos que me entregaron.

---

## Cómo está armado

```
barrio-pizza-ordenes/
├── motor.py          # toda la lógica - no sabe que Streamlit existe
├── app.py            # la interfaz
├── requirements.txt
└── datos/            # los 4 CSV
```

`motor.py` no importa Streamlit ni depende de ninguna pantalla. Carga, proyección, cruce,
alertas y orden corregida viven ahí, y se pueden llamar desde una API, un job programado o
un módulo de Odoo sin cambiar nada.

| Función | Qué hace |
|---|---|
| `cargar_datos()` | Lee los 4 CSV |
| `proyectar_consumo()` | Proyecta cada serie |
| `construir_analisis()` | Cruza todo en una tabla |
| `generar_alertas()` | Traduce números a alertas, ordenadas por gravedad |
| `orden_corregida()` | El pedido sugerido, agrupable por proveedor |
| `resumen()` | Los KPIs de arriba |

Nada en el motor asume que son 4 sucursales. Con las 10 funciona igual.

---

## Cómo lo conectaría a Odoo

Hoy lee CSV porque es lo que había. En producción los CSV desaparecen y el motor se
alimenta directo del ERP. Lo que no cambiaría es `motor.py`.

### De dónde saldría cada dato

| Hoy | En Odoo |
|---|---|
| `ingredientes.csv` | `product.template`. El formato de compra ya existe como unidad de compra (`uom_po_id`) y el factor de conversión vive en `uom.uom` |
| `consumo_historico.csv` | Los `stock.move` de salida por almacén, agrupados por semana |
| `inventario_actual.csv` | `stock.quant` por ubicación |
| `orden_compra_semana.csv` | Las `purchase.order.line` en borrador |
| Sucursales | `stock.warehouse` |
| Proveedores | `res.partner` con `supplier_rank > 0` |

Vale la pena notar que Odoo ya resuelve por su cuenta la conversión entre unidad base y
unidad de compra, que es la mitad del problema de este reto.

### En qué orden lo haría

**Primero, un módulo que solo lee.** Un addon que consulte esas tablas y corra el motor,
mostrando las alertas en su propia vista. No escribe nada. Es la manera de ganar confianza
sin riesgo: la gerente compara las sugerencias contra su criterio durante unas semanas y
ve si le sirven.

**Después, meter las alertas en el flujo.** Un widget en la vista de `purchase.order` que
muestre los avisos al abrir la orden en borrador, antes de confirmarla. El comprador la ve
donde ya está trabajando, sin cambiar de pantalla.

**Al final, que sugiera solo.** Un cron semanal que genere las órdenes en borrador ya
corregidas y agrupadas por proveedor, para que solo haya que revisar y confirmar.

### Qué le faltaría

- **Lead time por proveedor** para cubrir el tiempo de entrega además de la semana de
  consumo.
- **Stock de seguridad** por producto y almacén. En Odoo ya existe como regla de
  reabastecimiento.
- **Costos**, para poder decir "$1,200 inmovilizados" en vez de "18 paquetes de más". Mueve
  mucho más a quien aprueba.
- **Guardar las decisiones**: cuándo la gerente ignora una sugerencia y por qué. Con eso se
  calibran los umbrales con datos de uso real en vez de a criterio.
- Cuando haya años de histórico en lugar de 6 semanas, cambiar la tendencia lineal por un
  modelo que entienda estacionalidad.

---

## Cómo usé IA

Trabajé todo el desarrollo con Claude, y creo que importa más *cómo* lo usé que el hecho
de haberlo usado.

**Donde más sirvió fue en las decisiones, no en escribir código.** La conversación que
definió el proyecto no fue sobre sintaxis: fue sobre qué métrica usar. La primera versión
comparaba formatos pedidos contra necesarios y tiraba 18 alertas. Cuando las revisé, casi
todas eran falsas por redondeo. De discutir eso salió la métrica de cobertura y la regla
del formato completo, que es lo que bajó las alertas a 5. Esa diferencia, 18 ruidosas
contra 5 accionables, es la que decide si la herramienta se usa o se abandona, y no salió
de escribir mejor código sino de mirar la salida y preguntarme si tenía sentido.

**Verifiqué lo que la IA me afirmaba.** Dos casos concretos:

Me dijo que moviendo el control de sensibilidad de 3.5 a 6.0 iba a ver cómo la semana
atípica volvía a entrar al cálculo, y que eso servía para el video. Lo probé y no pasaba
nada. Al calcularlo, el pico de 150 kg está a 54 desviaciones robustas de la mediana:
ningún valor del slider puede incluirlo. La afirmación era falsa. De ahí salió el
interruptor de "promedio simple", que sí produce un contraste real.

Otro: un reemplazo automático de acentos le puso tildes también a los nombres de
variables. Python acepta identificadores con tilde, así que compilaba sin quejarse, pero
`motor.py` empezó a escribir la columna `"histórico"` mientras `app.py` seguía leyendo
`.historico`. Habría reventado recién al abrir una pestaña específica. Lo agarré revisando
los tokens del código antes de desplegar.

**Y varias veces le corregí el criterio visual.** El gráfico de series salió con las
etiquetas rotadas, la proyección puesta al principio en vez de al final, y barras planas
que no comunicaban nada. El comparativo entre sucursales salió con los números encima de
las barras equivocadas. Los dos se rehicieron después de verlos en pantalla y decir que no
se entendían.

**Lo que me llevo:** la IA acelera muchísimo y propone buenos enfoques, pero no reemplaza
mirar el resultado y desconfiar. El trabajo real estuvo en decidir qué construir, comprobar
que los números cuadraran con los datos, y descartar lo que no servía. Los bugs más
peligrosos que me encontré no tiraban error: devolvían resultados que parecían correctos y
no lo eran. Esos solo se agarran verificando.

---

## Bonus que alcancé a hacer

- [x] Proyección más inteligente que un promedio (MAD + tendencia)
- [x] Detección de órdenes raras comparando cada sucursal contra la mediana del grupo
- [x] Pedido corregido agrupado por proveedor, descargable en CSV
- [x] Carga de órdenes desde la interfaz
- [x] Mapa de calor de toda la red, filtro global por sucursal, parámetros de negocio
      ajustables desde la barra lateral y un diagnóstico en texto de cada serie

## Con más tiempo

- Chat en lenguaje natural sobre los datos.
- Poder editar las órdenes desde la interfaz, no solo cargarlas.
- Expresar las alertas en dinero además de en bultos.
- Tests del motor con casos armados para cada estado.

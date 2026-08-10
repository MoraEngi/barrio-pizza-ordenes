# Revisión automática de órdenes de compra - Barrio Pizza

Herramienta que revisa las órdenes de compra semanales de las sucursales y
levanta alertas cuando piden de más, de menos, o se olvidaron de algo.

## Cómo correrlo

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Estructura

- `motor.py` - lógica de negocio pura (proyección, alertas). No depende de la interfaz.
- `app.py` - dashboard Streamlit.
- `datos/` - los 4 CSV del reto.

*(Este README se completa en la fase final con supuestos, metodología e integración con Odoo.)*

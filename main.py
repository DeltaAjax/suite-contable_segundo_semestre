# main.py - Aplicación NiceGUI de Autoevaluación Financiera NIF V3 (Tema FACPYA) + Supabase
import os
from dataclasses import dataclass
from nicegui import ui
from supabase import create_client, Client

from catalog import (
    CATALOGO_V3,
    Clasificacion,
    CuentaV3,
    NIF,
    NIFS_POR_CLASIFICACION,
    SeccionCapital,
    crear_cuenta_balance_dinamica,
    crear_cuenta_capital_dinamica,
    listar_cuentas_por_clasificacion,
)
from engine import (
    MovimientoERI,
    MovimientoESF,
    ResultadoERI,
    ResultadoESF,
    calcular_eri,
    calcular_esf,
    generar_banner_verificacion,
    formatear_moneda,
)
from capital_contable import (
    EstadoCambiosCapital,
    generar_estado_cambios_capital,
    validar_consistencia_con_esf,
)
from flujo_efectivo import (
    ResultadoFlujoEfectivo,
    generar_flujo_indirecto,
    generar_flujo_directo,
)
from pdf_exporter import generar_pdf_estados_financieros
from excel_exporter import generar_excel_estados_financieros

# ==========================================
# 1. CONFIGURACIÓN E INICIALIZACIÓN SUPABASE
# ==========================================
SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ADVERTENCIA: Las variables de entorno de SUPABASE no están configuradas.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ==========================================
# 2. ESTRUCTURAS DE DATOS DE LA INTERFAZ
# ==========================================
@dataclass
class CapitalDinamicaRow:
    nombre_input: ui.input
    actual_input: ui.number
    anterior_input: ui.number
    seccion_select: ui.select
    reductora_check: ui.checkbox


@dataclass
class SubcuentaDinamicaRow:
    nombre_input: ui.input
    actual_input: ui.number
    anterior_input: ui.number
    clasificacion_select: ui.select
    nif_select: ui.select
    complementaria_check: ui.checkbox


filas_capital_dinamico: list[CapitalDinamicaRow] = []
filas_subcuentas_dinamicas: list[SubcuentaDinamicaRow] = []
inputs_cuentas_fijas: dict[str, tuple[ui.number, ui.number]] = {}

resultados_container: ui.column | None = None


# ==========================================
# 3. FUNCIONES DE BASE DE DATOS (SUPABASE)
# ==========================================
def guardar_practica_supabase(empresa: str, periodo: str) -> int | None:
    """Registra una práctica/evaluación financiera en Supabase."""
    try:
        respuesta = supabase.table("practicas").insert({
            "nombre": f"{empresa} ({periodo})"
        }).execute()
        if respuesta.data:
            return respuesta.data[0]["id"]
    except Exception as e:
        ui.notify(f"Error al guardar práctica en Supabase: {str(e)}", type="negative")
    return None


def guardar_movimientos_supabase(practica_id: int, movimientos_esf: list[MovimientoESF], movimientos_eri: list[MovimientoERI]):
    """Guarda todos los saldos/movimientos de la autoevaluación en Supabase."""
    registros = []
    
    for mov in movimientos_esf:
        registros.append({
            "practica_id": practica_id,
            "concepto": mov.cuenta.nombre,
            "monto": mov.monto_actual,
            "tipo": "ESF_ACTUAL"
        })
        if mov.monto_anterior != 0.0:
            registros.append({
                "practica_id": practica_id,
                "concepto": mov.cuenta.nombre,
                "monto": mov.monto_anterior,
                "tipo": "ESF_ANTERIOR"
            })

    for mov in movimientos_eri:
        registros.append({
            "practica_id": practica_id,
            "concepto": mov.cuenta.nombre,
            "monto": mov.monto,
            "tipo": "ERI"
        })

    if registros:
        try:
            supabase.table("movimientos_financieros").insert(registros).execute()
            ui.notify("Práctica guardada correctamente en la base de datos.", type="positive")
        except Exception as e:
            ui.notify(f"Error al guardar movimientos en Supabase: {str(e)}", type="negative")


# ==========================================
# 4. LÓGICA AUXILIAR Y CONSTRUCCIÓN DE DATOS
# ==========================================
def _extraer_float(elem) -> float:
    try:
        if elem is None:
            return 0.0
        val = elem.value if hasattr(elem, 'value') else elem
        if val is None:
            return 0.0
        return float(val)
    except Exception:
        return 0.0


def _validar_nombres_duplicados(filas, etiqueta_catalogo: str) -> bool:
    nombres = [(fila.nombre_input.value or "").strip() for fila in filas]
    nombres = [n for n in nombres if n]
    duplicados = sorted({n for n in nombres if nombres.count(n) > 1})
    if duplicados:
        ui.notify(
            f"Nombres duplicados en {etiqueta_catalogo}: {', '.join(duplicados)}. "
            "Cada subcuenta debe tener un nombre exacto único.",
            type="negative",
        )
        return True
    return False


def _construir_movimientos_esf() -> list[MovimientoESF]:
    movimientos: list[MovimientoESF] = []
    for cuenta in CATALOGO_V3.values():
        if cuenta.clasificacion == Clasificacion.RESULTADO:
            continue
        if cuenta.nombre in inputs_cuentas_fijas:
            inp_act, inp_ant = inputs_cuentas_fijas[cuenta.nombre]
            monto_actual = _extraer_float(inp_act)
            monto_anterior = _extraer_float(inp_ant)
            if monto_actual != 0.0 or monto_anterior != 0.0:
                movimientos.append(MovimientoESF(
                    cuenta=cuenta, monto_actual=monto_actual, monto_anterior=monto_anterior
                ))
    
    for fila in filas_capital_dinamico:
        nombre = (fila.nombre_input.value or "").strip()
        if not nombre:
            continue
        monto_actual = _extraer_float(fila.actual_input)
        monto_anterior = _extraer_float(fila.anterior_input)
        seccion = SeccionCapital(fila.seccion_select.value)
        reductora = fila.reductora_check.value or False
        if monto_actual != 0.0 or monto_anterior != 0.0:
            cuenta_din = crear_cuenta_capital_dinamica(nombre, seccion, reductora)
            movimientos.append(MovimientoESF(
                cuenta=cuenta_din, monto_actual=monto_actual, monto_anterior=monto_anterior
            ))

    for fila in filas_subcuentas_dinamicas:
        nombre = (fila.nombre_input.value or "").strip()
        if not nombre:
            continue
        monto_actual = _extraer_float(fila.actual_input)
        monto_anterior = _extraer_float(fila.anterior_input)
        clasificacion = Clasificacion(fila.clasificacion_select.value)
        nif = NIF(fila.nif_select.value)
        es_complementaria = fila.complementaria_check.value or False
        if monto_actual != 0.0 or monto_anterior != 0.0:
            cuenta_din = crear_cuenta_balance_dinamica(nombre, clasificacion, nif, es_complementaria)
            movimientos.append(MovimientoESF(
                cuenta=cuenta_din, monto_actual=monto_actual, monto_anterior=monto_anterior
            ))
    return movimientos


def _construir_movimientos_eri() -> list[MovimientoERI]:
    movimientos: list[MovimientoERI] = []
    for cuenta in CATALOGO_V3.values():
        if cuenta.clasificacion != Clasificacion.RESULTADO:
            continue
        if cuenta.nombre in inputs_cuentas_fijas:
            inp_act, _ = inputs_cuentas_fijas[cuenta.nombre]
            monto = _extraer_float(inp_act)
            if monto != 0.0:
                movimientos.append(MovimientoERI(cuenta=cuenta, monto=monto))
    return movimientos


# ==========================================
# 5. RENDERIZADO DE TABLAS Y RESULTADOS
# ==========================================
def _render_tab_esf(esf: ResultadoESF):
    with ui.column().classes("w-full gap-2"):
        banner = generar_banner_verificacion(esf)
        color = "green" if esf.cuadrado_actual else "red"
        ui.label(banner).classes(f"text-{color}-700 text-lg font-bold")
        columnas = [
            {"name": "concepto", "label": "Concepto", "field": "concepto", "align": "left"},
            {"name": "notas", "label": "Notas", "field": "notas", "align": "center"},
            {"name": "actual", "label": "Año Actual", "field": "actual", "align": "right"},
            {"name": "notas2", "label": "Notas", "field": "notas2", "align": "center"},
            {"name": "anterior", "label": "Año Anterior", "field": "anterior", "align": "right"},
        ]
        filas = []
        def _agregar_seccion(titulo: str, rubros: list, total_act: float, total_ant: float):
            filas.append({"concepto": titulo, "notas": "", "actual": "", "notas2": "", "anterior": ""})
            for r in rubros:
                filas.append({
                    "concepto": f"  {r.nif.etiqueta}",
                    "notas": "", "actual": formatear_moneda(r.saldo_actual),
                    "notas2": "", "anterior": formatear_moneda(r.saldo_anterior),
                })
            filas.append({
                "concepto": f"Total {titulo}",
                "notas": "", "actual": formatear_moneda(total_act),
                "notas2": "", "anterior": formatear_moneda(total_ant),
            })

        _agregar_seccion("Activo Circulante", esf.activo_circulante, esf.total_activo_circulante_actual, esf.total_activo_circulante_anterior)
        _agregar_seccion("Activo No Circulante", esf.activo_no_circulante, esf.total_activo_no_circulante_actual, esf.total_activo_no_circulante_anterior)
        filas.append({"concepto": "TOTAL ACTIVO", "notas": "", "actual": formatear_moneda(esf.total_activo_actual), "notas2": "", "anterior": formatear_moneda(esf.total_activo_anterior)})
        _agregar_seccion("Pasivo a Corto Plazo", esf.pasivo_corto_plazo, esf.total_pasivo_corto_plazo_actual, esf.total_pasivo_corto_plazo_anterior)
        _agregar_seccion("Pasivo a Largo Plazo", esf.pasivo_largo_plazo, esf.total_pasivo_largo_plazo_actual, esf.total_pasivo_largo_plazo_anterior)
        filas.append({"concepto": "TOTAL PASIVO", "notas": "", "actual": formatear_moneda(esf.total_pasivo_actual), "notas2": "", "anterior": formatear_moneda(esf.total_pasivo_anterior)})
        _agregar_seccion("Capital Contribuido", esf.capital_contribuido, esf.total_capital_contribuido_actual, esf.total_capital_contribuido_anterior)
        _agregar_seccion("Capital Ganado", esf.capital_ganado, esf.total_capital_ganado_actual, esf.total_capital_ganado_anterior)
        filas.append({"concepto": "TOTAL CAPITAL CONTABLE", "notas": "", "actual": formatear_moneda(esf.total_capital_contable_actual), "notas2": "", "anterior": formatear_moneda(esf.total_capital_contable_anterior)})
        filas.append({"concepto": "TOTAL PASIVO + CAPITAL", "notas": "", "actual": formatear_moneda(esf.total_pasivo_mas_capital_actual), "notas2": "", "anterior": formatear_moneda(esf.total_pasivo_mas_capital_anterior)})
        with ui.element("div").classes("w-full overflow-x-auto"):
            ui.table(columns=columnas, rows=filas, row_key="concepto").classes("w-full")


def _render_tab_eri(eri: ResultadoERI):
    with ui.column().classes("w-full gap-2"):
        columnas = [
            {"name": "concepto", "label": "Concepto", "field": "concepto", "align": "left"},
            {"name": "monto", "label": "Monto", "field": "monto", "align": "right"},
        ]
        filas = [
            {"concepto": "Ventas", "monto": formatear_moneda(eri.ventas)},
            {"concepto": "Costo de Ventas", "monto": formatear_moneda(eri.costo_ventas)},
            {"concepto": "Utilidad Bruta (3°)", "monto": formatear_moneda(eri.utilidad_bruta)},
            {"concepto": "Gastos de Venta", "monto": formatear_moneda(eri.gastos_venta)},
            {"concepto": "Gastos de Administración", "monto": formatear_moneda(eri.gastos_administracion)},
            {"concepto": "Gastos Generales (6°)", "monto": formatear_moneda(eri.gastos_generales)},
            {"concepto": "Utilidad antes de Otros (7°)", "monto": formatear_moneda(eri.utilidad_antes_otros)},
            {"concepto": "Otros Productos", "monto": formatear_moneda(eri.otros_productos)},
            {"concepto": "Otros Gastos", "monto": formatear_moneda(eri.otros_gastos)},
            {"concepto": "Neto Otros Productos/Gastos (10°)", "monto": formatear_moneda(eri.neto_otros_productos_gastos)},
            {"concepto": "Utilidad de Operación (11°)", "monto": formatear_moneda(eri.utilidad_operacion)},
            {"concepto": "Productos Financieros", "monto": formatear_moneda(eri.productos_financieros)},
            {"concepto": "Gastos Financieros", "monto": formatear_moneda(eri.gastos_financieros)},
            {"concepto": "RIF (14°)", "monto": formatear_moneda(eri.rif)},
            {"concepto": "Utilidad antes de Impuestos (15°)", "monto": formatear_moneda(eri.utilidad_antes_impuestos)},
            {"concepto": "ISR", "monto": formatear_moneda(eri.isr)},
            {"concepto": "PTU", "monto": formatear_moneda(eri.ptu)},
            {"concepto": "Impuestos a la Utilidad (18°)", "monto": formatear_moneda(eri.impuestos_utilidad)},
            {"concepto": "Utilidad Neta (19°)", "monto": formatear_moneda(eri.utilidad_neta)},
            {"concepto": "Otros Resultados Integrales (ORI)", "monto": formatear_moneda(eri.ori)},
            {"concepto": "Utilidad Integral (21°)", "monto": formatear_moneda(eri.utilidad_integral)},
        ]
        with ui.element("div").classes("w-full overflow-x-auto"):
            ui.table(columns=columnas, rows=filas, row_key="concepto").classes("w-full")


def _render_tab_flujo(indirecto: ResultadoFlujoEfectivo, directo: ResultadoFlujoEfectivo):
    with ui.column().classes("w-full gap-4"):
        for metodo, resultado in [("INDIRECTO", indirecto), ("DIRECTO", directo)]:
            ui.label(f"Método {metodo}").classes("text-lg font-bold text-red-900")
            columnas = [
                {"name": "concepto", "label": "Concepto", "field": "concepto", "align": "left"},
                {"name": "monto", "label": "Monto", "field": "monto", "align": "right"},
            ]
            filas = []
            for seccion, titulo, lista, total in [
                ("operacion", "Actividades de Operación", resultado.filas_operacion, resultado.total_operacion),
                ("inversion", "Actividades de Inversión", resultado.filas_inversion, resultado.total_inversion),
                ("financiamiento", "Actividades de Financiamiento", resultado.filas_financiamiento, resultado.total_financiamiento),
            ]:
                filas.append({"concepto": titulo, "monto": ""})
                for f in lista:
                    filas.append({"concepto": f"  {f.concepto}", "monto": formatear_moneda(f.monto)})
                filas.append({"concepto": f"Total {titulo}", "monto": formatear_moneda(total)})
            filas.append({"concepto": "Incremento de Efectivo", "monto": formatear_moneda(resultado.incremento_efectivo)})
            filas.append({"concepto": "Efectivo Inicial", "monto": formatear_moneda(resultado.efectivo_inicial)})
            filas.append({"concepto": "Efectivo Final (calculado)", "monto": formatear_moneda(resultado.efectivo_final_calculado)})
            filas.append({"concepto": "Efectivo Final (real)", "monto": formatear_moneda(resultado.efectivo_final_real)})
            color = "green" if resultado.concilia else "red"
            ui.label(f"¿Concilia? {'SÍ' if resultado.concilia else 'NO'} (diferencia: {formatear_moneda(resultado.diferencia_conciliacion)})").classes(f"text-{color}-700 font-bold")
            with ui.element("div").classes("w-full overflow-x-auto"):
                ui.table(columns=columnas, rows=filas, row_key="concepto").classes("w-full")
            ui.separator()


def _render_tab_capital(ec: EstadoCambiosCapital, esf: ResultadoESF):
    with ui.column().classes("w-full gap-2"):
        ok, diff = validar_consistencia_con_esf(ec, esf)
        color = "green" if ok else "red"
        ui.label(f"Consistencia con ESF: {'COINCIDE' if ok else f'DIFIERE (${diff:,.2f})'}").classes(f"text-{color}-700 text-lg font-bold")
        columnas = [
            {"name": "concepto", "label": "Concepto", "field": "concepto", "align": "left"},
            {"name": "notas", "label": "Notas", "field": "notas", "align": "center"},
            {"name": "contribuido", "label": "Capital Contribuido", "field": "contribuido", "align": "right"},
            {"name": "ganado", "label": "Capital Ganado", "field": "ganado", "align": "right"},
            {"name": "totales", "label": "Totales", "field": "totales", "align": "right"},
        ]
        filas = []
        for f in ec.filas:
            cc = formatear_moneda(f.capital_contribuido) if f.capital_contribuido is not None else ""
            cg = formatear_moneda(f.capital_ganado) if f.capital_ganado is not None else ""
            tt = formatear_moneda(f.totales) if f.totales is not None else ""
            concepto = f.concepto.upper() if f.es_encabezado_categoria else f.concepto
            filas.append({"concepto": concepto, "notas": f.notas or "", "contribuido": cc, "ganado": cg, "totales": tt})
        with ui.element("div").classes("w-full overflow-x-auto"):
            ui.table(columns=columnas, rows=filas, row_key="concepto").classes("w-full")


def _calcular_y_mostrar(empresa_val: str, periodo_val: str):
    global resultados_container

    if _validar_nombres_duplicados(filas_capital_dinamico, "Catálogo Complementario 1 (Capital Contable Dinámico)"):
        return
    if _validar_nombres_duplicados(filas_subcuentas_dinamicas, "Catálogo Complementario 2 (Subcuentas de Balance)"):
        return

    movimientos_esf = _construir_movimientos_esf()
    movimientos_eri = _construir_movimientos_eri()
    
    # 1. Guardar en Supabase
    practica_id = guardar_practica_supabase(empresa_val, periodo_val)
    if practica_id:
        guardar_movimientos_supabase(practica_id, movimientos_esf, movimientos_eri)

    # 2. Cálculos NIF
    resultado_eri = calcular_eri(movimientos_eri)
    resultado_esf = calcular_esf(
        movimientos_esf,
        utilidad_integral_actual=resultado_eri.utilidad_integral,
        utilidad_integral_anterior=0.0,
    )
    estado_cambios = generar_estado_cambios_capital(
        movimientos_esf, resultado_eri.utilidad_integral
    )
    flujo_indirecto = generar_flujo_indirecto(
        movimientos_esf, resultado_eri.utilidad_integral
    )
    flujo_directo = generar_flujo_directo(
        movimientos_esf, resultado_eri.utilidad_integral
    )

    if resultados_container is not None:
        resultados_container.clear()
        with resultados_container:
            ui.notify(f"Cálculo procesado. Cuentas detectadas: {len(movimientos_esf) + len(movimientos_eri)}", type="positive")
            
            def _descargar_pdf():
                pdf_bytes = generar_pdf_estados_financieros(
                    empresa=empresa_val,
                    periodo=periodo_val,
                    esf=resultado_esf,
                    eri=resultado_eri,
                    flujo_indirecto=flujo_indirecto,
                    flujo_directo=flujo_directo,
                    estado_cambios=estado_cambios
                )
                ui.download(pdf_bytes, filename="Estados_Financieros_FACPYA.pdf")

            def _descargar_excel():
                excel_bytes = generar_excel_estados_financieros(
                    esf=resultado_esf,
                    eri=resultado_eri,
                    flujo_indirecto=flujo_indirecto,
                    estado_cambios=estado_cambios,
                    empresa=empresa_val,
                    periodo=periodo_val
                )
                ui.download(excel_bytes, filename="Estados_Financieros_NIF.xlsx")

            with ui.row().classes("w-full justify-between items-center mb-4 border-b border-gray-300 pb-2"):
                ui.label("Reportes Financieros Generados").classes("text-xl font-bold text-red-900")
                with ui.row().classes("gap-2"):
                    ui.button("Exportar Excel (.xlsx)", on_click=_descargar_excel, icon="download").classes("bg-green-700 hover:bg-green-800 text-white font-bold px-4 py-2 rounded")
                    ui.button("Descargar PDF (Opcional)", on_click=_descargar_pdf).classes("bg-gray-700 hover:bg-gray-800 text-white font-bold px-4 py-2 rounded")

            tabs = ui.tabs().classes("text-red-900")
            with tabs:
                t1 = ui.tab("ESF")
                t2 = ui.tab("ERI")
                t3 = ui.tab("Flujo de Efectivo")
                t4 = ui.tab("Cambios en Capital")
            
            panels = ui.tab_panels(tabs, value=t1).classes("w-full")
            with panels:
                with ui.tab_panel(t1):
                    _render_tab_esf(resultado_esf)
                with ui.tab_panel(t2):
                    _render_tab_eri(resultado_eri)
                with ui.tab_panel(t3):
                    _render_tab_flujo(flujo_indirecto, flujo_directo)
                with ui.tab_panel(t4):
                    _render_tab_capital(estado_cambios, resultado_esf)


def _build_captura_cuentas_fijas():
    for clasif in Clasificacion:
        cuentas = listar_cuentas_por_clasificacion(clasif)
        if not cuentas:
            continue
        with ui.card().classes("w-full border-l-4 border-red-900"):
            ui.label(clasif.value).classes("text-md font-bold text-red-900")
            for cuenta in cuentas:
                with ui.row().classes("w-full items-center gap-4"):
                    ui.label(cuenta.nombre).classes("w-64 text-sm text-gray-700")
                    inp_actual = ui.number(label="Año Actual", value=0.0, format="%.2f").classes("w-40")
                    if cuenta.clasificacion != Clasificacion.RESULTADO:
                        inp_anterior = ui.number(label="Año Anterior", value=0.0, format="%.2f").classes("w-40")
                    else:
                        inp_anterior = ui.number(label="Año Anterior", value=0.0, format="%.2f").classes("w-40")
                        inp_anterior.disable()
                    inputs_cuentas_fijas[cuenta.nombre] = (inp_actual, inp_anterior)


NIF_POR_CLASIFICACION_CASCADA: dict[str, list[tuple[str, str]]] = {
    Clasificacion.ACTIVO_CIRCULANTE.value: [(n.value[0], n.value[0]) for n in NIFS_POR_CLASIFICACION[Clasificacion.ACTIVO_CIRCULANTE]],
    Clasificacion.ACTIVO_NO_CIRCULANTE.value: [(n.value[0], n.value[0]) for n in NIFS_POR_CLASIFICACION[Clasificacion.ACTIVO_NO_CIRCULANTE]],
    Clasificacion.PASIVO_CORTO_PLAZO.value: [(n.value[0], n.value[0]) for n in NIFS_POR_CLASIFICACION[Clasificacion.PASIVO_CORTO_PLAZO]],
    Clasificacion.PASIVO_LARGO_PLAZO.value: [(n.value[0], n.value[0]) for n in NIFS_POR_CLASIFICACION[Clasificacion.PASIVO_LARGO_PLAZO]],
}


def _agregar_fila_capital_dinamico():
    row_container = ui.row().classes("w-full items-center gap-2")
    with row_container:
        nombre = ui.input(label="Nombre cuenta", value="").classes("w-48")
        actual = ui.number(label="Año Actual", value=0.0, format="%.2f").classes("w-32")
        anterior = ui.number(label="Año Anterior", value=0.0, format="%.2f").classes("w-32")
        seccion = ui.select(
            label="Sección",
            options=[s.value for s in SeccionCapital],
            value=SeccionCapital.CAPITAL_CONTRIBUIDO.value,
        ).classes("w-40")
        reductora = ui.checkbox("Reductora", value=False)
        fila = CapitalDinamicaRow(nombre, actual, anterior, seccion, reductora)
        filas_capital_dinamico.append(fila)

        def _eliminar_fila(fila=fila, contenedor=row_container):
            if fila in filas_capital_dinamico:
                filas_capital_dinamico.remove(fila)
            contenedor.delete()

        ui.button(icon="delete", on_click=_eliminar_fila).props("flat round color=negative dense").classes("ml-2")


def _agregar_fila_subcuenta_dinamica():
    row_container = ui.row().classes("w-full items-center gap-2")
    with row_container:
        nombre = ui.input(label="Nombre cuenta", value="").classes("w-48")
        actual = ui.number(label="Año Actual", value=0.0, format="%.2f").classes("w-32")
        anterior = ui.number(label="Año Anterior", value=0.0, format="%.2f").classes("w-32")
        clasificacion = ui.select(
            label="Clasificación",
            options=list(NIF_POR_CLASIFICACION_CASCADA.keys()),
            value=Clasificacion.ACTIVO_CIRCULANTE.value,
        ).classes("w-44")
        nif = ui.select(
            label="NIF",
            options=[op[0] for op in NIF_POR_CLASIFICACION_CASCADA[Clasificacion.ACTIVO_CIRCULANTE.value]],
            value=NIF.EQUIVALENTES_EFECTIVO.value[0],
        ).classes("w-56")
        complementaria = ui.checkbox("Complementaria", value=False)
        
        def _actualizar_nif(event=None):
            opciones = NIF_POR_CLASIFICACION_CASCADA.get(clasificacion.value, [])
            nif.set_options([op[0] for op in opciones])
            if opciones:
                nif.set_value(opciones[0][0])
                
        clasificacion.on("update:model-value", _actualizar_nif)
        fila = SubcuentaDinamicaRow(nombre, actual, anterior, clasificacion, nif, complementaria)
        filas_subcuentas_dinamicas.append(fila)

        def _eliminar_fila(fila=fila, contenedor=row_container):
            if fila in filas_subcuentas_dinamicas:
                filas_subcuentas_dinamicas.remove(fila)
            contenedor.delete()

        ui.button(icon="delete", on_click=_eliminar_fila).props("flat round color=negative dense").classes("ml-2")


# ==========================================
# 6. PÁGINA PRINCIPAL
# ==========================================
@ui.page("/")
def pagina_principal():
    global resultados_container
    
    # Encabezado principal FACPYA
    with ui.row().classes("w-full bg-red-900 text-white p-4 rounded mb-6 items-center justify-between shadow-md"):
        ui.label("SuiteContable NIF V3 — FACPYA").classes("text-2xl font-bold")
        ui.label("Autoevaluación Financiera").classes("text-md opacity-80")
    
    with ui.card().classes("w-full mb-4 border-l-4 border-gray-600"):
        ui.label("Datos Generales").classes("text-lg font-bold text-gray-800")
        with ui.row().classes("gap-4"):
            input_empresa = ui.input(label="Nombre de la empresa", value="Empresa Demo S.A.").classes("w-64")
            ui.input(label="Tipo de sociedad", value="S.A. de C.V.").classes("w-40")
        with ui.row().classes("gap-4"):
            input_periodo = ui.input(label="Periodo actual", value="Del 1 de enero al 31 de diciembre de 2025").classes("w-80")
            ui.input(label="Periodo anterior", value="Al 31 de diciembre de 2024").classes("w-80")

    with ui.card().classes("w-full mb-4 border-l-4 border-gray-600"):
        ui.label("Catálogo de Cuentas Fijo (CATALOGO_V3)").classes("text-lg font-bold text-gray-800")
        _build_captura_cuentas_fijas()

    with ui.card().classes("w-full mb-4 border-l-4 border-gray-600"):
        ui.label("Catálogo Complementario 2: Otras Subcuentas de Balance").classes("text-lg font-bold text-gray-800")
        ui.label("Agrega cuentas adicionales de Activo/Pasivo con su NIF correspondiente.").classes("text-sm text-gray-500")
        container_subcuentas = ui.column().classes("w-full")
        with container_subcuentas:
            _agregar_fila_subcuenta_dinamica()
        ui.button("+ Agregar subcuenta de balance", on_click=_agregar_fila_subcuenta_dinamica).classes("bg-gray-700 text-white")

    with ui.card().classes("w-full mb-4 border-l-4 border-gray-600"):
        ui.label("Catálogo Complementario 1: Capital Contable Dinámico").classes("text-lg font-bold text-gray-800")
        ui.label("Agrega cuentas adicionales de Capital Contable.").classes("text-sm text-gray-500")
        container_capital = ui.column().classes("w-full")
        with container_capital:
            _agregar_fila_capital_dinamico()
        ui.button("+ Agregar cuenta de capital", on_click=_agregar_fila_capital_dinamico).classes("bg-gray-700 text-white")

    # Botón principal en Rojo Guinda
    ui.button(
        "Calcular Estados Financieros",
        on_click=lambda: _calcular_y_mostrar(input_empresa.value, input_periodo.value)
    ).classes("text-lg bg-red-900 hover:bg-red-800 text-white font-bold my-6 w-full py-3 shadow-lg")

    resultados_container = ui.column().classes("w-full")


if __name__ in {"__main__", "__mp_main__"}:
    port = int(os.environ.get("PORT", 8080))
    ui.run(title="Autoevaluación Financiera NIF V3 - FACPYA", host="0.0.0.0", port=port, reload=False)
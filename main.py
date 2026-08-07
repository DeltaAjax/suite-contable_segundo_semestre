"""
main.py — Interfaz Unificada (NiceGUI) con persistencia y exportación
Herramienta de Autoevaluación Financiera (FACPYA — UANL)
Hito 4: Integración de Auditoría NIF C-6 (Depreciación) y C-19 (Amortización)
"""

from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from nicegui import ui
from supabase import create_client, Client

# Módulos internos
from catalog import (
    CATALOGO_UNIFICADO,
    CATEGORIAS_ESF_DISPONIBLES,
    COMPORTAMIENTOS_DISPONIBLES,
    Clasificacion,
    Cuenta,
    LineaERI,
    NIF,
    NIFS_POR_CLASIFICACION,
    SeccionCapital,
    TipoEstado,
    crear_cuenta_balance_dinamica,
    crear_cuenta_capital_dinamica,
    crear_cuenta_personalizada,
    listar_cuentas_por_clasificacion,
    listar_cuentas_por_grupo,
    nif_por_etiqueta,
    obtener_cuenta_por_linea_eri,
)
from engine import (
    MovimientoCuenta,
    MovimientoERI,
    MovimientoESF,
    ResultadoERI,
    ResultadoESF,
    calcular_eri,
    calcular_esf,
    formatear_moneda,
    generar_banner_verificacion,
)
from flujo_efectivo import (
    generar_flujo_indirecto,
    generar_flujo_directo,
    ResultadoFlujoEfectivo,
)
from capital_contable import (
    generar_estado_cambios_capital,
    validar_consistencia_con_esf,
    EstadoCambiosCapital,
)
from pdf_exporter import generar_pdf_estados_financieros
from excel_exporter import generar_excel_estados_financieros

# ===== IMPORTS PARA AUDITORÍA NIF (Hito 4) =====
from depreciacion import (
    calcular_linea_recta,
    calcular_suma_digitos,
    calcular_unidades_produccion,
    calcular_saldos_decrecientes,
    exportar_depreciacion_excel,
    TablaDepreciacion
)
from amortizacion import (
    calcular_amortizacion_capital_fijo,
    calcular_amortizacion_vencimiento,
    exportar_amortizacion_excel,
    TablaAmortizacion
)

# ---------------------------------------------------------------------------
# Identidad institucional
# ---------------------------------------------------------------------------
COLOR_GUINDA = "#800000"
COLOR_GUINDA_OSCURO = "#600000"
COLOR_DORADO = "#F2A900"

MODO_SIMPLE = "1er Semestre — Modo Simplificado"
MODO_AVANZADO = "NIF V3 — Suite Profesional"

# ---------------------------------------------------------------------------
# Constantes compartidas
# ---------------------------------------------------------------------------
LINEAS_CAPTURA_ERI: list[LineaERI] = [
    LineaERI.VENTAS,
    LineaERI.COSTO_VENTAS,
    LineaERI.GASTOS_VENTA,
    LineaERI.GASTOS_ADMINISTRACION,
    LineaERI.OTROS_PRODUCTOS,
    LineaERI.OTROS_GASTOS,
    LineaERI.PRODUCTOS_FINANCIEROS,
    LineaERI.GASTOS_FINANCIEROS,
    LineaERI.ISR,
    LineaERI.PTU,
    LineaERI.ORI,
]

GRUPOS_ESF_ORDEN: list[str] = CATEGORIAS_ESF_DISPONIBLES

def grupo_de_cuenta(cuenta: Cuenta) -> str:
    if cuenta.tipo == TipoEstado.ERI:
        return cuenta.linea_eri.value  # type: ignore
    if cuenta.clasificacion == Clasificacion.CAPITAL_CONTABLE:
        if cuenta.seccion_capital == SeccionCapital.CAPITAL_CONTRIBUIDO:
            return "Capital Contribuido"
        return "Capital Ganado"
    return cuenta.clasificacion.value

def listar_cuentas_simplificadas(grupo_valor: str) -> list[Cuenta]:
    return [c for c in listar_cuentas_por_grupo(grupo_valor) if c.es_simplificada]


# ---------------------------------------------------------------------------
# Estructuras auxiliares – filas dinámicas (modo avanzado)
# ---------------------------------------------------------------------------
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

NIF_POR_CLASIFICACION_CASCADA: dict[str, list[str]] = {
    Clasificacion.ACTIVO_CIRCULANTE.value: [n.etiqueta for n in NIFS_POR_CLASIFICACION[Clasificacion.ACTIVO_CIRCULANTE]],
    Clasificacion.ACTIVO_NO_CIRCULANTE.value: [n.etiqueta for n in NIFS_POR_CLASIFICACION[Clasificacion.ACTIVO_NO_CIRCULANTE]],
    Clasificacion.PASIVO_CORTO_PLAZO.value: [n.etiqueta for n in NIFS_POR_CLASIFICACION[Clasificacion.PASIVO_CORTO_PLAZO]],
    Clasificacion.PASIVO_LARGO_PLAZO.value: [n.etiqueta for n in NIFS_POR_CLASIFICACION[Clasificacion.PASIVO_LARGO_PLAZO]],
}

# ---------------------------------------------------------------------------
# Estado de Sesión Unificado
# ---------------------------------------------------------------------------
class EstadoSesion:
    def __init__(self) -> None:
        self.modo: str = MODO_SIMPLE

        # Modo simplificado (1er semestre)
        self.campos_eri: dict[str, ui.number] = {}
        self.subtotales_eri: dict[str, ui.number] = {}
        self.campos_esf_predeterminados: dict[str, ui.number] = {}
        self.cuentas_personalizadas: list[Cuenta] = []
        self.campos_esf_personalizados: dict[str, ui.number] = {}
        self.contenedor_personalizadas: ui.column | None = None
        self.campo_utilidad_perdida: ui.number | None = None
        self.utilidad_perdida_editada_manualmente = False
        self.contenedor_informe_eri: ui.column | None = None
        self.contenedor_informe_esf: ui.row | None = None
        self.banner_simple: ui.label | None = None

        # Modo avanzado (NIF V3)
        self.inputs_cuentas_fijas: dict[str, tuple[ui.number, ui.number]] = {}
        self.filas_capital_dinamico: list[CapitalDinamicaRow] = []
        self.filas_subcuentas_dinamicas: list[SubcuentaDinamicaRow] = []
        self.resultados_container: ui.column | None = None
        self.container_capital_ref: ui.column | None = None
        self.container_subcuentas_ref: ui.column | None = None
        self.input_empresa_ref: ui.input | None = None
        self.input_periodo_ref: ui.input | None = None
        self.input_elaboro_ref: ui.input | None = None
        self.input_catedratico_ref: ui.input | None = None

        # Almacenamiento de resultados calculados
        self.ultimo_esf: ResultadoESF | None = None
        self.ultimo_eri: ResultadoERI | None = None
        self.ultimo_flujo_indirecto: ResultadoFlujoEfectivo | None = None
        self.ultimo_flujo_directo: ResultadoFlujoEfectivo | None = None
        self.ultimo_estado_cambios: EstadoCambiosCapital | None = None
        self.ultima_empresa: str = ""
        self.ultimo_periodo: str = ""
        self.ultimo_elaboro: str = ""
        self.ultimo_catedratico: str = ""

        # Persistencia
        self.select_practicas: ui.select | None = None
        self.practica_id_actual: int | None = None
        self.practica_nombre_input: ui.input | None = None

    def construir_movimientos_eri_simple(self) -> list[MovimientoCuenta]:
        movimientos = []
        for linea in LINEAS_CAPTURA_ERI:
            campo = self.campos_eri.get(linea.value)
            if campo is None:
                continue
            monto = campo.value or 0
            if monto:
                cuenta = obtener_cuenta_por_linea_eri(linea)
                if cuenta is None:
                    ui.notify(f"No se encontró cuenta para '{linea.value}'.", type="negative")
                    continue
                movimientos.append(MovimientoCuenta(cuenta=cuenta, monto=monto))
        return movimientos

    def construir_movimientos_esf_simple(self) -> list[MovimientoCuenta]:
        movimientos = []
        for grupo in GRUPOS_ESF_ORDEN:
            for cuenta in listar_cuentas_simplificadas(grupo):
                campo = self.campos_esf_predeterminados.get(cuenta.nombre)
                if campo is None:
                    continue
                monto = campo.value or 0
                if monto:
                    movimientos.append(MovimientoCuenta(cuenta=cuenta, monto=monto))
        for cuenta in self.cuentas_personalizadas:
            campo = self.campos_esf_personalizados.get(cuenta.nombre)
            if campo is None:
                continue
            monto = campo.value or 0
            if monto:
                movimientos.append(MovimientoCuenta(cuenta=cuenta, monto=monto))
        return movimientos

    def recalcular_eri_simple(self) -> None:
        movimientos = self.construir_movimientos_eri_simple()
        r = calcular_eri(movimientos)
        self.subtotales_eri["Utilidad/Pérdida Bruta (3°)"].value = r.utilidad_bruta
        self.subtotales_eri["Gastos Generales (6°)"].value = r.gastos_generales
        self.subtotales_eri["Utilidad/Pérdida Antes de Otros Prod. y Gastos (7°)"].value = r.utilidad_antes_otros
        self.subtotales_eri["Neto Otros Productos y Gastos (10°)"].value = r.neto_otros_productos_gastos
        self.subtotales_eri["Utilidad/Pérdida en Operación (11°)"].value = r.utilidad_operacion
        self.subtotales_eri["Resultado Integral de Financiamiento (14°)"].value = r.rif
        self.subtotales_eri["Utilidad/Pérdida Antes de Impuestos (15°)"].value = r.utilidad_antes_impuestos
        self.subtotales_eri["Impuestos a la Utilidad (18°)"].value = r.impuestos_utilidad
        self.subtotales_eri["Utilidad/Pérdida Neta (19°)"].value = r.utilidad_neta
        self.subtotales_eri["Utilidad/Pérdida Integral (21°)"].value = r.utilidad_integral

        if self.campo_utilidad_perdida is not None and not self.utilidad_perdida_editada_manualmente:
            self.campo_utilidad_perdida.value = r.utilidad_integral
        self.recalcular_informe_simple()

    def recalcular_informe_simple(self) -> None:
        if self.contenedor_informe_eri is None:
            return
        movimientos_eri = self.construir_movimientos_eri_simple()
        movimientos_esf = self.construir_movimientos_esf_simple()
        r_eri = calcular_eri(movimientos_eri)
        utilidad_perdida = (self.campo_utilidad_perdida.value or 0) if self.campo_utilidad_perdida else 0
        r_esf = calcular_esf(movimientos_esf, resultado_del_ejercicio=utilidad_perdida)
        self._pintar_informe_eri_simple(r_eri)
        self._pintar_informe_esf_simple(movimientos_esf, r_esf, utilidad_perdida)
        self._pintar_banner_simple(r_esf)

    def _pintar_informe_eri_simple(self, r: ResultadoERI) -> None:
        self.contenedor_informe_eri.clear()
        filas = [
            ("Ventas", r.ventas),
            ("Costo de Ventas", r.costo_ventas),
            ("= Utilidad / Pérdida Bruta (3°)", r.utilidad_bruta),
            ("Gastos de Venta", r.gastos_venta),
            ("Gastos de Administración", r.gastos_administracion),
            ("= Gastos Generales (6°)", r.gastos_generales),
            ("= Utilidad/Pérdida Antes de Otros Prod. y Gastos (7°)", r.utilidad_antes_otros),
            ("Otros Productos", r.otros_productos),
            ("Otros Gastos", r.otros_gastos),
            ("= Neto Otros Productos y Gastos (10°)", r.neto_otros_productos_gastos),
            ("= Utilidad/Pérdida en Operación (11°)", r.utilidad_operacion),
            ("Productos Financieros", r.productos_financieros),
            ("Gastos Financieros", r.gastos_financieros),
            ("= Resultado Integral de Financiamiento (14°)", r.rif),
            ("= Utilidad/Pérdida Antes de Impuestos (15°)", r.utilidad_antes_impuestos),
            ("ISR", r.isr),
            ("PTU", r.ptu),
            ("= Impuestos a la Utilidad (18°)", r.impuestos_utilidad),
            ("= Utilidad/Pérdida Neta (19°)", r.utilidad_neta),
            ("Otros Resultados Integrales (ORI)", r.ori),
            ("= Utilidad/Pérdida Integral (21°)", r.utilidad_integral),
        ]
        subtotal_labels = {
            "= Utilidad / Pérdida Bruta (3°)", "= Gastos Generales (6°)",
            "= Utilidad/Pérdida Antes de Otros Prod. y Gastos (7°)",
            "= Neto Otros Productos y Gastos (10°)", "= Utilidad/Pérdida en Operación (11°)",
            "= Resultado Integral de Financiamiento (14°)",
            "= Utilidad/Pérdida Antes de Impuestos (15°)", "= Impuestos a la Utilidad (18°)",
            "= Utilidad/Pérdida Neta (19°)", "= Utilidad/Pérdida Integral (21°)",
        }
        with self.contenedor_informe_eri:
            ui.label("Estado de Resultado Integral (ERI)").classes(f"text-lg font-bold text-[{COLOR_GUINDA}]")
            for etiqueta, monto in filas:
                clases = "text-sm"
                if etiqueta in subtotal_labels:
                    clases = "text-sm font-bold border-t pt-1"
                with ui.row().classes(f"w-full justify-between {clases}"):
                    ui.label(etiqueta)
                    ui.label(formatear_moneda(monto))

    def _pintar_informe_esf_simple(self, movimientos_esf, r, utilidad_perdida) -> None:
        self.contenedor_informe_esf.clear()
        def columna_grupos(grupos: list[str], titulo_total: str, total: float) -> None:
            for grupo in grupos:
                ui.label(grupo).classes("font-semibold mt-2")
                movs_grupo = [m for m in movimientos_esf if grupo_de_cuenta(m.cuenta) == grupo]
                if not movs_grupo:
                    ui.label("— (sin movimientos) —").classes("text-xs text-gray-400 italic")
                for m in movs_grupo:
                    with ui.row().classes("w-full justify-between text-sm pl-2"):
                        ui.label(m.cuenta.nombre)
                        ui.label(formatear_moneda(m.monto))
                subtotal = round(sum(m.monto_con_signo for m in movs_grupo), 2)
                with ui.row().classes("w-full justify-between text-sm font-bold border-t"):
                    ui.label(f"Total {grupo}")
                    ui.label(formatear_moneda(subtotal))
            with ui.row().classes("w-full justify-between text-base font-bold border-t-2 mt-2"):
                ui.label(titulo_total)
                ui.label(formatear_moneda(total))

        with self.contenedor_informe_esf:
            with ui.column().classes("w-1/2 gap-1"):
                ui.label("ACTIVO").classes(f"text-lg font-bold text-[{COLOR_GUINDA}]")
                columna_grupos(["Activo Circulante", "Activo No Circulante"], "TOTAL DE ACTIVO", r.total_activo)
            with ui.column().classes("w-1/2 gap-1"):
                ui.label("PASIVO Y CAPITAL CONTABLE").classes(f"text-lg font-bold text-[{COLOR_GUINDA}]")
                columna_grupos(["Pasivo a Corto Plazo", "Pasivo a Largo Plazo"], "Total de Pasivo", r.total_pasivo)
                ui.label("CAPITAL CONTABLE").classes("font-semibold mt-2")
                columna_grupos(["Capital Contribuido", "Capital Ganado"], "Total de Capital Contable", r.total_capital_contable)
                with ui.row().classes("w-full justify-between text-xs italic pl-2"):
                    ui.label("(incluye Utilidad/Pérdida del Ejercicio)")
                    ui.label(formatear_moneda(utilidad_perdida))
                with ui.row().classes("w-full justify-between text-base font-bold border-t-2 mt-2"):
                    ui.label("TOTAL PASIVO + CAPITAL")
                    ui.label(formatear_moneda(r.total_pasivo_mas_capital))

    def _pintar_banner_simple(self, r) -> None:
        texto = generar_banner_verificacion(r)
        self.banner_simple.text = texto
        self.banner_simple.classes(
            remove="bg-green-100 text-green-800 bg-red-100 text-red-800",
            add="bg-green-100 text-green-800" if r.cuadrado else "bg-red-100 text-red-800",
        )


# ---------------------------------------------------------------------------
# Cliente Supabase y funciones de persistencia
# ---------------------------------------------------------------------------
_supabase_client: Client | None = None

def _get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            ui.notify("Faltan variables de entorno SUPABASE_URL y SUPABASE_KEY", type="negative")
            raise RuntimeError("Faltan variables de entorno para Supabase")
        _supabase_client = create_client(url, key)
    return _supabase_client

def _serializar_cuenta(cuenta: Cuenta) -> dict:
    return {
        "nombre": cuenta.nombre,
        "clasificacion": cuenta.clasificacion.value,
        "nif_etiqueta": cuenta.nif.etiqueta if cuenta.nif else None,
        "es_complementaria": cuenta.es_complementaria,
        "seccion_capital": cuenta.seccion_capital.value if cuenta.seccion_capital else None,
        "signo": cuenta.signo,
        "tipo": cuenta.tipo.value,
        "linea_eri": cuenta.linea_eri.value if cuenta.linea_eri else None,
    }

def _deserializar_cuenta(data: dict) -> Cuenta:
    nombre = data["nombre"]
    cuenta = CATALOGO_UNIFICADO.get(nombre)
    if cuenta is not None:
        return cuenta

    clasificacion = Clasificacion(data["clasificacion"])
    if data["tipo"] == "ESF":
        if clasificacion == Clasificacion.CAPITAL_CONTABLE:
            seccion = SeccionCapital(data["seccion_capital"])
            reductora = data["signo"] == -1
            return crear_cuenta_capital_dinamica(nombre, seccion, reductora)
        else:
            nif = nif_por_etiqueta(data["nif_etiqueta"])
            if nif is None:
                raise ValueError(f"NIF no encontrado para {data['nif_etiqueta']}")
            es_comp = data["es_complementaria"]
            return crear_cuenta_balance_dinamica(nombre, clasificacion, nif, es_comp)
    else:
        linea = LineaERI(data["linea_eri"])
        cuenta_eri = obtener_cuenta_por_linea_eri(linea)
        if cuenta_eri is None:
            raise ValueError(f"No se encontró cuenta ERI para línea {linea}")
        return cuenta_eri

def guardar_practica_supabase(estado: EstadoSesion, nombre: str) -> None:
    """Guarda la práctica actual en Supabase con payload limpio."""
    try:
        supabase = _get_supabase()
        movs_esf = _construir_movimientos_esf_avanzado(estado)
        movs_eri = _construir_movimientos_eri_avanzado(estado)

        empresa = estado.input_empresa_ref.value if estado.input_empresa_ref else ""
        periodo = estado.input_periodo_ref.value if estado.input_periodo_ref else ""

        # FIX: Se eliminan elaboro y catedratico para evitar el error PGRST204 de Supabase
        data_practica = {
            "nombre": nombre,
            "empresa": empresa,
            "periodo": periodo,
        }
        result = supabase.table("practicas").insert(data_practica).execute()
        practica_id = result.data[0]["id"]

        for m in movs_esf:
            cuenta_meta = _serializar_cuenta(m.cuenta)
            row = {
                "practica_id": practica_id,
                "concepto": m.cuenta.nombre,
                "cuenta": m.cuenta.nombre,
                "monto": m.monto_actual,
                "tipo": "ESF",
                "nif_clasificacion": m.cuenta.nif.codigo if m.cuenta.nif else None,
                "metadata": cuenta_meta,
                "monto_anterior": m.monto_anterior,
            }
            supabase.table("movimientos_financieros").insert(row).execute()

        for m in movs_eri:
            cuenta_meta = _serializar_cuenta(m.cuenta)
            row = {
                "practica_id": practica_id,
                "concepto": m.cuenta.nombre,
                "cuenta": m.cuenta.nombre,
                "monto": m.monto,
                "tipo": "ERI",
                "nif_clasificacion": None,
                "metadata": cuenta_meta,
                "monto_anterior": 0.0,
            }
            supabase.table("movimientos_financieros").insert(row).execute()

        estado.practica_id_actual = practica_id
        ui.notify(f"Práctica '{nombre}' guardada con ID {practica_id}", type="positive")
        _refrescar_lista_practicas(estado)
    except Exception as e:
        ui.notify(f"Error al guardar: {str(e)}", type="negative")

def listar_practicas_supabase() -> list[dict]:
    try:
        supabase = _get_supabase()
        result = supabase.table("practicas").select("*").order("creado_en", desc=True).execute()
        return result.data
    except Exception as e:
        ui.notify(f"Error al listar prácticas: {str(e)}", type="negative")
        return []

def cargar_practica_supabase(estado: EstadoSesion, practica_id: int) -> None:
    try:
        supabase = _get_supabase()
        result_p = supabase.table("practicas").select("*").eq("id", practica_id).execute()
        if not result_p.data:
            ui.notify("Práctica no encontrada", type="negative")
            return
        practica = result_p.data[0]

        if estado.input_empresa_ref:
            estado.input_empresa_ref.value = practica.get("empresa", "")
        if estado.input_periodo_ref:
            estado.input_periodo_ref.value = practica.get("periodo", "")

        result_m = supabase.table("movimientos_financieros").select("*").eq("practica_id", practica_id).execute()
        movimientos = result_m.data

        _reiniciar_formulario_avanzado(estado, mantener_datos_generales=True)

        for m in movimientos:
            tipo = m["tipo"]
            metadata = m.get("metadata") or {}
            cuenta = _deserializar_cuenta(metadata)
            if tipo == "ERI":
                for linea in LINEAS_CAPTURA_ERI:
                    if cuenta.linea_eri == linea:
                        campo = estado.campos_eri.get(linea.value)
                        if campo:
                            campo.value = m["monto"]
                        break
            else:
                if cuenta.nombre in estado.inputs_cuentas_fijas:
                    inp_act, inp_ant = estado.inputs_cuentas_fijas[cuenta.nombre]
                    inp_act.value = m["monto"]
                    inp_ant.value = m.get("monto_anterior", 0.0)
                else:
                    if cuenta.clasificacion == Clasificacion.CAPITAL_CONTABLE:
                        seccion = cuenta.seccion_capital or SeccionCapital.CAPITAL_CONTRIBUIDO
                        reductora = cuenta.signo == -1
                        _agregar_fila_capital_dinamico(estado, nombre=cuenta.nombre,
                                                       actual=m["monto"], anterior=m.get("monto_anterior", 0.0),
                                                       seccion=seccion, reductora=reductora)
                    else:
                        nif = cuenta.nif
                        clasif = cuenta.clasificacion
                        comp = cuenta.es_complementaria
                        _agregar_fila_subcuenta_dinamica(estado, nombre=cuenta.nombre,
                                                         actual=m["monto"], anterior=m.get("monto_anterior", 0.0),
                                                         clasificacion=clasif, nif=nif, complementaria=comp)

        estado.practica_id_actual = practica_id
        ui.notify(f"Práctica '{practica['nombre']}' cargada", type="positive")
    except Exception as e:
        ui.notify(f"Error al cargar: {str(e)}", type="negative")

def eliminar_practica_supabase(estado: EstadoSesion, practica_id: int) -> None:
    try:
        supabase = _get_supabase()
        supabase.table("movimientos_financieros").delete().eq("practica_id", practica_id).execute()
        supabase.table("practicas").delete().eq("id", practica_id).execute()
        ui.notify("Práctica eliminada", type="positive")
        if estado.practica_id_actual == practica_id:
            estado.practica_id_actual = None
        _refrescar_lista_practicas(estado)
    except Exception as e:
        ui.notify(f"Error al eliminar: {str(e)}", type="negative")

def _refrescar_lista_practicas(estado: EstadoSesion) -> None:
    if estado.select_practicas is None:
        return
    practicas = listar_practicas_supabase()
    options = {f"{p['id']}: {p['nombre']}": p['id'] for p in practicas}
    estado.select_practicas.set_options(options)
    if options:
        estado.select_practicas.set_value(next(iter(options.values())))


# ---------------------------------------------------------------------------
# Funciones de construcción de movimientos (modo avanzado)
# ---------------------------------------------------------------------------
def _extraer_float(elem) -> float:
    try:
        if elem is None:
            return 0.0
        val = elem.value if hasattr(elem, "value") else elem
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

def _construir_movimientos_esf_avanzado(estado: EstadoSesion) -> list[MovimientoESF]:
    movimientos: list[MovimientoESF] = []
    for cuenta in CATALOGO_UNIFICADO.values():
        if cuenta.clasificacion == Clasificacion.RESULTADO:
            continue
        if cuenta.nombre in estado.inputs_cuentas_fijas:
            inp_act, inp_ant = estado.inputs_cuentas_fijas[cuenta.nombre]
            monto_actual = _extraer_float(inp_act)
            monto_anterior = _extraer_float(inp_ant)
            if monto_actual != 0.0 or monto_anterior != 0.0:
                movimientos.append(MovimientoESF(cuenta=cuenta, monto_actual=monto_actual, monto_anterior=monto_anterior))

    for fila in estado.filas_capital_dinamico:
        nombre = (fila.nombre_input.value or "").strip()
        if not nombre:
            continue
        monto_actual = _extraer_float(fila.actual_input)
        monto_anterior = _extraer_float(fila.anterior_input)
        seccion = SeccionCapital(fila.seccion_select.value)
        reductora = fila.reductora_check.value or False
        if monto_actual != 0.0 or monto_anterior != 0.0:
            cuenta_din = crear_cuenta_capital_dinamica(nombre, seccion, reductora)
            movimientos.append(MovimientoESF(cuenta=cuenta_din, monto_actual=monto_actual, monto_anterior=monto_anterior))

    for fila in estado.filas_subcuentas_dinamicas:
        nombre = (fila.nombre_input.value or "").strip()
        if not nombre:
            continue
        monto_actual = _extraer_float(fila.actual_input)
        monto_anterior = _extraer_float(fila.anterior_input)
        clasificacion = Clasificacion(fila.clasificacion_select.value)
        nif = nif_por_etiqueta(fila.nif_select.value)
        if nif is None:
            ui.notify(f"No se pudo determinar el NIF para '{nombre}'.", type="negative")
            continue
        es_complementaria = fila.complementaria_check.value or False
        if monto_actual != 0.0 or monto_anterior != 0.0:
            cuenta_din = crear_cuenta_balance_dinamica(nombre, clasificacion, nif, es_complementaria)
            movimientos.append(MovimientoESF(cuenta=cuenta_din, monto_actual=monto_actual, monto_anterior=monto_anterior))
    return movimientos

def _construir_movimientos_eri_avanzado(estado: EstadoSesion) -> list[MovimientoERI]:
    movimientos: list[MovimientoERI] = []
    for cuenta in CATALOGO_UNIFICADO.values():
        if cuenta.clasificacion != Clasificacion.RESULTADO:
            continue
        if cuenta.nombre in estado.inputs_cuentas_fijas:
            inp_act, _ = estado.inputs_cuentas_fijas[cuenta.nombre]
            monto = _extraer_float(inp_act)
            if monto != 0.0:
                movimientos.append(MovimientoERI(cuenta=cuenta, monto=monto))
    return movimientos

def _reiniciar_formulario_avanzado(estado: EstadoSesion, mantener_datos_generales: bool = False) -> None:
    for inp_act, inp_ant in estado.inputs_cuentas_fijas.values():
        inp_act.set_value(0.0)
        inp_ant.set_value(0.0)

    estado.filas_capital_dinamico.clear()
    if estado.container_capital_ref is not None:
        estado.container_capital_ref.clear()
        with estado.container_capital_ref:
            _agregar_fila_capital_dinamico(estado)

    estado.filas_subcuentas_dinamicas.clear()
    if estado.container_subcuentas_ref is not None:
        estado.container_subcuentas_ref.clear()
        with estado.container_subcuentas_ref:
            _agregar_fila_subcuenta_dinamica(estado)

    if not mantener_datos_generales:
        if estado.input_empresa_ref is not None:
            estado.input_empresa_ref.set_value("")
        if estado.input_periodo_ref is not None:
            estado.input_periodo_ref.set_value("")
        if estado.input_elaboro_ref is not None:
            estado.input_elaboro_ref.set_value("")
        if estado.input_catedratico_ref is not None:
            estado.input_catedratico_ref.set_value("")

    if estado.resultados_container is not None:
        estado.resultados_container.clear()

def _agregar_fila_capital_dinamico(estado: EstadoSesion, *, nombre: str = "", actual: float = 0.0,
                                   anterior: float = 0.0, seccion: SeccionCapital = SeccionCapital.CAPITAL_CONTRIBUIDO,
                                   reductora: bool = False) -> None:
    row_container = ui.row().classes("w-full items-center gap-2")
    with row_container:
        inp_nombre = ui.input(label="Nombre cuenta", value=nombre).classes("w-48")
        inp_actual = ui.number(label="Año Actual", value=actual, format="%.2f").classes("w-32")
        inp_anterior = ui.number(label="Año Anterior", value=anterior, format="%.2f").classes("w-32")
        sel_seccion = ui.select(
            label="Sección",
            options=[s.value for s in SeccionCapital],
            value=seccion.value,
        ).classes("w-40")
        chk_reductora = ui.checkbox("Reductora", value=reductora)
        fila = CapitalDinamicaRow(inp_nombre, inp_actual, inp_anterior, sel_seccion, chk_reductora)
        estado.filas_capital_dinamico.append(fila)

        def _eliminar_fila(fila=fila, contenedor=row_container) -> None:
            if fila in estado.filas_capital_dinamico:
                estado.filas_capital_dinamico.remove(fila)
            contenedor.delete()

        ui.button(icon="delete", on_click=_eliminar_fila).props("flat round color=negative dense").classes("ml-2")

def _agregar_fila_subcuenta_dinamica(estado: EstadoSesion, *, nombre: str = "", actual: float = 0.0,
                                     anterior: float = 0.0,
                                     clasificacion: Clasificacion = Clasificacion.ACTIVO_CIRCULANTE,
                                     nif: Optional[NIF] = None,
                                     complementaria: bool = False) -> None:
    if nif is None:
        nif = NIF.EQUIVALENTES_EFECTIVO
    row_container = ui.row().classes("w-full items-center gap-2")
    with row_container:
        inp_nombre = ui.input(label="Nombre cuenta", value=nombre).classes("w-48")
        inp_actual = ui.number(label="Año Actual", value=actual, format="%.2f").classes("w-32")
        inp_anterior = ui.number(label="Año Anterior", value=anterior, format="%.2f").classes("w-32")
        sel_clasificacion = ui.select(
            label="Clasificación",
            options=list(NIF_POR_CLASIFICACION_CASCADA.keys()),
            value=clasificacion.value,
        ).classes("w-44")
        opciones_nif = NIF_POR_CLASIFICACION_CASCADA.get(clasificacion.value, [])
        sel_nif = ui.select(
            label="NIF",
            options=opciones_nif,
            value=nif.etiqueta if nif and nif.etiqueta in opciones_nif else (opciones_nif[0] if opciones_nif else ""),
        ).classes("w-56")
        chk_complementaria = ui.checkbox("Complementaria", value=complementaria)

        def _actualizar_nif(event=None) -> None:
            opciones = NIF_POR_CLASIFICACION_CASCADA.get(sel_clasificacion.value, [])
            sel_nif.set_options(list(opciones))
            if opciones:
                sel_nif.set_value(opciones[0])

        sel_clasificacion.on("update:model-value", _actualizar_nif)
        fila = SubcuentaDinamicaRow(inp_nombre, inp_actual, inp_anterior, sel_clasificacion, sel_nif, chk_complementaria)
        estado.filas_subcuentas_dinamicas.append(fila)

        def _eliminar_fila(fila=fila, contenedor=row_container) -> None:
            if fila in estado.filas_subcuentas_dinamicas:
                estado.filas_subcuentas_dinamicas.remove(fila)
            contenedor.delete()

        ui.button(icon="delete", on_click=_eliminar_fila).props("flat round color=negative dense").classes("ml-2")


# ---------------------------------------------------------------------------
# Renderizado de pestañas en modo avanzado
# ---------------------------------------------------------------------------
def _render_tab_esf_avanzado(esf: ResultadoESF) -> None:
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

        def _agregar_seccion(titulo: str, rubros: list, total_act: float, total_ant: float) -> None:
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

def _render_tab_eri_avanzado(eri: ResultadoERI) -> None:
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

def _render_tab_flujo(flujo_indirecto: ResultadoFlujoEfectivo, flujo_directo: ResultadoFlujoEfectivo) -> None:
    def _tabla_flujo(resultado: ResultadoFlujoEfectivo, titulo: str) -> None:
        ui.label(titulo).classes(f"text-lg font-bold text-[{COLOR_GUINDA}] mt-2")
        columnas = [{"name": "concepto", "label": "Concepto", "field": "concepto", "align": "left"},
                    {"name": "monto", "label": "Monto", "field": "monto", "align": "right"}]
        filas = []
        filas.append({"concepto": "Actividades de Operación", "monto": ""})
        for f in resultado.filas_operacion:
            filas.append({"concepto": f"  {f.concepto}", "monto": formatear_moneda(f.monto)})
        filas.append({"concepto": "Total Operación", "monto": formatear_moneda(resultado.total_operacion)})

        filas.append({"concepto": "Actividades de Inversión", "monto": ""})
        for f in resultado.filas_inversion:
            filas.append({"concepto": f"  {f.concepto}", "monto": formatear_moneda(f.monto)})
        filas.append({"concepto": "Total Inversión", "monto": formatear_moneda(resultado.total_inversion)})

        filas.append({"concepto": "Actividades de Financiamiento", "monto": ""})
        for f in resultado.filas_financiamiento:
            filas.append({"concepto": f"  {f.concepto}", "monto": formatear_moneda(f.monto)})
        filas.append({"concepto": "Total Financiamiento", "monto": formatear_moneda(resultado.total_financiamiento)})

        filas.append({"concepto": "Incremento de Efectivo", "monto": formatear_moneda(resultado.incremento_efectivo)})
        filas.append({"concepto": "Efectivo Inicial", "monto": formatear_moneda(resultado.efectivo_inicial)})
        filas.append({"concepto": "Efectivo Final (real)", "monto": formatear_moneda(resultado.efectivo_final_real)})
        with ui.element("div").classes("w-full overflow-x-auto"):
            ui.table(columns=columnas, rows=filas, row_key="concepto").classes("w-full")

    with ui.column().classes("w-full gap-4"):
        _tabla_flujo(flujo_indirecto, "Método Indirecto")
        _tabla_flujo(flujo_directo, "Método Directo")

def _render_tab_capital(estado_cambios: EstadoCambiosCapital) -> None:
    with ui.column().classes("w-full gap-2"):
        columnas = [
            {"name": "concepto", "label": "Concepto", "field": "concepto", "align": "left"},
            {"name": "contrib", "label": "Capital Contribuido", "field": "contrib", "align": "right"},
            {"name": "ganado", "label": "Capital Ganado", "field": "ganado", "align": "right"},
            {"name": "total", "label": "Total", "field": "total", "align": "right"},
        ]
        filas = []
        for f in estado_cambios.filas:
            concepto = f.concepto.upper() if f.es_encabezado_categoria else f.concepto
            filas.append({
                "concepto": concepto,
                "contrib": formatear_moneda(f.capital_contribuido) if f.capital_contribuido is not None else "",
                "ganado": formatear_moneda(f.capital_ganado) if f.capital_ganado is not None else "",
                "total": formatear_moneda(f.totales) if f.totales is not None else "",
            })
        with ui.element("div").classes("w-full overflow-x-auto"):
            ui.table(columns=columnas, rows=filas, row_key="concepto").classes("w-full")


# ---------------------------------------------------------------------------
# AUDITORÍA NIF (Hito 4)
# ---------------------------------------------------------------------------
def build_auditoria_nif() -> None:
    ui.label("Auditoría de Activos Fijos (NIF C-6) y Pasivos (NIF C-19)").classes("text-sm text-gray-500 mb-4")

    with ui.tabs().classes("w-full") as tabs:
        tab_depreciacion = ui.tab("📊 Depreciación (NIF C-6)")
        tab_amortizacion = ui.tab("💰 Amortización (NIF C-19)")

    with ui.tab_panels(tabs, value=tab_depreciacion).classes("w-full"):
        with ui.tab_panel(tab_depreciacion):
            ui.label("Depreciación de Activos Fijos").classes(f"text-lg font-bold text-[{COLOR_GUINDA}]")
            contenedor_resultados_dep = ui.column().classes("w-full mt-2")

            with ui.card().classes("w-full mb-4"):
                with ui.row().classes("w-full gap-4"):
                    concepto_dep = ui.input(label="Concepto del activo", value="Maquinaria Industrial").classes("w-1/3")
                    costo_dep = ui.number(label="Costo de adquisición", value=100000.0, format="%.2f", min=0).classes("w-1/4")
                    residual_dep = ui.number(label="Valor residual", value=10000.0, format="%.2f", min=0).classes("w-1/4")
                    vida_dep = ui.number(label="Vida útil (años)", value=5, format="%.0f", min=1, step=1).classes("w-1/6")

                metodo_dep = ui.select(
                    label="Método de Depreciación",
                    options=["Línea Recta", "Suma de Dígitos", "Unidades de Producción", "Saldos Decrecientes"],
                    value="Línea Recta"
                ).classes("w-1/3")

                with ui.column().classes("w-full mt-2") as col_unidades:
                    ui.label("Configuración para Unidades de Producción").classes("font-semibold text-sm")
                    with ui.row().classes("w-full gap-4"):
                        capacidad_dep = ui.number(label="Capacidad total", value=100000.0, format="%.2f", min=0).classes("w-1/4")
                        tipo_unidad_dep = ui.select(
                            label="Tipo de unidad",
                            options=["KM", "Unidades", "Horas"],
                            value="Unidades"
                        ).classes("w-1/4")
                        usos_dep = ui.number(
                            label="Uso anual (KM/Unidades/Horas)",
                            value=20000.0, format="%.2f", min=0
                        ).classes("w-1/4")

                def toggle_unidades(*_) -> None:
                    col_unidades.set_visibility(metodo_dep.value == "Unidades de Producción")

                metodo_dep.on("update:model-value", toggle_unidades)
                toggle_unidades()

                ui.button(
                    "Calcular Tabla de Depreciación",
                    on_click=lambda: _calcular_depreciacion(
                        concepto_dep, costo_dep, residual_dep, vida_dep,
                        metodo_dep, capacidad_dep, tipo_unidad_dep, usos_dep,
                        contenedor_resultados_dep
                    )
                ).classes(f"bg-[{COLOR_GUINDA}] hover:bg-[{COLOR_GUINDA_OSCURO}] text-white font-bold mt-2")

            with contenedor_resultados_dep:
                ui.label("Los resultados se mostrarán aquí después de calcular.").classes("text-gray-400 text-sm italic")

        with ui.tab_panel(tab_amortizacion):
            ui.label("Amortización de Pasivos (NIF C-19)").classes(f"text-lg font-bold text-[{COLOR_GUINDA}]")
            contenedor_resultados_amort = ui.column().classes("w-full mt-2")

            with ui.card().classes("w-full mb-4"):
                concepto_amort = ui.input(label="Concepto de la deuda", value="Préstamo Bancario").classes("w-1/2")

                ui.label("Valor de la deuda").classes("font-semibold mt-2")
                with ui.row().classes("w-full gap-4"):
                    valor_total_amort = ui.number(label="Valor total directo", value=500000.0, format="%.2f", min=0).classes("w-1/3")
                    with ui.column().classes("w-1/3"):
                        unidades_amort = ui.number(label="Unidades", value=100, format="%.0f", min=1, step=1).classes("w-full")
                        valor_unitario_amort = ui.number(label="Valor unitario", value=5000.0, format="%.2f", min=0).classes("w-full")
                        monto_calculado_label = ui.label("Monto calculado: $500,000.00").classes("text-sm font-bold text-blue-600")

                        def actualizar_monto_calculado(*_) -> None:
                            unidades = unidades_amort.value or 0
                            valor_unit = valor_unitario_amort.value or 0
                            monto_calc = unidades * valor_unit
                            monto_calculado_label.text = f"Monto calculado: ${monto_calc:,.2f}"
                            valor_total_amort.value = monto_calc

                        unidades_amort.on("update:model-value", actualizar_monto_calculado)
                        valor_unitario_amort.on("update:model-value", actualizar_monto_calculado)
                        actualizar_monto_calculado()

                ui.separator().classes("my-3")

                with ui.row().classes("w-full gap-4"):
                    tasa_amort = ui.number(label="Tasa de interés anual (%)", value=12.0, format="%.2f", min=0).classes("w-1/5")
                    pagos_anio_amort = ui.select(
                        label="Pagos por año",
                        options={"12": "Mensual (12)", "6": "Bimestral (6)", "4": "Trimestral (4)", "2": "Semestral (2)", "1": "Anual (1)"},
                        value="12"
                    ).classes("w-1/5")
                    plazo_amort = ui.number(label="Plazo (años)", value=5, format="%.0f", min=1, step=1).classes("w-1/5")
                    gracia_amort = ui.number(label="Periodos de gracia", value=0, format="%.0f", min=0, step=1).classes("w-1/5")

                metodo_amort = ui.select(
                    label="Método de extinción",
                    options=["Capital Fijo", "Pago al Vencimiento"],
                    value="Capital Fijo"
                ).classes("w-1/3")

                ui.button(
                    "Generar Tabla de Amortización",
                    on_click=lambda: _calcular_amortizacion(
                        concepto_amort, valor_total_amort, tasa_amort,
                        pagos_anio_amort, plazo_amort, gracia_amort, metodo_amort,
                        contenedor_resultados_amort
                    )
                ).classes(f"bg-[{COLOR_GUINDA}] hover:bg-[{COLOR_GUINDA_OSCURO}] text-white font-bold mt-2")

            with contenedor_resultados_amort:
                ui.label("Los resultados se mostrarán aquí después de calcular.").classes("text-gray-400 text-sm italic")


def _calcular_depreciacion(
    concepto: ui.input,
    costo: ui.number,
    residual: ui.number,
    vida: ui.number,
    metodo: ui.select,
    capacidad: ui.number,
    tipo_unidad: ui.select,
    uso_anual: ui.number,
    contenedor: ui.column
) -> None:
    try:
        costo_val = costo.value or 0
        residual_val = residual.value or 0
        vida_val = int(vida.value or 1)
        concepto_val = concepto.value or "Activo"

        if costo_val <= 0:
            ui.notify("El costo de adquisición debe ser mayor a 0.", type="warning")
            return

        metodo_val = metodo.value

        if metodo_val == "Línea Recta":
            tabla = calcular_linea_recta(concepto_val, costo_val, residual_val, vida_val)
        elif metodo_val == "Suma de Dígitos":
            tabla = calcular_suma_digitos(concepto_val, costo_val, residual_val, vida_val)
        elif metodo_val == "Saldos Decrecientes":
            tabla = calcular_saldos_decrecientes(concepto_val, costo_val, residual_val, vida_val)
        elif metodo_val == "Unidades de Producción":
            cap = capacidad.value or 1
            uso = uso_anual.value or 0
            tipo = tipo_unidad.value or "Unidades"
            if cap <= 0:
                ui.notify("La capacidad total debe ser mayor a 0.", type="warning")
                return
            if uso <= 0:
                ui.notify("El uso anual debe ser mayor a 0.", type="warning")
                return
            usos = [uso] * vida_val
            tabla = calcular_unidades_produccion(concepto_val, costo_val, residual_val, vida_val, cap, tipo, usos)
        else:
            ui.notify(f"Método no soportado: {metodo_val}", type="negative")
            return

        contenedor.clear()
        with contenedor:
            with ui.card().classes("w-full bg-gray-50"):
                ui.label(f"Tabla de Depreciación - {tabla.concepto}").classes(f"text-lg font-bold text-[{COLOR_GUINDA}]")
                with ui.row().classes("w-full justify-between text-sm"):
                    ui.label(f"Método: {tabla.metodo}")
                    ui.label(f"Total depreciado: ${tabla.total_depreciado:,.2f}")
                    ui.label(f"Valor en libros final: ${tabla.valor_libros_final:,.2f}")

                columnas = [{"name": str(i), "label": h, "field": str(i), "align": "right" if i > 0 else "left"}
                            for i, h in enumerate(tabla.encabezados)]
                filas_tabla = []
                for fila in tabla.filas:
                    row_dict = {}
                    for i, val in enumerate(fila):
                        key = str(i)
                        if i == 0:
                            row_dict[key] = val
                        else:
                            row_dict[key] = f"${val:,.2f}" if isinstance(val, float) else val
                    filas_tabla.append(row_dict)

                with ui.element("div").classes("w-full overflow-x-auto"):
                    ui.table(columns=columnas, rows=filas_tabla, row_key="0").classes("w-full")

                ui.label(tabla.info_extra[0]).classes("text-xs text-gray-500 mt-1")

            def exportar_dep():
                try:
                    data = exportar_depreciacion_excel(tabla)
                    ui.download(data, f"Depreciacion_{tabla.concepto}.xlsx")
                    ui.notify("Excel generado correctamente", type="positive")
                except Exception as e:
                    ui.notify(f"Error al exportar: {str(e)}", type="negative")

            ui.button("Exportar a Excel", on_click=exportar_dep, icon="download").classes(
                "bg-green-700 hover:bg-green-800 text-white font-bold"
            )

    except Exception as e:
        ui.notify(f"Error al calcular depreciación: {str(e)}", type="negative")


def _calcular_amortizacion(
    concepto: ui.input,
    valor_total: ui.number,
    tasa: ui.number,
    pagos_anio: ui.select,
    plazo: ui.number,
    gracia: ui.number,
    metodo: ui.select,
    contenedor: ui.column
) -> None:
    try:
        monto_val = valor_total.value or 0
        tasa_val = (tasa.value or 0) / 100
        pagos_anio_val = int(pagos_anio.value or 12)
        plazo_val = int(plazo.value or 1)
        gracia_val = int(gracia.value or 0)
        concepto_val = concepto.value or "Deuda"

        if monto_val <= 0:
            ui.notify("El monto total debe ser mayor a 0.", type="warning")
            return

        total_pagos = plazo_val * pagos_anio_val
        tasa_periodica = tasa_val / pagos_anio_val

        if metodo.value == "Capital Fijo":
            tabla = calcular_amortizacion_capital_fijo(concepto_val, monto_val, tasa_periodica, total_pagos, gracia_val)
        else:
            tabla = calcular_amortizacion_vencimiento(concepto_val, monto_val, tasa_periodica, total_pagos, gracia_val)

        contenedor.clear()
        with contenedor:
            with ui.card().classes("w-full bg-gray-50"):
                ui.label(f"Tabla de Amortización - {tabla.concepto}").classes(f"text-lg font-bold text-[{COLOR_GUINDA}]")
                with ui.row().classes("w-full justify-between text-sm"):
                    ui.label(f"Método: {tabla.metodo}")
                    ui.label(f"Total intereses: ${tabla.total_intereses:,.2f}")
                    ui.label(f"Total pagado: ${tabla.total_pagado:,.2f}")

                columnas = [{"name": str(i), "label": h, "field": str(i), "align": "right" if i > 0 else "left"}
                            for i, h in enumerate(tabla.encabezados)]
                filas_tabla = []
                for fila in tabla.filas:
                    row_dict = {}
                    for i, val in enumerate(fila):
                        key = str(i)
                        row_dict[key] = val if i == 0 else f"${val:,.2f}" if isinstance(val, float) else val
                    filas_tabla.append(row_dict)

                with ui.element("div").classes("w-full overflow-x-auto"):
                    ui.table(columns=columnas, rows=filas_tabla, row_key="0").classes("w-full")

                for info in tabla.info_extra:
                    ui.label(info).classes("text-xs text-gray-500")

            def exportar_amort():
                try:
                    data = exportar_amortizacion_excel(tabla)
                    ui.download(data, f"Amortizacion_{tabla.concepto}.xlsx")
                    ui.notify("Excel generado correctamente", type="positive")
                except Exception as e:
                    ui.notify(f"Error al exportar: {str(e)}", type="negative")

            ui.button("Exportar a Excel", on_click=exportar_amort, icon="download").classes(
                "bg-green-700 hover:bg-green-800 text-white font-bold"
            )

    except Exception as e:
        ui.notify(f"Error al calcular amortización: {str(e)}", type="negative")


# ---------------------------------------------------------------------------
# Procesamiento y exportación (modo avanzado)
# ---------------------------------------------------------------------------
def _procesar_y_mostrar_avanzado(estado: EstadoSesion, empresa_val: str, periodo_val: str,
                                  elaboro_val: str = "", catedratico_val: str = "") -> None:
    movimientos_esf = _construir_movimientos_esf_avanzado(estado)
    movimientos_eri = _construir_movimientos_eri_avanzado(estado)

    resultado_eri = calcular_eri(movimientos_eri)
    resultado_esf = calcular_esf(
        movimientos_esf,
        resultado_del_ejercicio=resultado_eri.utilidad_integral,
        resultado_del_ejercicio_anterior=0.0,
    )

    flujo_indirecto = generar_flujo_indirecto(movimientos_esf, resultado_eri.utilidad_integral)
    flujo_directo = generar_flujo_directo(movimientos_esf, resultado_eri.utilidad_integral)
    estado_cambios = generar_estado_cambios_capital(movimientos_esf, resultado_eri.utilidad_integral)

    estado.ultimo_esf = resultado_esf
    estado.ultimo_eri = resultado_eri
    estado.ultimo_flujo_indirecto = flujo_indirecto
    estado.ultimo_flujo_directo = flujo_directo
    estado.ultimo_estado_cambios = estado_cambios
    estado.ultima_empresa = empresa_val
    estado.ultimo_periodo = periodo_val
    estado.ultimo_elaboro = elaboro_val
    estado.ultimo_catedratico = catedratico_val

    if estado.resultados_container is None:
        return

    estado.resultados_container.clear()
    with estado.resultados_container:
        ui.notify(
            f"Cálculo procesado. Cuentas detectadas: {len(movimientos_esf) + len(movimientos_eri)}",
            type="positive",
        )

        with ui.row().classes("w-full justify-between items-center mb-4 border-b border-gray-300 pb-2"):
            ui.label("Reportes Financieros Generados").classes(f"text-xl font-bold text-[{COLOR_GUINDA}]")
            with ui.row().classes("gap-2"):
                ui.button("Exportar Excel (.xlsx)", on_click=lambda: _exportar_excel(estado), icon="download").classes(
                    "bg-green-700 hover:bg-green-800 text-white font-bold px-4 py-2 rounded"
                )
                ui.button("Descargar PDF", on_click=lambda: _exportar_pdf(estado), icon="download").classes(
                    "bg-gray-700 hover:bg-gray-800 text-white font-bold px-4 py-2 rounded"
                )

        tabs = ui.tabs().classes(f"text-[{COLOR_GUINDA}]").props(f'indicator-color=amber-9 active-color="{COLOR_GUINDA}"')
        with tabs:
            t1 = ui.tab("ESF")
            t2 = ui.tab("ERI")
            t3 = ui.tab("Flujo de Efectivo")
            t4 = ui.tab("Cambios en Capital")
            t5 = ui.tab("Auditoría NIF (C-6 / C-19)")

        with ui.tab_panels(tabs, value=t1).classes("w-full"):
            with ui.tab_panel(t1):
                _render_tab_esf_avanzado(resultado_esf)
            with ui.tab_panel(t2):
                _render_tab_eri_avanzado(resultado_eri)
            with ui.tab_panel(t3):
                _render_tab_flujo(flujo_indirecto, flujo_directo)
            with ui.tab_panel(t4):
                _render_tab_capital(estado_cambios)
            with ui.tab_panel(t5):
                build_auditoria_nif()

        with ui.row().classes(
            f"w-full justify-between items-center mt-6 pt-3 border-t-2 border-[{COLOR_DORADO}] "
            "text-sm text-gray-700"
        ):
            ui.label(f"Elaboró (Alumno): {elaboro_val or '—'}").classes("font-medium")
            ui.label(f"Catedrático / Maestro: {catedratico_val or '—'}").classes("font-medium")

def _calcular_y_mostrar_avanzado(estado: EstadoSesion, empresa_val: str, periodo_val: str,
                                  elaboro_val: str = "", catedratico_val: str = "") -> None:
    if _validar_nombres_duplicados(estado.filas_capital_dinamico, "Catálogo Complementario 1 (Capital Contable Dinámico)"):
        return
    if _validar_nombres_duplicados(estado.filas_subcuentas_dinamicas, "Catálogo Complementario 2 (Subcuentas de Balance)"):
        return

    movimientos_esf = _construir_movimientos_esf_avanzado(estado)
    movimientos_eri = _construir_movimientos_eri_avanzado(estado)

    if not movimientos_esf and not movimientos_eri:
        ui.notify("Por favor ingresa al menos un movimiento contable antes de calcular.", type="warning")
        return

    _procesar_y_mostrar_avanzado(estado, empresa_val, periodo_val, elaboro_val, catedratico_val)

def _exportar_pdf(estado: EstadoSesion) -> None:
    if estado.ultimo_esf is None:
        ui.notify("Primero debes calcular los estados financieros.", type="warning")
        return
    try:
        pdf_bytes = generar_pdf_estados_financieros(
            empresa=estado.ultima_empresa,
            periodo=estado.ultimo_periodo,
            esf=estado.ultimo_esf,
            eri=estado.ultimo_eri,
            flujo_indirecto=estado.ultimo_flujo_indirecto,
            flujo_directo=estado.ultimo_flujo_directo,
            estado_cambios=estado.ultimo_estado_cambios,
        )
        ui.download(pdf_bytes, "Estados_Financieros.pdf")
        ui.notify("PDF generado correctamente", type="positive")
    except Exception as e:
        ui.notify(f"Error al generar PDF: {str(e)}", type="negative")

def _exportar_excel(estado: EstadoSesion) -> None:
    if estado.ultimo_esf is None:
        ui.notify("Primero debes calcular los estados financieros.", type="warning")
        return
    try:
        excel_bytes = generar_excel_estados_financieros(
            esf=estado.ultimo_esf,
            eri=estado.ultimo_eri,
            flujo_indirecto=estado.ultimo_flujo_indirecto,
            estado_cambios=estado.ultimo_estado_cambios,
            empresa=estado.ultima_empresa,
            periodo=estado.ultimo_periodo,
        )
        ui.download(excel_bytes, "Estados_Financieros.xlsx")
        ui.notify("Excel generado correctamente", type="positive")
    except Exception as e:
        ui.notify(f"Error al generar Excel: {str(e)}", type="negative")


# ---------------------------------------------------------------------------
# UI Layout
# ---------------------------------------------------------------------------
def _construir_membrete() -> None:
    with ui.row().classes(
        "w-full bg-white text-[#800000] px-4 py-2 items-center justify-center "
        "border-b-2 border-[#F2A900]"
    ):
        ui.label(
            "UNIVERSIDAD AUTÓNOMA DE NUEVO LEÓN | FACULTAD DE CONTADURÍA PÚBLICA Y ADMINISTRACIÓN"
        ).classes("text-xs md:text-sm font-semibold tracking-wide text-center")

def _construir_encabezado(estado: EstadoSesion, on_cambio_modo) -> None:
    # FIX: Se añade z-30 para evitar solapamientos con otros elementos
    with ui.row().classes(
        f"w-full bg-[{COLOR_GUINDA}] text-white p-4 mb-2 items-center justify-between "
        f"shadow-md border-b-4 border-[{COLOR_DORADO}] flex-wrap gap-2 z-30 relative"
    ):
        with ui.column().classes("gap-0"):
            ui.label("Herramienta de Autoevaluación Financiera — FACPYA").classes("text-2xl font-bold")
            ui.label("Estado de Resultado Integral y Estado de Situación Financiera").classes("text-md opacity-80")

        with ui.column().classes("items-end gap-1"):
            ui.label("Modo de Autoevaluación").classes("text-xs font-semibold opacity-90 self-end")
            ui.select(
                options=[MODO_SIMPLE, MODO_AVANZADO],
                value=estado.modo,
                on_change=on_cambio_modo,
            ).props(f'outlined dense bg-color=white color="{COLOR_GUINDA}"').classes("w-72 bg-white rounded shadow")

def build_modo_simplificado(estado: EstadoSesion) -> None:
    ui.label(
        "1er Semestre — Estado de Resultado Integral y Estado de Situación Financiera"
    ).classes("text-sm text-gray-500 mb-4")

    with ui.tabs().classes("w-full") as tabs:
        tab_eri = ui.tab("1. Estado de Resultado Integral")
        tab_esf = ui.tab("2. Balance General (ESF)")
        tab_informe = ui.tab("3. Informe Final y Diagnóstico")

    tabs.on_value_change(lambda *_: estado.recalcular_informe_simple())

    with ui.tab_panels(tabs, value=tab_eri).classes("w-full"):
        with ui.tab_panel(tab_eri):
            ui.label("Captura los saldos según la cascada oficial. Los subtotales se calculan solos.").classes(
                "text-sm text-gray-500 mb-2"
            )

            def campo_captura(linea: LineaERI, etiqueta: str | None = None) -> None:
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(etiqueta or linea.value).classes("w-2/3")
                    campo = ui.number(
                        value=0, min=0, format="%.2f",
                        on_change=lambda *_: estado.recalcular_eri_simple(),
                    ).classes("w-1/3")
                    if linea == LineaERI.ORI:
                        campo.props(remove="min")
                    estado.campos_eri[linea.value] = campo

            def campo_subtotal(clave: str) -> None:
                with ui.row().classes("w-full items-center justify-between bg-gray-50 rounded px-2"):
                    ui.label(clave).classes("w-2/3 font-bold")
                    campo = ui.number(value=0, format="%.2f").props("readonly").classes("w-1/3")
                    estado.subtotales_eri[clave] = campo

            ui.label("Ventas").classes("font-semibold mt-2")
            campo_captura(LineaERI.VENTAS)
            campo_captura(LineaERI.COSTO_VENTAS)
            campo_subtotal("Utilidad/Pérdida Bruta (3°)")

            ui.label("Gastos Generales").classes("font-semibold mt-2")
            campo_captura(LineaERI.GASTOS_VENTA)
            campo_captura(LineaERI.GASTOS_ADMINISTRACION)
            campo_subtotal("Gastos Generales (6°)")
            campo_subtotal("Utilidad/Pérdida Antes de Otros Prod. y Gastos (7°)")

            ui.label("Otros Productos y Gastos").classes("font-semibold mt-2")
            campo_captura(LineaERI.OTROS_PRODUCTOS)
            campo_captura(LineaERI.OTROS_GASTOS)
            campo_subtotal("Neto Otros Productos y Gastos (10°)")
            campo_subtotal("Utilidad/Pérdida en Operación (11°)")

            ui.label("Resultado Integral de Financiamiento").classes("font-semibold mt-2")
            campo_captura(LineaERI.PRODUCTOS_FINANCIEROS)
            campo_captura(LineaERI.GASTOS_FINANCIEROS)
            campo_subtotal("Resultado Integral de Financiamiento (14°)")
            campo_subtotal("Utilidad/Pérdida Antes de Impuestos (15°)")

            ui.label("Impuestos a la Utilidad").classes("font-semibold mt-2")
            campo_captura(LineaERI.ISR)
            campo_captura(LineaERI.PTU)
            campo_subtotal("Impuestos a la Utilidad (18°)")
            campo_subtotal("Utilidad/Pérdida Neta (19°)")

            ui.label("Otros Resultados Integrales").classes("font-semibold mt-2")
            campo_captura(LineaERI.ORI, etiqueta="Otros Resultados Integrales (ORI) — admite negativos")
            campo_subtotal("Utilidad/Pérdida Integral (21°)")

        with ui.tab_panel(tab_esf):
            ui.label(
                "Captura las cuentas predeterminadas por categoría, o agrega tus propias cuentas personalizadas."
            ).classes("text-sm text-gray-500 mb-2")

            with ui.row().classes("w-full gap-8"):
                for grupo in GRUPOS_ESF_ORDEN:
                    with ui.column().classes("w-full md:w-[30%]"):
                        ui.label(grupo).classes("font-bold text-md mt-2")
                        for cuenta in listar_cuentas_simplificadas(grupo):
                            with ui.row().classes("w-full items-center justify-between"):
                                ui.label(cuenta.nombre).classes("text-sm w-2/3")
                                campo = ui.number(
                                    value=0, min=0, format="%.2f",
                                    on_change=lambda *_: estado.recalcular_informe_simple(),
                                ).classes("w-1/3")
                                estado.campos_esf_predeterminados[cuenta.nombre] = campo

            ui.separator().classes("my-4")

            with ui.card().classes("w-full bg-blue-50"):
                ui.label("Utilidad / Pérdida del Ejercicio").classes("font-bold")
                ui.label(
                    "Se autocompleta con la Utilidad/Pérdida Integral (21°) del Tab 1. "
                    "Puedes editarla manualmente si estás resolviendo solo el Balance General."
                ).classes("text-xs text-gray-500")

                def marcar_edicion_manual(*_) -> None:
                    estado.utilidad_perdida_editada_manualmente = True
                    estado.recalcular_informe_simple()

                campo_utilidad = ui.number(value=0, format="%.2f", on_change=marcar_edicion_manual)
                estado.campo_utilidad_perdida = campo_utilidad

                ui.button(
                    "Restaurar valor calculado desde el ERI",
                    on_click=lambda: (
                        setattr(estado, "utilidad_perdida_editada_manualmente", False),
                        estado.recalcular_eri_simple(),
                    ),
                ).props("flat dense")

            ui.separator().classes("my-4")

            with ui.card().classes("w-full"):
                ui.label("Agregar Cuenta Personalizada").classes("font-bold")
                with ui.row().classes("w-full items-end gap-4"):
                    campo_nombre = ui.input(label="Nombre de la cuenta").classes("w-1/3")
                    campo_categoria = ui.select(
                        options=CATEGORIAS_ESF_DISPONIBLES, label="Categoría ESF"
                    ).classes("w-1/4")
                    campo_comportamiento = ui.select(
                        options=COMPORTAMIENTOS_DISPONIBLES, label="Comportamiento", value="suma"
                    ).classes("w-1/6")

                    def agregar_cuenta_personalizada() -> None:
                        nombre = (campo_nombre.value or "").strip()
                        if not nombre or not campo_categoria.value:
                            ui.notify("Indica un nombre y una categoría ESF.", type="warning")
                            return
                        if nombre in estado.campos_esf_predeterminados or any(
                            c.nombre == nombre for c in estado.cuentas_personalizadas
                        ):
                            ui.notify("Ya existe una cuenta con ese nombre.", type="warning")
                            return

                        cuenta = crear_cuenta_personalizada(
                            nombre=nombre,
                            categoria_esf=campo_categoria.value,
                            comportamiento=campo_comportamiento.value,
                        )
                        estado.cuentas_personalizadas.append(cuenta)

                        with estado.contenedor_personalizadas:
                            with ui.row().classes("w-full items-center justify-between"):
                                ui.label(
                                    f"{cuenta.nombre}  ·  {campo_categoria.value}  ·  {cuenta.comportamiento.value}"
                                ).classes("text-sm w-2/3")
                                campo_monto = ui.number(
                                    value=0, min=0, format="%.2f",
                                    on_change=lambda *_: estado.recalcular_informe_simple(),
                                ).classes("w-1/3")
                                estado.campos_esf_personalizados[cuenta.nombre] = campo_monto

                        campo_nombre.value = ""
                        campo_categoria.value = None
                        ui.notify(f"Cuenta '{cuenta.nombre}' agregada.", type="positive")

                    ui.button("Agregar", on_click=agregar_cuenta_personalizada).classes("w-1/6")

                ui.label("Cuentas personalizadas capturadas:").classes("text-sm font-semibold mt-3")
                estado.contenedor_personalizadas = ui.column().classes("w-full gap-1")

        with ui.tab_panel(tab_informe):
            ui.button("Actualizar Informe", on_click=lambda: estado.recalcular_informe_simple()).classes("mb-4")

            estado.banner_simple = ui.label("").classes("w-full text-center text-lg font-bold rounded p-3 mb-4")

            with ui.row().classes("w-full gap-8 items-start"):
                estado.contenedor_informe_eri = ui.column().classes("w-full md:w-[35%] gap-1")
                estado.contenedor_informe_esf = ui.row().classes("w-full md:w-[60%] gap-4")

    estado.recalcular_eri_simple()

def build_modo_avanzado(estado: EstadoSesion) -> None:
    ui.label(
        "NIF V3 — Suite Profesional: captura comparativa Año Actual / Año Anterior"
    ).classes("text-sm text-gray-500 mb-4")

    estado.inputs_cuentas_fijas = {}
    estado.filas_capital_dinamico = []
    estado.filas_subcuentas_dinamicas = []

    # --- Historial de Prácticas ---
    with ui.card().classes(f"w-full mb-4 border-l-4 border-[{COLOR_DORADO}]"):
        ui.label("Historial de Prácticas").classes(f"text-lg font-bold text-[{COLOR_GUINDA}]")
        with ui.row().classes("w-full items-center gap-2 flex-wrap"):
            estado.practica_nombre_input = ui.input(label="Nombre práctica", value="Práctica 1").classes("w-48")
            estado.select_practicas = ui.select(label="Prácticas guardadas", options={}).classes("w-64")
            ui.button("Guardar", icon="save", on_click=lambda: _guardar_practica_ui(estado)).classes(
                f"bg-[{COLOR_GUINDA}] hover:bg-[{COLOR_GUINDA_OSCURO}] text-white font-bold"
            )
            ui.button("Cargar", icon="folder_open", on_click=lambda: _cargar_practica_ui(estado)).classes(
                f"bg-[{COLOR_GUINDA}] hover:bg-[{COLOR_GUINDA_OSCURO}] text-white font-bold"
            )
            ui.button("Nueva", icon="add", on_click=lambda: _nueva_practica_ui(estado)).classes(
                "bg-gray-700 hover:bg-gray-800 text-white font-bold"
            )
            ui.button("Eliminar", icon="delete", on_click=lambda: _eliminar_practica_ui(estado)).classes(
                "bg-red-700 hover:bg-red-800 text-white font-bold"
            )
        _refrescar_lista_practicas(estado)

    # --- Datos Generales ---
    with ui.card().classes("w-full mb-4 border-l-4 border-gray-600"):
        ui.label("Datos Generales").classes("text-lg font-bold text-gray-800")
        with ui.row().classes("gap-4"):
            estado.input_empresa_ref = ui.input(label="Nombre de la empresa", value="Empresa Demo S.A.").classes("w-64")
            ui.input(label="Tipo de sociedad", value="S.A. de C.V.").classes("w-40")
        with ui.row().classes("gap-4"):
            estado.input_periodo_ref = ui.input(
                label="Periodo actual", value="Del 1 de enero al 31 de diciembre de 2025"
            ).classes("w-80")
            ui.input(label="Periodo anterior", value="Al 31 de diciembre de 2024").classes("w-80")

    # --- Catálogo Fijo ---
    with ui.card().classes("w-full mb-4 border-l-4 border-gray-600"):
        ui.label("Catálogo de Cuentas Fijo (NIF V3)").classes("text-lg font-bold text-gray-800")
        for clasif in Clasificacion:
            cuentas = listar_cuentas_por_clasificacion(clasif)
            if not cuentas:
                continue
            with ui.card().classes(f"w-full border-l-4 border-[{COLOR_GUINDA}]"):
                ui.label(clasif.value).classes(f"text-md font-bold text-[{COLOR_GUINDA}]")
                for cuenta in cuentas:
                    with ui.row().classes("w-full items-center gap-4"):
                        ui.label(cuenta.nombre).classes("w-64 text-sm text-gray-700")
                        inp_actual = ui.number(label="Año Actual", value=0.0, format="%.2f").classes("w-40")
                        inp_anterior = ui.number(label="Año Anterior", value=0.0, format="%.2f").classes("w-40")
                        if cuenta.clasificacion == Clasificacion.RESULTADO:
                            inp_anterior.disable()
                        estado.inputs_cuentas_fijas[cuenta.nombre] = (inp_actual, inp_anterior)

    # --- Catálogo Complementario 2 ---
    with ui.card().classes("w-full mb-4 border-l-4 border-gray-600"):
        ui.label("Catálogo Complementario 2: Otras Subcuentas de Balance").classes(
            "text-lg font-bold text-gray-800"
        )
        ui.label("Agrega cuentas adicionales de Activo/Pasivo con su NIF correspondiente.").classes(
            "text-sm text-gray-500"
        )
        container_subcuentas = ui.column().classes("w-full")
        with container_subcuentas:
            _agregar_fila_subcuenta_dinamica(estado)
        ui.button(
            "+ Agregar subcuenta de balance",
            on_click=lambda: _agregar_fila_subcuenta_dinamica(estado),
        ).classes("bg-gray-700 text-white")
        estado.container_subcuentas_ref = container_subcuentas

    # --- Catálogo Complementario 1 ---
    with ui.card().classes("w-full mb-4 border-l-4 border-gray-600"):
        ui.label("Catálogo Complementario 1: Capital Contable Dinámico").classes(
            "text-lg font-bold text-gray-800"
        )
        ui.label("Agrega cuentas adicionales de Capital Contable.").classes("text-sm text-gray-500")
        container_capital = ui.column().classes("w-full")
        with container_capital:
            _agregar_fila_capital_dinamico(estado)
        ui.button(
            "+ Agregar cuenta de capital",
            on_click=lambda: _agregar_fila_capital_dinamico(estado),
        ).classes("bg-gray-700 text-white")
        estado.container_capital_ref = container_capital

    # --- Datos Académicos ---
    with ui.card().classes(f"w-full mb-4 border-l-4 border-[{COLOR_DORADO}]"):
        ui.label("Datos Académicos").classes(f"text-lg font-bold text-[{COLOR_GUINDA}]")
        with ui.row().classes("gap-4"):
            estado.input_elaboro_ref = ui.input(label="Elaboró (Alumno)", value="").classes("w-64")
            estado.input_catedratico_ref = ui.input(label="Catedrático / Maestro", value="").classes("w-64")

    # --- Botón principal ---
    ui.button(
        "Calcular Estados Financieros",
        on_click=lambda: _calcular_y_mostrar_avanzado(
            estado,
            estado.input_empresa_ref.value,
            estado.input_periodo_ref.value,
            estado.input_elaboro_ref.value,
            estado.input_catedratico_ref.value,
        ),
    ).classes(
        f"text-lg bg-[{COLOR_GUINDA}] hover:bg-[{COLOR_GUINDA_OSCURO}] text-white font-bold my-6 w-full py-3 "
        f"shadow-lg border-b-4 border-[{COLOR_DORADO}]"
    )

    estado.resultados_container = ui.column().classes("w-full")


# ---------------------------------------------------------------------------
# Funciones de persistencia UI
# ---------------------------------------------------------------------------
def _guardar_practica_ui(estado: EstadoSesion) -> None:
    nombre = estado.practica_nombre_input.value if estado.practica_nombre_input else "Práctica"
    if not nombre.strip():
        ui.notify("Ingresa un nombre para la práctica", type="warning")
        return
    guardar_practica_supabase(estado, nombre.strip())

def _cargar_practica_ui(estado: EstadoSesion) -> None:
    if estado.select_practicas is None:
        return
    val = estado.select_practicas.value
    if val is None:
        ui.notify("Selecciona una práctica", type="warning")
        return
    try:
        practica_id = int(val)
    except Exception:
        ui.notify("ID de práctica inválido", type="negative")
        return
    cargar_practica_supabase(estado, practica_id)

def _nueva_practica_ui(estado: EstadoSesion) -> None:
    _reiniciar_formulario_avanzado(estado, mantener_datos_generales=False)
    estado.practica_id_actual = None
    ui.notify("Formulario listo para una nueva práctica", type="positive")

def _eliminar_practica_ui(estado: EstadoSesion) -> None:
    if estado.select_practicas is None:
        return
    val = estado.select_practicas.value
    if val is None:
        ui.notify("Selecciona una práctica", type="warning")
        return
    try:
        practica_id = int(val)
    except Exception:
        ui.notify("ID de práctica inválido", type="negative")
        return
    eliminar_practica_supabase(estado, practica_id)


# ---------------------------------------------------------------------------
# Página principal
# ---------------------------------------------------------------------------
@ui.page("/")
def pagina_principal() -> None:
    estado = EstadoSesion()
    
    # 1. Dibujar Membrete
    _construir_membrete()

    def renderizar_cuerpo() -> None:
        cuerpo.clear()
        with cuerpo:
            if estado.modo == MODO_SIMPLE:
                build_modo_simplificado(estado)
            else:
                build_modo_avanzado(estado)

    def cambiar_modo(evento) -> None:
        nuevo_modo = evento.value if hasattr(evento, "value") else evento
        if nuevo_modo not in (MODO_SIMPLE, MODO_AVANZADO):
            return
        estado.modo = nuevo_modo
        renderizar_cuerpo()

    # 2. Dibujar Encabezado (ahora se renderiza ANTES del cuerpo)
    _construir_encabezado(estado, cambiar_modo)

    # 3. Dibujar Contenedor del Cuerpo (con un margen inferior de resguardo)
    cuerpo = ui.column().classes("w-full px-4 max-w-7xl mx-auto mb-16")
    
    # 4. Cargar contenido inicial
    renderizar_cuerpo()

ui.run(
    title="Autoevaluación Financiera FACPYA",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8080)),
    reload=False,
)
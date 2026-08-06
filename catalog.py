"""
catalog.py — Catálogo Estándar V3 (NIF)
Herramienta de Autoevaluación Financiera — Motor Contable NIF

V3 sustituye a la V2 simplificada. Cambios principales:
  - Las cuentas de balance ya no se clasifican solo en 6 categorías ESF;
    ahora llevan un agrupador NIF con código (C1, C3, C4... ) que es el
    nivel real de agrupación usado por el ESF, el Flujo de Efectivo y el
    Estado de Cambios en Capital Contable.
  - Las cuentas complementarias de activo (Depreciación Acumulada,
    Estimación de Cobros Dudosos, Amortización Acumulada) se modelan
    explícitamente como tales (es_complementaria=True) en vez de solo
    "cuentas que restan", porque el Flujo de Efectivo Indirecto necesita
    mostrarlas como una fila propia (partida virtual).
  - Las cuentas de Resultado siguen usando LineaERI (igual que en V2),
    porque el ERI necesita más granularidad de la que da el agrupador NIF
    "Ingresos / Costo de venta / Gastos generales / RIF".
"""

from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# 1. ENUMS DE CLASIFICACIÓN
# ---------------------------------------------------------------------------

class Clasificacion(str, Enum):
    """Las 6 grandes secciones de los estados financieros."""
    ACTIVO_CIRCULANTE = "Activo Circulante"
    ACTIVO_NO_CIRCULANTE = "Activo No Circulante"
    PASIVO_CORTO_PLAZO = "Pasivo a Corto Plazo"
    PASIVO_LARGO_PLAZO = "Pasivo a Largo Plazo"
    CAPITAL_CONTABLE = "Capital Contable"
    RESULTADO = "Resultado"


class SeccionCapital(str, Enum):
    """Sección dentro de Capital Contable, usada por el Edo. de Cambios en el Capital."""
    CAPITAL_CONTRIBUIDO = "Capital Contribuido"
    UTILIDADES = "Utilidades"
    RESERVAS = "Reservas"


class LineaERI(str, Enum):
    """Las líneas/conceptos que alimentan la cascada del ERI (sin cambios respecto a V2)."""
    VENTAS = "Ventas"
    COSTO_VENTAS = "Costo de Ventas"
    GASTOS_VENTA = "Gastos de Venta"
    GASTOS_ADMINISTRACION = "Gastos de Administración"
    OTROS_PRODUCTOS = "Otros Productos"
    OTROS_GASTOS = "Otros Gastos"
    PRODUCTOS_FINANCIEROS = "Productos Financieros"
    GASTOS_FINANCIEROS = "Gastos Financieros"
    ISR = "ISR"
    PTU = "PTU"
    ORI = "Otros Resultados Integrales"


# Signo intrínseco de cada línea del ERI (no depende de la cuenta capturada,
# depende del concepto). ORI se captura ya con signo (puede ser pérdida
# integral negativa), por eso lleva +1: su signo lo pone el usuario.
SIGNO_LINEA_ERI: dict[LineaERI, int] = {
    LineaERI.VENTAS: 1,
    LineaERI.COSTO_VENTAS: -1,
    LineaERI.GASTOS_VENTA: -1,
    LineaERI.GASTOS_ADMINISTRACION: -1,
    LineaERI.OTROS_PRODUCTOS: 1,
    LineaERI.OTROS_GASTOS: -1,
    LineaERI.PRODUCTOS_FINANCIEROS: 1,
    LineaERI.GASTOS_FINANCIEROS: -1,
    LineaERI.ISR: -1,
    LineaERI.PTU: -1,
    LineaERI.ORI: 1,
}


class NIF(Enum):
    """
    Agrupadores técnicos NIF con su código, tal como el Catálogo de Cuentas
    Actualizado V3. El valor de cada miembro es (etiqueta, código).
    """
    EQUIVALENTES_EFECTIVO = ("Equivalentes de efectivo", "C1")
    CUENTAS_POR_COBRAR = ("Cuentas por cobrar", "C3")
    INVENTARIOS = ("Inventarios", "C4")
    PAGOS_ANTICIPADOS = ("Pagos anticipados", "C5")
    PROPIEDAD_PLANTA_EQUIPO = ("Propiedad, planta y equipo", "C6")
    ACTIVOS_INTANGIBLES = ("Activos intangibles / Otros activos", "C8")
    CTAS_POR_PAGAR_PROVEEDORES = ("Cuentas por pagar a proveedores", "C9")
    DOCUMENTOS_POR_PAGAR_CP = ("Documentos por pagar a corto plazo", "C9")
    CONTRIBUCIONES_POR_PAGAR = ("Contribuciones por pagar", "C9")
    OTRAS_CTAS_POR_PAGAR = ("Otras cuentas por pagar", "C9")
    DEUDA_LARGO_PLAZO = ("Deuda a largo plazo", "C19")
    CAPITAL_SOCIAL = ("Capital social", "C11")
    APORTACIONES_FUTUROS_AUMENTOS = ("Aportaciones para futuros aumentos de capital", "C11")
    RESERVA_LEGAL = ("Reserva legal", "C11")
    RESERVA_REINVERSION = ("Reserva de reinversión", "C11")
    UTILIDADES_ACUMULADAS = ("Utilidades acumuladas", "C11")
    PERDIDAS_ACUMULADAS = ("Pérdidas acumuladas", "C11")

    @property
    def etiqueta(self) -> str:
        return self.value[0]

    @property
    def codigo(self) -> str:
        return self.value[1]


# El .value de cada miembro de NIF es la tupla (etiqueta, código), NO solo la
# etiqueta. Por eso `NIF("Propiedad, planta y equipo")` falla con ValueError:
# ese string no es un valor válido del Enum (le falta el código). Cualquier
# UI que solo capture/envíe la etiqueta (p.ej. un ui.select con options de
# solo texto) debe resolver el Enum a través de este mapeo, no con NIF(...).
NIF_POR_ETIQUETA: dict[str, NIF] = {n.etiqueta: n for n in NIF}


def nif_por_etiqueta(etiqueta: str) -> NIF | None:
    """Resuelve un miembro de NIF a partir de su etiqueta (texto visible en la UI)."""
    return NIF_POR_ETIQUETA.get(etiqueta)


# ---------------------------------------------------------------------------
# 2. MODELO DE CUENTA
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CuentaV3:
    nombre: str
    clasificacion: Clasificacion

    # Para cuentas de balance (todo menos RESULTADO):
    nif: NIF | None = None
    es_complementaria: bool = False   # ej. Depreciación Acumulada, Estimación de Cobros Dudosos
    seccion_capital: SeccionCapital | None = None  # solo si clasificacion == CAPITAL_CONTABLE
    signo: int = 1                    # +1 normal, -1 si la cuenta reduce su grupo (ej. Pérdidas acumuladas)

    # Para cuentas de resultado (clasificacion == RESULTADO):
    linea_eri: LineaERI | None = None

    def __post_init__(self):
        if self.clasificacion == Clasificacion.RESULTADO:
            if self.linea_eri is None:
                raise ValueError(f"'{self.nombre}': cuenta de Resultado requiere linea_eri.")
        else:
            if self.nif is None:
                raise ValueError(f"'{self.nombre}': cuenta de balance requiere nif.")
            if self.clasificacion == Clasificacion.CAPITAL_CONTABLE and self.seccion_capital is None:
                raise ValueError(f"'{self.nombre}': cuenta de Capital Contable requiere seccion_capital.")


# ---------------------------------------------------------------------------
# 3. CATÁLOGO ESTÁNDAR V3
# ---------------------------------------------------------------------------

CATALOGO_V3: dict[str, CuentaV3] = {}


def _registrar(cuenta: CuentaV3) -> None:
    CATALOGO_V3[cuenta.nombre] = cuenta


# --- ACTIVO CIRCULANTE ---
for _nombre in ["Caja", "Bancos", "Inversiones a la vista / temporales"]:
    _registrar(CuentaV3(_nombre, Clasificacion.ACTIVO_CIRCULANTE, nif=NIF.EQUIVALENTES_EFECTIVO))

for _nombre in [
    "Clientes", "Documentos por cobrar", "Deudores diversos",
    "IVA acreditable", "IVA acreditable pagado", "IVA a favor",
]:
    _registrar(CuentaV3(_nombre, Clasificacion.ACTIVO_CIRCULANTE, nif=NIF.CUENTAS_POR_COBRAR))

for _nombre in ["Almacén", "Mercancías en tránsito"]:
    _registrar(CuentaV3(_nombre, Clasificacion.ACTIVO_CIRCULANTE, nif=NIF.INVENTARIOS))

for _nombre in [
    "Anticipo a proveedores", "Papelería y útiles", "Publicidad",
    "Primas de seguro", "Rentas pagadas por anticipado",
]:
    _registrar(CuentaV3(_nombre, Clasificacion.ACTIVO_CIRCULANTE, nif=NIF.PAGOS_ANTICIPADOS))

# Complementaria de Activo Circulante
_registrar(CuentaV3(
    "Estimación de cobros dudosos", Clasificacion.ACTIVO_CIRCULANTE,
    nif=NIF.CUENTAS_POR_COBRAR, es_complementaria=True, signo=-1,
))

# --- ACTIVO NO CIRCULANTE ---
for _nombre in [
    "Terrenos", "Edificios", "Equipo de transporte",
    "Muebles y enseres", "Mobiliario y eq. de oficina", "Eq. de cómputo",
]:
    _registrar(CuentaV3(_nombre, Clasificacion.ACTIVO_NO_CIRCULANTE, nif=NIF.PROPIEDAD_PLANTA_EQUIPO))

for _nombre in [
    "Depósitos en garantía", "Inversiones en valores",
    "Gastos de organización", "Gastos de instalación", "Gastos de constitución",
]:
    _registrar(CuentaV3(_nombre, Clasificacion.ACTIVO_NO_CIRCULANTE, nif=NIF.ACTIVOS_INTANGIBLES))

# Complementarias de Activo No Circulante
_registrar(CuentaV3(
    "Depreciación acumulada de...", Clasificacion.ACTIVO_NO_CIRCULANTE,
    nif=NIF.PROPIEDAD_PLANTA_EQUIPO, es_complementaria=True, signo=-1,
))
_registrar(CuentaV3(
    "Amortización acumulada de...", Clasificacion.ACTIVO_NO_CIRCULANTE,
    nif=NIF.ACTIVOS_INTANGIBLES, es_complementaria=True, signo=-1,
))

# --- PASIVO A CORTO PLAZO ---
_registrar(CuentaV3("Proveedores", Clasificacion.PASIVO_CORTO_PLAZO, nif=NIF.CTAS_POR_PAGAR_PROVEEDORES))
for _nombre in ["Documentos por pagar", "Préstamos bancarios"]:
    _registrar(CuentaV3(_nombre, Clasificacion.PASIVO_CORTO_PLAZO, nif=NIF.DOCUMENTOS_POR_PAGAR_CP))
for _nombre in ["Contribuciones por pagar", "IVA trasladado", "IVA trasladado cobrado", "IVA por pagar"]:
    _registrar(CuentaV3(_nombre, Clasificacion.PASIVO_CORTO_PLAZO, nif=NIF.CONTRIBUCIONES_POR_PAGAR))
for _nombre in ["Acreedores diversos", "Anticipo de clientes", "Dividendos por pagar", "Rentas cobradas por anticipado"]:
    _registrar(CuentaV3(_nombre, Clasificacion.PASIVO_CORTO_PLAZO, nif=NIF.OTRAS_CTAS_POR_PAGAR))

# --- PASIVO A LARGO PLAZO ---
for _nombre in ["Hipotecas por pagar", "Documentos por pagar a largo plazo", "Préstamos bancarios a largo plazo"]:
    _registrar(CuentaV3(_nombre, Clasificacion.PASIVO_LARGO_PLAZO, nif=NIF.DEUDA_LARGO_PLAZO))

# --- CAPITAL CONTABLE ---
_registrar(CuentaV3(
    "Capital social", Clasificacion.CAPITAL_CONTABLE,
    nif=NIF.CAPITAL_SOCIAL, seccion_capital=SeccionCapital.CAPITAL_CONTRIBUIDO,
))
_registrar(CuentaV3(
    "Aportaciones para futuros aumentos de capital", Clasificacion.CAPITAL_CONTABLE,
    nif=NIF.APORTACIONES_FUTUROS_AUMENTOS, seccion_capital=SeccionCapital.CAPITAL_CONTRIBUIDO,
))
_registrar(CuentaV3(
    "Reserva legal", Clasificacion.CAPITAL_CONTABLE,
    nif=NIF.RESERVA_LEGAL, seccion_capital=SeccionCapital.RESERVAS,
))
_registrar(CuentaV3(
    "Reserva de reinversión", Clasificacion.CAPITAL_CONTABLE,
    nif=NIF.RESERVA_REINVERSION, seccion_capital=SeccionCapital.RESERVAS,
))
_registrar(CuentaV3(
    "Utilidades acumuladas", Clasificacion.CAPITAL_CONTABLE,
    nif=NIF.UTILIDADES_ACUMULADAS, seccion_capital=SeccionCapital.UTILIDADES,
))
_registrar(CuentaV3(
    "Pérdidas acumuladas", Clasificacion.CAPITAL_CONTABLE,
    nif=NIF.PERDIDAS_ACUMULADAS, seccion_capital=SeccionCapital.UTILIDADES, signo=-1,
))

# --- CUENTAS DE RESULTADO (alimentan el ERI) ---
_registrar(CuentaV3("Ventas", Clasificacion.RESULTADO, linea_eri=LineaERI.VENTAS))
_registrar(CuentaV3("Otros productos", Clasificacion.RESULTADO, linea_eri=LineaERI.OTROS_PRODUCTOS))
_registrar(CuentaV3("Productos financieros", Clasificacion.RESULTADO, linea_eri=LineaERI.PRODUCTOS_FINANCIEROS))
_registrar(CuentaV3("Costo de venta", Clasificacion.RESULTADO, linea_eri=LineaERI.COSTO_VENTAS))
_registrar(CuentaV3("Gasto de venta", Clasificacion.RESULTADO, linea_eri=LineaERI.GASTOS_VENTA))
_registrar(CuentaV3("Gasto de administración", Clasificacion.RESULTADO, linea_eri=LineaERI.GASTOS_ADMINISTRACION))
_registrar(CuentaV3("Otros gastos", Clasificacion.RESULTADO, linea_eri=LineaERI.OTROS_GASTOS))
_registrar(CuentaV3("Gastos financieros", Clasificacion.RESULTADO, linea_eri=LineaERI.GASTOS_FINANCIEROS))
# ISR, PTU y ORI no vienen en el catálogo de cuentas pero son obligatorios
# para completar la cascada del ERI (líneas 16°, 17° y 20°).
_registrar(CuentaV3("ISR", Clasificacion.RESULTADO, linea_eri=LineaERI.ISR))
_registrar(CuentaV3("PTU", Clasificacion.RESULTADO, linea_eri=LineaERI.PTU))
_registrar(CuentaV3("Otros Resultados Integrales", Clasificacion.RESULTADO, linea_eri=LineaERI.ORI))


# ---------------------------------------------------------------------------
# 4. AGRUPACIONES PARA ARMAR LOS REPORTES (usadas por engine.py y main.py)
# ---------------------------------------------------------------------------

NIFS_POR_CLASIFICACION: dict[Clasificacion, list[NIF]] = {
    Clasificacion.ACTIVO_CIRCULANTE: [
        NIF.EQUIVALENTES_EFECTIVO, NIF.CUENTAS_POR_COBRAR, NIF.INVENTARIOS, NIF.PAGOS_ANTICIPADOS,
    ],
    Clasificacion.ACTIVO_NO_CIRCULANTE: [
        NIF.PROPIEDAD_PLANTA_EQUIPO, NIF.ACTIVOS_INTANGIBLES,
    ],
    Clasificacion.PASIVO_CORTO_PLAZO: [
        NIF.CTAS_POR_PAGAR_PROVEEDORES, NIF.DOCUMENTOS_POR_PAGAR_CP,
        NIF.CONTRIBUCIONES_POR_PAGAR, NIF.OTRAS_CTAS_POR_PAGAR,
    ],
    Clasificacion.PASIVO_LARGO_PLAZO: [NIF.DEUDA_LARGO_PLAZO],
}

NIFS_CAPITAL_CONTRIBUIDO: list[NIF] = [NIF.CAPITAL_SOCIAL, NIF.APORTACIONES_FUTUROS_AUMENTOS]
NIFS_CAPITAL_GANADO: list[NIF] = [
    NIF.RESERVA_LEGAL, NIF.RESERVA_REINVERSION, NIF.UTILIDADES_ACUMULADAS, NIF.PERDIDAS_ACUMULADAS,
]


# ---------------------------------------------------------------------------
# 5. FUNCIONES DE ACCESO
# ---------------------------------------------------------------------------

def obtener_cuenta(nombre: str) -> CuentaV3 | None:
    return CATALOGO_V3.get(nombre)


def obtener_cuenta_por_linea_eri(linea: LineaERI) -> CuentaV3 | None:
    """Busca, por grupo (no por nombre), la cuenta de Resultado asociada a una línea del ERI."""
    for cuenta in CATALOGO_V3.values():
        if cuenta.clasificacion == Clasificacion.RESULTADO and cuenta.linea_eri == linea:
            return cuenta
    return None


def listar_cuentas_por_nif(nif: NIF, incluir_complementarias: bool = True) -> list[CuentaV3]:
    return [
        c for c in CATALOGO_V3.values()
        if c.nif == nif and (incluir_complementarias or not c.es_complementaria)
    ]


def listar_cuentas_por_clasificacion(clasificacion: Clasificacion) -> list[CuentaV3]:
    return [c for c in CATALOGO_V3.values() if c.clasificacion == clasificacion]


# ---------------------------------------------------------------------------
# 6. FACTORÍAS PARA CUENTAS DINÁMICAS (catálogos complementarios)
# ---------------------------------------------------------------------------
# Nota: la UI para capturar estas cuentas dinámicas (Catálogo Complementario 1
# y 2 de tu especificación de Excel) se construye en un paso posterior; aquí
# solo se deja lista la lógica del modelo de datos.

def crear_cuenta_balance_dinamica(
    nombre: str, clasificacion: Clasificacion, nif: NIF, es_complementaria: bool = False,
) -> CuentaV3:
    """Cuenta dinámica de Activo/Pasivo (Catálogo Complementario 2: 'Otras Subcuentas')."""
    if clasificacion == Clasificacion.CAPITAL_CONTABLE:
        raise ValueError("Usa crear_cuenta_capital_dinamica() para cuentas de Capital Contable.")
    return CuentaV3(
        nombre=nombre, clasificacion=clasificacion, nif=nif,
        es_complementaria=es_complementaria, signo=-1 if es_complementaria else 1,
    )


def crear_cuenta_capital_dinamica(
    nombre: str, seccion: SeccionCapital, reductora: bool = False,
) -> CuentaV3:
    """
    Cuenta dinámica de Capital Contable (Catálogo Complementario 1), con la
    bandera 'Reductora de capital' (SI/NO) de tu especificación de Excel.
    Se registra sin NIF fijo (nif=None no es válido en CuentaV3 para Capital,
    así que se usa un NIF genérico por sección para no romper la agrupación
    por NIF en reportes que lo requieran).
    """
    nif_generico = {
        SeccionCapital.CAPITAL_CONTRIBUIDO: NIF.APORTACIONES_FUTUROS_AUMENTOS,
        SeccionCapital.UTILIDADES: NIF.UTILIDADES_ACUMULADAS,
        SeccionCapital.RESERVAS: NIF.RESERVA_LEGAL,
    }[seccion]
    return CuentaV3(
        nombre=nombre, clasificacion=Clasificacion.CAPITAL_CONTABLE,
        nif=nif_generico, seccion_capital=seccion, signo=-1 if reductora else 1,
    )


if __name__ == "__main__":
    print(f"Total de cuentas en catálogo V3: {len(CATALOGO_V3)}")
    for clasif in Clasificacion:
        cuentas = listar_cuentas_por_clasificacion(clasif)
        print(f"  {clasif.value}: {len(cuentas)} cuentas")
    print("\nNIFs de Activo Circulante:")
    for nif in NIFS_POR_CLASIFICACION[Clasificacion.ACTIVO_CIRCULANTE]:
        cuentas = listar_cuentas_por_nif(nif)
        print(f"  [{nif.codigo}] {nif.etiqueta}: {[c.nombre for c in cuentas]}")
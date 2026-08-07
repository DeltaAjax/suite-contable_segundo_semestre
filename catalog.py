"""
catalog.py — Catálogo Unificado (V2 Simplificado + V3 Avanzado NIF)
Herramienta de Autoevaluación Financiera (FACPYA)

Este módulo reemplaza a `catalog_v2_1er_semestre.py` y `catalog_v3_avanzado.py`,
consolidando ambos catálogos de cuentas en un único modelo de datos (`Cuenta`)
y un único registro (`CATALOGO_UNIFICADO`), de modo que la aplicación pueda
operar en:

  - "Modo Simplificado (1er Semestre)": expone únicamente el comportamiento
    binario suma/resta y las 6 categorías del ESF, sin exponer al alumno la
    naturaleza deudora/acreedora ni los agrupadores técnicos NIF.

  - "Modo Avanzado (NIF V3)": expone el agrupador NIF con código (C1, C3,
    C4...), la bandera `es_complementaria` (para que el Flujo de Efectivo
    Indirecto pueda mostrar depreciaciones/estimaciones como fila propia) y
    la sección de Capital Contable (para el Estado de Cambios en el Capital).

Diseño clave:
  - Todas las cuentas del catálogo estándar (las que capturan ambos archivos
    originales) existen con el MISMO nombre en ambas versiones, por lo que se
    registran una sola vez en `CATALOGO_UNIFICADO` con `es_simplificada=True`
    y con los campos completos de la versión avanzada (nif, es_complementaria,
    seccion_capital) ya resueltos.
  - Las cuentas creadas en tiempo de ejecución mediante las factorías de los
    "catálogos complementarios" de NIF V3 (subcuentas de balance / subcuentas
    de capital) NO se insertan en `CATALOGO_UNIFICADO` — igual que en el
    archivo original, quedan como objetos `Cuenta` independientes que la UI
    avanzada gestiona por su cuenta — y se marcan con `es_simplificada=False`
    porque son exclusivas del modo avanzado.
  - Las cuentas personalizadas del modo simplificado (formulario de 1er
    semestre) tampoco se insertan en el registro global; se marcan con
    `es_simplificada=True` porque nacen en, y pertenecen a, ese modo.
"""

from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# 1. ENUMERACIONES COMBINADAS
# ---------------------------------------------------------------------------

class Clasificacion(str, Enum):
    """Las 6 grandes secciones del Estado de Situación Financiera."""
    ACTIVO_CIRCULANTE = "Activo Circulante"
    ACTIVO_NO_CIRCULANTE = "Activo No Circulante"
    PASIVO_CORTO_PLAZO = "Pasivo a Corto Plazo"
    PASIVO_LARGO_PLAZO = "Pasivo a Largo Plazo"
    CAPITAL_CONTABLE = "Capital Contable"
    RESULTADO = "Resultado"


class SeccionCapital(str, Enum):
    """Secciones de Capital Contable usadas por el Estado de Cambios en el Capital."""
    CAPITAL_CONTRIBUIDO = "Capital Contribuido"
    UTILIDADES = "Utilidades"
    RESERVAS = "Reservas"


class LineaERI(str, Enum):
    """Las 11 líneas/conceptos que alimentan la cascada del ERI."""
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
# integral negativa), por eso lleva +1: su signo lo pone quien lo captura.
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
    Actualizado V3. El valor de cada miembro es la tupla (etiqueta, código).
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
# etiqueta, por lo que `NIF("Propiedad, planta y equipo")` falla. Cualquier UI
# que capture/envíe solo la etiqueta debe resolver el Enum vía este mapeo.
NIF_POR_ETIQUETA: dict[str, NIF] = {n.etiqueta: n for n in NIF}


def nif_por_etiqueta(etiqueta: str) -> "NIF | None":
    """Resuelve un miembro de NIF a partir de su etiqueta (texto visible en la UI)."""
    return NIF_POR_ETIQUETA.get(etiqueta)


class Comportamiento(str, Enum):
    """Comportamiento binario requerido por la vista simplificada de 1er semestre."""
    SUMA = "suma"
    RESTA = "resta"


class TipoEstado(str, Enum):
    """A qué estado financiero pertenece la cuenta."""
    ESF = "ESF"
    ERI = "ERI"


# ---------------------------------------------------------------------------
# 2. MODELO DE CUENTA ÚNICO
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Cuenta:
    """
    Modelo único de cuenta que integra los atributos de ambas versiones.

    - Los campos `nif`, `es_complementaria` y `seccion_capital` sólo tienen
      sentido para cuentas de balance (clasificacion != RESULTADO) y son los
      que consume el motor/UI del modo avanzado NIF V3.
    - Los campos `comportamiento` y `signo` son equivalentes entre sí (suma
      <-> +1, resta <-> -1) y son los que consume el motor/UI del modo
      simplificado de 1er semestre; se mantienen ambos, sincronizados, para
      no romper ninguno de los dos motores.
    - `linea_eri` sólo aplica a cuentas de Resultado (clasificacion == RESULTADO).
    - `es_simplificada` indica si la cuenta es visible por defecto en la
      interfaz de 1er semestre (True) o si es exclusiva del modo avanzado
      NIF V3 (False, típicamente cuentas dinámicas de los catálogos
      complementarios).
    """
    nombre: str
    clasificacion: Clasificacion
    tipo: TipoEstado = TipoEstado.ESF

    # Atributos del modo avanzado (NIF V3) — sólo para cuentas de balance:
    nif: "NIF | None" = None
    es_complementaria: bool = False
    seccion_capital: "SeccionCapital | None" = None
    signo: int = 1  # +1 normal, -1 para cuentas reductoras o complementarias

    # Atributos del modo simplificado (1er semestre):
    comportamiento: Comportamiento = Comportamiento.SUMA

    # Sólo para cuentas de Resultado (clasificacion == RESULTADO):
    linea_eri: "LineaERI | None" = None

    # Bandera de visibilidad por modo:
    es_simplificada: bool = True

    def __post_init__(self) -> None:
        # Única validación estructural que ambas versiones originales exigían:
        # una cuenta de Resultado necesita su línea del ERI para poder
        # alimentar la cascada, sin importar el modo en que se esté usando.
        if self.clasificacion == Clasificacion.RESULTADO and self.linea_eri is None:
            raise ValueError(f"'{self.nombre}': cuenta de Resultado requiere linea_eri.")

    def signo_num(self) -> int:
        """
        Devuelve +1 o -1 de acuerdo al comportamiento/signo de la cuenta, para
        compatibilidad con ambos motores (el simplificado consulta
        `comportamiento`, el avanzado consulta `signo`; aquí se reconcilian
        por si alguno de los dos quedara desincronizado).
        """
        if self.comportamiento == Comportamiento.RESTA or self.signo < 0:
            return -1
        return 1


def _comportamiento_de_signo(signo: int) -> Comportamiento:
    return Comportamiento.RESTA if signo < 0 else Comportamiento.SUMA


# ---------------------------------------------------------------------------
# 3. REGISTRO CENTRALIZADO DEL CATÁLOGO
# ---------------------------------------------------------------------------
# Nota: en los dos archivos originales, el catálogo "estándar" (el que no se
# crea dinámicamente) contiene exactamente las mismas cuentas, con el mismo
# nombre, en ambas versiones. Por eso aquí se registran una sola vez, con
# es_simplificada=True, y con los metadatos completos del modo avanzado ya
# resueltos (nif / es_complementaria / seccion_capital).

CATALOGO_UNIFICADO: dict[str, Cuenta] = {}


def _registrar_balance(
    nombre: str,
    clasificacion: Clasificacion,
    nif: NIF,
    *,
    es_complementaria: bool = False,
    seccion_capital: "SeccionCapital | None" = None,
    signo: int = 1,
    es_simplificada: bool = True,
) -> None:
    CATALOGO_UNIFICADO[nombre] = Cuenta(
        nombre=nombre,
        clasificacion=clasificacion,
        tipo=TipoEstado.ESF,
        nif=nif,
        es_complementaria=es_complementaria,
        seccion_capital=seccion_capital,
        signo=signo,
        comportamiento=_comportamiento_de_signo(signo),
        es_simplificada=es_simplificada,
    )


def _registrar_resultado(nombre: str, linea: LineaERI, *, es_simplificada: bool = True) -> None:
    signo = SIGNO_LINEA_ERI[linea]
    CATALOGO_UNIFICADO[nombre] = Cuenta(
        nombre=nombre,
        clasificacion=Clasificacion.RESULTADO,
        tipo=TipoEstado.ERI,
        signo=signo,
        comportamiento=_comportamiento_de_signo(signo),
        linea_eri=linea,
        es_simplificada=es_simplificada,
    )


# --- ACTIVO CIRCULANTE ---
for _nombre in ["Caja", "Bancos", "Inversiones a la vista / temporales"]:
    _registrar_balance(_nombre, Clasificacion.ACTIVO_CIRCULANTE, NIF.EQUIVALENTES_EFECTIVO)

for _nombre in [
    "Clientes", "Documentos por cobrar", "Deudores diversos",
    "IVA acreditable", "IVA acreditable pagado", "IVA a favor",
]:
    _registrar_balance(_nombre, Clasificacion.ACTIVO_CIRCULANTE, NIF.CUENTAS_POR_COBRAR)

for _nombre in ["Almacén", "Mercancías en tránsito"]:
    _registrar_balance(_nombre, Clasificacion.ACTIVO_CIRCULANTE, NIF.INVENTARIOS)

for _nombre in [
    "Anticipo a proveedores", "Papelería y útiles", "Publicidad",
    "Primas de seguro", "Rentas pagadas por anticipado",
]:
    _registrar_balance(_nombre, Clasificacion.ACTIVO_CIRCULANTE, NIF.PAGOS_ANTICIPADOS)

# Complementaria de Activo Circulante -> es_complementaria=True, signo=-1
_registrar_balance(
    "Estimación de cobros dudosos", Clasificacion.ACTIVO_CIRCULANTE, NIF.CUENTAS_POR_COBRAR,
    es_complementaria=True, signo=-1,
)

# --- ACTIVO NO CIRCULANTE ---
for _nombre in [
    "Terrenos", "Edificios", "Equipo de transporte",
    "Muebles y enseres", "Mobiliario y eq. de oficina", "Eq. de cómputo",
]:
    _registrar_balance(_nombre, Clasificacion.ACTIVO_NO_CIRCULANTE, NIF.PROPIEDAD_PLANTA_EQUIPO)

for _nombre in [
    "Depósitos en garantía", "Inversiones en valores",
    "Gastos de organización", "Gastos de instalación", "Gastos de constitución",
]:
    _registrar_balance(_nombre, Clasificacion.ACTIVO_NO_CIRCULANTE, NIF.ACTIVOS_INTANGIBLES)

# Complementarias de Activo No Circulante -> es_complementaria=True, signo=-1
_registrar_balance(
    "Depreciación acumulada de...", Clasificacion.ACTIVO_NO_CIRCULANTE, NIF.PROPIEDAD_PLANTA_EQUIPO,
    es_complementaria=True, signo=-1,
)
_registrar_balance(
    "Amortización acumulada de...", Clasificacion.ACTIVO_NO_CIRCULANTE, NIF.ACTIVOS_INTANGIBLES,
    es_complementaria=True, signo=-1,
)

# --- PASIVO A CORTO PLAZO ---
_registrar_balance("Proveedores", Clasificacion.PASIVO_CORTO_PLAZO, NIF.CTAS_POR_PAGAR_PROVEEDORES)
for _nombre in ["Documentos por pagar", "Préstamos bancarios"]:
    _registrar_balance(_nombre, Clasificacion.PASIVO_CORTO_PLAZO, NIF.DOCUMENTOS_POR_PAGAR_CP)
for _nombre in ["Contribuciones por pagar", "IVA trasladado", "IVA trasladado cobrado", "IVA por pagar"]:
    _registrar_balance(_nombre, Clasificacion.PASIVO_CORTO_PLAZO, NIF.CONTRIBUCIONES_POR_PAGAR)
for _nombre in ["Acreedores diversos", "Anticipo de clientes", "Dividendos por pagar", "Rentas cobradas por anticipado"]:
    _registrar_balance(_nombre, Clasificacion.PASIVO_CORTO_PLAZO, NIF.OTRAS_CTAS_POR_PAGAR)

# --- PASIVO A LARGO PLAZO ---
for _nombre in ["Hipotecas por pagar", "Documentos por pagar a largo plazo", "Préstamos bancarios a largo plazo"]:
    _registrar_balance(_nombre, Clasificacion.PASIVO_LARGO_PLAZO, NIF.DEUDA_LARGO_PLAZO)

# --- CAPITAL CONTABLE ---
_registrar_balance(
    "Capital social", Clasificacion.CAPITAL_CONTABLE, NIF.CAPITAL_SOCIAL,
    seccion_capital=SeccionCapital.CAPITAL_CONTRIBUIDO,
)
_registrar_balance(
    "Aportaciones para futuros aumentos de capital", Clasificacion.CAPITAL_CONTABLE,
    NIF.APORTACIONES_FUTUROS_AUMENTOS, seccion_capital=SeccionCapital.CAPITAL_CONTRIBUIDO,
)
_registrar_balance(
    "Reserva legal", Clasificacion.CAPITAL_CONTABLE, NIF.RESERVA_LEGAL,
    seccion_capital=SeccionCapital.RESERVAS,
)
_registrar_balance(
    "Reserva de reinversión", Clasificacion.CAPITAL_CONTABLE, NIF.RESERVA_REINVERSION,
    seccion_capital=SeccionCapital.RESERVAS,
)
_registrar_balance(
    "Utilidades acumuladas", Clasificacion.CAPITAL_CONTABLE, NIF.UTILIDADES_ACUMULADAS,
    seccion_capital=SeccionCapital.UTILIDADES,
)
# Pérdidas acumuladas: cuenta reductora de Capital -> signo=-1
_registrar_balance(
    "Pérdidas acumuladas", Clasificacion.CAPITAL_CONTABLE, NIF.PERDIDAS_ACUMULADAS,
    seccion_capital=SeccionCapital.UTILIDADES, signo=-1,
)

# --- CUENTAS DE RESULTADO (alimentan el ERI) ---
_registrar_resultado("Ventas", LineaERI.VENTAS)
_registrar_resultado("Otros productos", LineaERI.OTROS_PRODUCTOS)
_registrar_resultado("Productos financieros", LineaERI.PRODUCTOS_FINANCIEROS)
_registrar_resultado("Costo de venta", LineaERI.COSTO_VENTAS)
_registrar_resultado("Gasto de venta", LineaERI.GASTOS_VENTA)
_registrar_resultado("Gasto de administración", LineaERI.GASTOS_ADMINISTRACION)
_registrar_resultado("Otros gastos", LineaERI.OTROS_GASTOS)
_registrar_resultado("Gastos financieros", LineaERI.GASTOS_FINANCIEROS)
# ISR, PTU y ORI no vienen en el catálogo de cuentas pero son obligatorios
# para completar la cascada del ERI (líneas 16°, 17° y 20° de la plantilla).
_registrar_resultado("ISR", LineaERI.ISR)
_registrar_resultado("PTU", LineaERI.PTU)
_registrar_resultado("Otros Resultados Integrales", LineaERI.ORI)


# ---------------------------------------------------------------------------
# 4. AGRUPACIONES AUXILIARES PARA REPORTES (modo avanzado)
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
# 5. OPCIONES PARA CUENTAS PERSONALIZADAS (UI modo simplificado)
# ---------------------------------------------------------------------------
# Las 6 categorías ESF tal como las expone el formulario de 1er semestre.
# "Capital Contribuido" y "Capital Ganado" son subcategorías de
# Clasificacion.CAPITAL_CONTABLE; se resuelven a (clasificacion, seccion)
# mediante el mapeo siguiente para poder construir una Cuenta completa.
CATEGORIAS_ESF_DISPONIBLES: list[str] = [
    Clasificacion.ACTIVO_CIRCULANTE.value,
    Clasificacion.ACTIVO_NO_CIRCULANTE.value,
    Clasificacion.PASIVO_CORTO_PLAZO.value,
    Clasificacion.PASIVO_LARGO_PLAZO.value,
    "Capital Contribuido",
    "Capital Ganado",
]

COMPORTAMIENTOS_DISPONIBLES: list[str] = [c.value for c in Comportamiento]

# Mapeo de categoría ESF (texto de la UI simplificada) -> (clasificacion, seccion_capital)
_CATEGORIA_ESF_A_CLASIFICACION: dict[str, tuple[Clasificacion, "SeccionCapital | None"]] = {
    Clasificacion.ACTIVO_CIRCULANTE.value: (Clasificacion.ACTIVO_CIRCULANTE, None),
    Clasificacion.ACTIVO_NO_CIRCULANTE.value: (Clasificacion.ACTIVO_NO_CIRCULANTE, None),
    Clasificacion.PASIVO_CORTO_PLAZO.value: (Clasificacion.PASIVO_CORTO_PLAZO, None),
    Clasificacion.PASIVO_LARGO_PLAZO.value: (Clasificacion.PASIVO_LARGO_PLAZO, None),
    "Capital Contribuido": (Clasificacion.CAPITAL_CONTABLE, SeccionCapital.CAPITAL_CONTRIBUIDO),
    # "Capital Ganado" no distingue en la UI simplificada entre Reservas y
    # Utilidades; se ubica en Utilidades por default (igual que Utilidades /
    # Pérdidas acumuladas, las cuentas más comunes de este grupo).
    "Capital Ganado": (Clasificacion.CAPITAL_CONTABLE, SeccionCapital.UTILIDADES),
}


# ---------------------------------------------------------------------------
# 6. FACTORÍAS DE CUENTAS DINÁMICAS Y PERSONALIZADAS
# ---------------------------------------------------------------------------

def crear_cuenta_personalizada(nombre: str, categoria_esf: str, comportamiento: str) -> Cuenta:
    """
    Crea una cuenta personalizada capturada por el alumno en el formulario
    de 1er semestre (catálogo V2). No se agrega a CATALOGO_UNIFICADO: es
    responsabilidad de quien la crea conservarla (p. ej. en la sesión del
    usuario), igual que en el motor original.
    """
    if categoria_esf not in CATEGORIAS_ESF_DISPONIBLES:
        raise ValueError(f"Categoría ESF inválida: {categoria_esf}")
    if comportamiento not in COMPORTAMIENTOS_DISPONIBLES:
        raise ValueError(f"Comportamiento inválido: {comportamiento}")

    clasificacion, seccion_capital = _CATEGORIA_ESF_A_CLASIFICACION[categoria_esf]
    comportamiento_enum = Comportamiento(comportamiento)
    signo = 1 if comportamiento_enum == Comportamiento.SUMA else -1

    return Cuenta(
        nombre=nombre,
        clasificacion=clasificacion,
        tipo=TipoEstado.ESF,
        seccion_capital=seccion_capital,
        signo=signo,
        comportamiento=comportamiento_enum,
        es_simplificada=True,
    )


def crear_cuenta_balance_dinamica(
    nombre: str, clasificacion: Clasificacion, nif: NIF, es_complementaria: bool = False,
) -> Cuenta:
    """
    Cuenta dinámica de Activo/Pasivo (Catálogo Complementario 2: 'Otras
    Subcuentas' del modo avanzado NIF V3). No se agrega a CATALOGO_UNIFICADO.
    """
    if clasificacion == Clasificacion.CAPITAL_CONTABLE:
        raise ValueError("Usa crear_cuenta_capital_dinamica() para cuentas de Capital Contable.")
    if clasificacion == Clasificacion.RESULTADO:
        raise ValueError("Las cuentas de Resultado no se crean con esta factoría.")

    signo = -1 if es_complementaria else 1
    return Cuenta(
        nombre=nombre,
        clasificacion=clasificacion,
        tipo=TipoEstado.ESF,
        nif=nif,
        es_complementaria=es_complementaria,
        signo=signo,
        comportamiento=_comportamiento_de_signo(signo),
        es_simplificada=False,
    )


def crear_cuenta_capital_dinamica(
    nombre: str, seccion: SeccionCapital, reductora: bool = False,
) -> Cuenta:
    """
    Cuenta dinámica de Capital Contable (Catálogo Complementario 1 del modo
    avanzado NIF V3), con la bandera 'Reductora de capital' (SI/NO). Se
    registra con un NIF genérico por sección para no romper la agrupación
    por NIF en reportes que lo requieran (igual que en el motor original).
    No se agrega a CATALOGO_UNIFICADO.
    """
    nif_generico = {
        SeccionCapital.CAPITAL_CONTRIBUIDO: NIF.APORTACIONES_FUTUROS_AUMENTOS,
        SeccionCapital.UTILIDADES: NIF.UTILIDADES_ACUMULADAS,
        SeccionCapital.RESERVAS: NIF.RESERVA_LEGAL,
    }[seccion]

    signo = -1 if reductora else 1
    return Cuenta(
        nombre=nombre,
        clasificacion=Clasificacion.CAPITAL_CONTABLE,
        tipo=TipoEstado.ESF,
        nif=nif_generico,
        seccion_capital=seccion,
        signo=signo,
        comportamiento=_comportamiento_de_signo(signo),
        es_simplificada=False,
    )


# ---------------------------------------------------------------------------
# 7. FUNCIONES DE CONSULTA Y ACCESO
# ---------------------------------------------------------------------------

def obtener_cuenta(nombre: str) -> "Cuenta | None":
    """Busca una cuenta por su nombre exacto en CATALOGO_UNIFICADO."""
    return CATALOGO_UNIFICADO.get(nombre)


def obtener_cuenta_por_linea_eri(linea: LineaERI) -> "Cuenta | None":
    """
    Busca, por línea (no por nombre), la cuenta de Resultado asociada a una
    línea de la cascada del ERI. Esto es lo que debe usar la UI para mapear
    cada campo de captura a su cuenta, en vez de obtener_cuenta(linea.value),
    ya que el nombre "amigable" de la cuenta (ej. 'Costo de venta') no
    siempre coincide textualmente con el nombre de la línea (ej. 'Costo de
    Ventas').
    """
    for cuenta in CATALOGO_UNIFICADO.values():
        if cuenta.clasificacion == Clasificacion.RESULTADO and cuenta.linea_eri == linea:
            return cuenta
    return None


def listar_cuentas_por_clasificacion(
    clasificacion: Clasificacion, solo_simplificadas: bool = False,
) -> list[Cuenta]:
    """
    Devuelve todas las cuentas de una clasificación (sección del ESF, o
    Resultado). Si `solo_simplificadas` es True, filtra únicamente las
    cuentas visibles por defecto en la interfaz de 1er semestre.
    """
    return [
        c for c in CATALOGO_UNIFICADO.values()
        if c.clasificacion == clasificacion and (not solo_simplificadas or c.es_simplificada)
    ]


def listar_cuentas_por_nif(nif: NIF, incluir_complementarias: bool = True) -> list[Cuenta]:
    """Obtiene las cuentas agrupadas bajo un código NIF (modo avanzado)."""
    return [
        c for c in CATALOGO_UNIFICADO.values()
        if c.nif == nif and (incluir_complementarias or not c.es_complementaria)
    ]


def _grupo_v2(cuenta: Cuenta) -> str:
    """
    Reconstruye el valor de "grupo" tal como lo exponía el motor de 1er
    semestre (GrupoESF o LineaERI), a partir del modelo unificado.
    """
    if cuenta.tipo == TipoEstado.ERI:
        return cuenta.linea_eri.value  # type: ignore[union-attr]
    if cuenta.clasificacion == Clasificacion.CAPITAL_CONTABLE:
        if cuenta.seccion_capital == SeccionCapital.CAPITAL_CONTRIBUIDO:
            return "Capital Contribuido"
        return "Capital Ganado"  # UTILIDADES y RESERVAS caen aquí en el modo simplificado
    return cuenta.clasificacion.value


def listar_cuentas_por_grupo(grupo_valor: str) -> list[Cuenta]:
    """
    Compatibilidad con el motor de 1er semestre: obtiene cuentas según el
    valor textual de la categoría (GrupoESF.value o LineaERI.value).
    """
    return [c for c in CATALOGO_UNIFICADO.values() if _grupo_v2(c) == grupo_valor]


if __name__ == "__main__":
    # Prueba rápida manual del catálogo unificado
    print(f"Total de cuentas en catálogo unificado: {len(CATALOGO_UNIFICADO)}")
    print(f"  Simplificadas (1er semestre): "
          f"{sum(1 for c in CATALOGO_UNIFICADO.values() if c.es_simplificada)}")
    print(f"  Exclusivas de modo avanzado: "
          f"{sum(1 for c in CATALOGO_UNIFICADO.values() if not c.es_simplificada)}")

    print("\nEjemplo — Activo Circulante (vista simplificada, grupo V2):")
    for c in listar_cuentas_por_grupo(Clasificacion.ACTIVO_CIRCULANTE.value):
        print(f"  {c.nombre:35s} {c.comportamiento.value}")

    print("\nEjemplo — NIFs de Activo Circulante (vista avanzada):")
    for nif in NIFS_POR_CLASIFICACION[Clasificacion.ACTIVO_CIRCULANTE]:
        cuentas = listar_cuentas_por_nif(nif)
        print(f"  [{nif.codigo}] {nif.etiqueta}: {[c.nombre for c in cuentas]}")

    print("\nEjemplo — cascada ERI:")
    for linea in LineaERI:
        c = obtener_cuenta_por_linea_eri(linea)
        if c:
            print(f"  {linea.value:30s} -> {c.nombre:25s} signo={c.signo_num()}")
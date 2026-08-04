"""
flujo_efectivo.py — Estado de Flujo de Efectivo (Método Directo e Indirecto)
Herramienta de Autoevaluación Financiera — Motor Contable NIF

REGLA ANTIERROR (de tu especificación): está prohibido consolidar en una
sola fila los conceptos de operación. Este módulo itera NIF por NIF /
cuenta por cuenta y genera una fila independiente por cada una — nunca
una fila genérica "Cuentas por cobrar / Inventarios / Pasivos".

Nota importante sobre Complementarias de Activo (Depreciación Acumulada,
Estimación de Cobros Dudosos):
  - Método INDIRECTO: se muestran como fila propia ('partida virtual') en
    Operación, y las cuentas de Activo usan su saldo BRUTO (sin la
    complementaria) en sus variaciones — para no contar el mismo
    movimiento dos veces.
  - Método DIRECTO: no hay partidas virtuales; la complementaria se
    'netea' directo contra su cuenta de activo (tal como pide tu
    especificación), así que las variaciones de Activo Circulante e
    Inversión usan el saldo NETO.
  Ambos métodos llegan al MISMO incremento de efectivo total — solo
  reparten el efecto de la complementaria en secciones distintas
  (Operación vs. Inversión). Esto es una simplificación pedagógica
  explícita de tu especificación, no un error: en un Flujo de Efectivo
  'de libro de texto' completo, el método directo no debería mezclar
  efectos no monetarios dentro de Inversión, pero así lo pide tu guía.
"""

from dataclasses import dataclass, field

from catalog import Clasificacion, NIF, NIFS_POR_CLASIFICACION
from engine import MovimientoESF

_TOLERANCIA = 0.005


@dataclass
class FilaFlujo:
    concepto: str
    monto: float


@dataclass
class ResultadoFlujoEfectivo:
    metodo: str  # "indirecto" | "directo"
    filas_operacion: list[FilaFlujo] = field(default_factory=list)
    total_operacion: float = 0.0
    filas_inversion: list[FilaFlujo] = field(default_factory=list)
    total_inversion: float = 0.0
    filas_financiamiento: list[FilaFlujo] = field(default_factory=list)
    total_financiamiento: float = 0.0
    incremento_efectivo: float = 0.0
    efectivo_inicial: float = 0.0
    efectivo_final_calculado: float = 0.0
    efectivo_final_real: float = 0.0
    concilia: bool = True
    diferencia_conciliacion: float = 0.0


# ---------------------------------------------------------------------------
# Helpers de suma por NIF
# ---------------------------------------------------------------------------

def _neto_nif(movimientos: list[MovimientoESF], nif: NIF, anio: str) -> float:
    """Saldo del NIF incluyendo complementarias (ya vienen con signo -1 vía cuenta.signo)."""
    return round(sum(m.monto(anio) for m in movimientos if m.cuenta.nif == nif), 2)


def _bruto_nif(movimientos: list[MovimientoESF], nif: NIF, anio: str) -> float:
    """Saldo del NIF EXCLUYENDO complementarias (para el método indirecto)."""
    return round(sum(
        m.monto(anio) for m in movimientos if m.cuenta.nif == nif and not m.cuenta.es_complementaria
    ), 2)


def _aumento_complementaria(movimientos: list[MovimientoESF], nif: NIF) -> tuple[str | None, float]:
    """
    Devuelve (nombre_de_la_cuenta_complementaria, aumento) para el NIF dado.
    El aumento se calcula sobre el saldo CRUDO capturado (no el signado),
    porque el alumno captura la depreciación/estimación como un número
    positivo que representa el monto acumulado.
    """
    cuentas_complementarias = [m for m in movimientos if m.cuenta.nif == nif and m.cuenta.es_complementaria]
    if not cuentas_complementarias:
        return None, 0.0
    nombre = cuentas_complementarias[0].cuenta.nombre
    actual = sum(m.monto_actual for m in cuentas_complementarias)
    anterior = sum(m.monto_anterior for m in cuentas_complementarias)
    return nombre, round(actual - anterior, 2)


def _calcular_financiamiento(movimientos: list[MovimientoESF]) -> tuple[list[FilaFlujo], float]:
    """
    Idéntico para ambos métodos: una fila por cada NIF de Pasivo LP, y una
    fila por CADA CUENTA individual de Capital Contable (no por NIF, porque
    varias cuentas de capital comparten el mismo código NIF C11 y deben
    verse por separado, tal como exige tu especificación).
    """
    filas: list[FilaFlujo] = []
    total = 0.0

    for nif in NIFS_POR_CLASIFICACION[Clasificacion.PASIVO_LARGO_PLAZO]:
        actual = _neto_nif(movimientos, nif, "actual")
        anterior = _neto_nif(movimientos, nif, "anterior")
        variacion = round(actual - anterior, 2)
        if variacion:
            filas.append(FilaFlujo(nif.etiqueta, variacion))
            total += variacion

    cuentas_capital = [m for m in movimientos if m.cuenta.clasificacion == Clasificacion.CAPITAL_CONTABLE]
    nombres_vistos: list[str] = []
    for m in cuentas_capital:
        if m.cuenta.nombre in nombres_vistos:
            continue
        nombres_vistos.append(m.cuenta.nombre)
        actual = round(sum(x.monto("actual") for x in cuentas_capital if x.cuenta.nombre == m.cuenta.nombre), 2)
        anterior = round(sum(x.monto("anterior") for x in cuentas_capital if x.cuenta.nombre == m.cuenta.nombre), 2)
        variacion = round(actual - anterior, 2)
        if variacion:
            filas.append(FilaFlujo(m.cuenta.nombre, variacion))
            total += variacion

    return filas, round(total, 2)


def _conciliar(
    movimientos: list[MovimientoESF], total_operacion: float, total_inversion: float, total_financiamiento: float,
) -> tuple[float, float, float, float, bool, float]:
    incremento = round(total_operacion + total_inversion + total_financiamiento, 2)
    efectivo_inicial = _neto_nif(movimientos, NIF.EQUIVALENTES_EFECTIVO, "anterior")
    efectivo_final_calculado = round(efectivo_inicial + incremento, 2)
    efectivo_final_real = _neto_nif(movimientos, NIF.EQUIVALENTES_EFECTIVO, "actual")
    diferencia = round(efectivo_final_calculado - efectivo_final_real, 2)
    return incremento, efectivo_inicial, efectivo_final_calculado, efectivo_final_real, abs(diferencia) < _TOLERANCIA, diferencia


# ---------------------------------------------------------------------------
# MÉTODO INDIRECTO
# ---------------------------------------------------------------------------

def generar_flujo_indirecto(movimientos_esf: list[MovimientoESF], utilidad_integral_actual: float) -> ResultadoFlujoEfectivo:
    filas_operacion = [FilaFlujo("Utilidad / Pérdida del ejercicio", round(utilidad_integral_actual, 2))]
    total_operacion = round(utilidad_integral_actual, 2)

    # Partidas virtuales: una fila por cada NIF que tenga cuenta complementaria
    for nif in [NIF.CUENTAS_POR_COBRAR, NIF.PROPIEDAD_PLANTA_EQUIPO, NIF.ACTIVOS_INTANGIBLES]:
        nombre, aumento = _aumento_complementaria(movimientos_esf, nif)
        if nombre and aumento:
            filas_operacion.append(FilaFlujo(f"(+) {nombre}", aumento))
            total_operacion = round(total_operacion + aumento, 2)

    # Variaciones de Activo Circulante (Operación) — excluye Equivalentes de Efectivo, usa saldo BRUTO
    for nif in [NIF.CUENTAS_POR_COBRAR, NIF.INVENTARIOS, NIF.PAGOS_ANTICIPADOS]:
        bruto_actual = _bruto_nif(movimientos_esf, nif, "actual")
        bruto_anterior = _bruto_nif(movimientos_esf, nif, "anterior")
        variacion = round(bruto_anterior - bruto_actual, 2)
        if variacion:
            filas_operacion.append(FilaFlujo(nif.etiqueta, variacion))
            total_operacion = round(total_operacion + variacion, 2)

    # Variaciones de Pasivo a Corto Plazo (Operación)
    for nif in NIFS_POR_CLASIFICACION[Clasificacion.PASIVO_CORTO_PLAZO]:
        actual = _neto_nif(movimientos_esf, nif, "actual")
        anterior = _neto_nif(movimientos_esf, nif, "anterior")
        variacion = round(actual - anterior, 2)
        if variacion:
            filas_operacion.append(FilaFlujo(nif.etiqueta, variacion))
            total_operacion = round(total_operacion + variacion, 2)

    # Inversión: Activo No Circulante, saldo BRUTO (la complementaria ya se contó como partida virtual)
    filas_inversion = []
    total_inversion = 0.0
    for nif in NIFS_POR_CLASIFICACION[Clasificacion.ACTIVO_NO_CIRCULANTE]:
        bruto_actual = _bruto_nif(movimientos_esf, nif, "actual")
        bruto_anterior = _bruto_nif(movimientos_esf, nif, "anterior")
        variacion = round(bruto_anterior - bruto_actual, 2)
        if variacion:
            filas_inversion.append(FilaFlujo(nif.etiqueta, variacion))
            total_inversion = round(total_inversion + variacion, 2)

    filas_financiamiento, total_financiamiento = _calcular_financiamiento(movimientos_esf)

    incremento, ef_inicial, ef_final_calc, ef_final_real, concilia, diferencia = _conciliar(
        movimientos_esf, total_operacion, total_inversion, total_financiamiento,
    )

    return ResultadoFlujoEfectivo(
        metodo="indirecto",
        filas_operacion=filas_operacion, total_operacion=total_operacion,
        filas_inversion=filas_inversion, total_inversion=total_inversion,
        filas_financiamiento=filas_financiamiento, total_financiamiento=total_financiamiento,
        incremento_efectivo=incremento, efectivo_inicial=ef_inicial,
        efectivo_final_calculado=ef_final_calc, efectivo_final_real=ef_final_real,
        concilia=concilia, diferencia_conciliacion=diferencia,
    )


# ---------------------------------------------------------------------------
# MÉTODO DIRECTO
# ---------------------------------------------------------------------------

_ETIQUETAS_DIRECTO_ACTIVO = {
    NIF.CUENTAS_POR_COBRAR: "Cobros a clientes",
    NIF.INVENTARIOS: "Pagos por inventario",
    NIF.PAGOS_ANTICIPADOS: "Pagos anticipados",
}
_ETIQUETAS_DIRECTO_PASIVO_CP = {
    NIF.CTAS_POR_PAGAR_PROVEEDORES: "Pago a proveedores",
    NIF.DOCUMENTOS_POR_PAGAR_CP: "Pago de documentos por pagar",
    NIF.CONTRIBUCIONES_POR_PAGAR: "Pago de impuestos y contribuciones",
    NIF.OTRAS_CTAS_POR_PAGAR: "Pago de otras cuentas por pagar",
}


def generar_flujo_directo(movimientos_esf: list[MovimientoESF], utilidad_integral_actual: float) -> ResultadoFlujoEfectivo:
    filas_operacion = [FilaFlujo("Utilidad / Pérdida del ejercicio", round(utilidad_integral_actual, 2))]
    total_operacion = round(utilidad_integral_actual, 2)

    # Sin partidas virtuales: la complementaria se netea directo en su cuenta de activo.
    for nif, etiqueta in _ETIQUETAS_DIRECTO_ACTIVO.items():
        neto_actual = _neto_nif(movimientos_esf, nif, "actual")
        neto_anterior = _neto_nif(movimientos_esf, nif, "anterior")
        variacion = round(neto_anterior - neto_actual, 2)
        if variacion:
            filas_operacion.append(FilaFlujo(etiqueta, variacion))
            total_operacion = round(total_operacion + variacion, 2)

    for nif, etiqueta in _ETIQUETAS_DIRECTO_PASIVO_CP.items():
        actual = _neto_nif(movimientos_esf, nif, "actual")
        anterior = _neto_nif(movimientos_esf, nif, "anterior")
        variacion = round(actual - anterior, 2)
        if variacion:
            filas_operacion.append(FilaFlujo(etiqueta, variacion))
            total_operacion = round(total_operacion + variacion, 2)

    filas_inversion = []
    total_inversion = 0.0
    for nif in NIFS_POR_CLASIFICACION[Clasificacion.ACTIVO_NO_CIRCULANTE]:
        neto_actual = _neto_nif(movimientos_esf, nif, "actual")
        neto_anterior = _neto_nif(movimientos_esf, nif, "anterior")
        variacion = round(neto_anterior - neto_actual, 2)
        if variacion:
            filas_inversion.append(FilaFlujo(nif.etiqueta, variacion))
            total_inversion = round(total_inversion + variacion, 2)

    filas_financiamiento, total_financiamiento = _calcular_financiamiento(movimientos_esf)

    incremento, ef_inicial, ef_final_calc, ef_final_real, concilia, diferencia = _conciliar(
        movimientos_esf, total_operacion, total_inversion, total_financiamiento,
    )

    return ResultadoFlujoEfectivo(
        metodo="directo",
        filas_operacion=filas_operacion, total_operacion=total_operacion,
        filas_inversion=filas_inversion, total_inversion=total_inversion,
        filas_financiamiento=filas_financiamiento, total_financiamiento=total_financiamiento,
        incremento_efectivo=incremento, efectivo_inicial=ef_inicial,
        efectivo_final_calculado=ef_final_calc, efectivo_final_real=ef_final_real,
        concilia=concilia, diferencia_conciliacion=diferencia,
    )


# ---------------------------------------------------------------------------
# PRUEBA MANUAL: escenario diseñado para reconciliar EXACTO ($0.00 diferencia)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from catalog import obtener_cuenta
    from engine import calcular_esf

    def mov(nombre: str, actual: float, anterior: float = 0.0) -> MovimientoESF:
        return MovimientoESF(cuenta=obtener_cuenta(nombre), monto_actual=actual, monto_anterior=anterior)

    # Escenario construido a mano para que Activo = Pasivo + Capital cuadre
    # en AMBOS años, y por lo tanto el Flujo de Efectivo debe reconciliar
    # exacto (es una consecuencia matemática directa, no una coincidencia).
    movimientos = [
        mov("Caja", actual=35000, anterior=20000),
        mov("Clientes", actual=25000, anterior=10000),
        mov("Edificios", actual=100000, anterior=100000),
        mov("Depreciación acumulada de...", actual=5000, anterior=0),
        mov("Proveedores", actual=30000, anterior=20000),
        mov("Capital social", actual=90000, anterior=90000),
        mov("Utilidades acumuladas", actual=20000, anterior=20000),
    ]
    utilidad_integral_actual = 15000.0

    # Primero, confirmar que el ESF cuadra en ambos años con este escenario.
    esf = calcular_esf(movimientos, utilidad_integral_actual=utilidad_integral_actual, utilidad_integral_anterior=0)
    print(f"ESF cuadrado (actual):   {esf.cuadrado_actual}  (Activo={esf.total_activo_actual}, P+C={esf.total_pasivo_mas_capital_actual})")
    print(f"ESF cuadrado (anterior): {esf.cuadrado_anterior}  (Activo={esf.total_activo_anterior}, P+C={esf.total_pasivo_mas_capital_anterior})")
    assert esf.cuadrado_actual and esf.cuadrado_anterior

    for metodo, generar in [("INDIRECTO", generar_flujo_indirecto), ("DIRECTO", generar_flujo_directo)]:
        print(f"\n=== MÉTODO {metodo} ===")
        r = generar(movimientos, utilidad_integral_actual)
        print("Actividades de Operación:")
        for f in r.filas_operacion:
            print(f"  {f.concepto:45s} {f.monto:>12,.2f}")
        print(f"  {'TOTAL OPERACIÓN':45s} {r.total_operacion:>12,.2f}")
        print("Actividades de Inversión:")
        for f in r.filas_inversion:
            print(f"  {f.concepto:45s} {f.monto:>12,.2f}")
        print(f"  {'TOTAL INVERSIÓN':45s} {r.total_inversion:>12,.2f}")
        print("Actividades de Financiamiento:")
        for f in r.filas_financiamiento:
            print(f"  {f.concepto:45s} {f.monto:>12,.2f}")
        print(f"  {'TOTAL FINANCIAMIENTO':45s} {r.total_financiamiento:>12,.2f}")
        print(f"\n  Incremento de efectivo:       {r.incremento_efectivo:,.2f}")
        print(f"  Efectivo inicial:             {r.efectivo_inicial:,.2f}")
        print(f"  Efectivo final (calculado):   {r.efectivo_final_calculado:,.2f}")
        print(f"  Efectivo final (real, Caja):  {r.efectivo_final_real:,.2f}")
        print(f"  ¿Concilia? {r.concilia}  (diferencia: {r.diferencia_conciliacion})")
        assert r.concilia, f"Método {metodo} NO reconcilió — revisar lógica"

    print("\nTODAS LAS ASERCIONES PASARON (ambos métodos reconcilian exacto).")
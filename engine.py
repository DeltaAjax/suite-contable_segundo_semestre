"""
engine.py — Motor de Cálculo Contable V3 (NIF)
Herramienta de Autoevaluación Financiera — Motor Contable NIF

Este módulo cubre, en este primer bloque de la V3:
  - calcular_eri(): cascada oficial del ERI (1° a 21°), sin cambios de
    fondo respecto a V2 — sigue siendo de un solo periodo.
  - calcular_esf(): Estado de Situación Financiera de 5 columnas
    (Concepto, Notas, Año Actual, Notas, Año Anterior), agrupado por NIF,
    restando las cuentas complementarias de activo a nivel de grupo NIF
    (tal como exige la especificación: "MENOS los saldos de las filas que
    además tengan Cuentas complementarias de activo").

Flujo de Efectivo y Estado de Cambios en Capital Contable se agregan en un
módulo posterior, una vez validado este bloque base.
"""

from dataclasses import dataclass

from catalog import (
    CuentaV3,
    Clasificacion,
    LineaERI,
    NIF,
    NIFS_CAPITAL_CONTRIBUIDO,
    NIFS_CAPITAL_GANADO,
    NIFS_POR_CLASIFICACION,
    SIGNO_LINEA_ERI,
)

_TOLERANCIA = 0.005  # tolerancia por redondeo de centavos


# ---------------------------------------------------------------------------
# 1. ENTRADA: MOVIMIENTOS CAPTURADOS POR EL ALUMNO
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MovimientoERI:
    """Renglón del ERI: un solo periodo (no hay comparativo año anterior)."""
    cuenta: CuentaV3
    monto: float

    @property
    def monto_con_signo(self) -> float:
        return self.monto * SIGNO_LINEA_ERI[self.cuenta.linea_eri]


@dataclass(frozen=True)
class MovimientoESF:
    """
    Renglón del balance: lleva saldo del año actual y, opcionalmente, del
    año anterior (0.0 si no se captura comparativo).
    """
    cuenta: CuentaV3
    monto_actual: float
    monto_anterior: float = 0.0

    def monto(self, anio: str) -> float:
        crudo = self.monto_actual if anio == "actual" else self.monto_anterior
        return crudo * self.cuenta.signo


# ---------------------------------------------------------------------------
# 2. SALIDA: RESULTADOS ESTRUCTURADOS
# ---------------------------------------------------------------------------

@dataclass
class ResultadoERI:
    ventas: float
    costo_ventas: float
    utilidad_bruta: float                # 3°

    gastos_venta: float
    gastos_administracion: float
    gastos_generales: float              # 6°

    utilidad_antes_otros: float          # 7°

    otros_productos: float
    otros_gastos: float
    neto_otros_productos_gastos: float   # 10°

    utilidad_operacion: float            # 11°

    productos_financieros: float
    gastos_financieros: float
    rif: float                           # 14°

    utilidad_antes_impuestos: float      # 15°

    isr: float
    ptu: float
    impuestos_utilidad: float            # 18°

    utilidad_neta: float                 # 19°

    ori: float
    utilidad_integral: float             # 21°


@dataclass
class RubroNIF:
    """Un renglón del ESF: un NIF con su saldo año actual y año anterior."""
    nif: NIF
    saldo_actual: float
    saldo_anterior: float


@dataclass
class ResultadoESF:
    """
    ESF de 5 columnas. Cada sección trae la lista de RubroNIF que la
    componen (para poder imprimir 'Cuentas por cobrar ... $X / $Y' línea
    por línea) más los totales de la sección, en ambos años.
    """
    activo_circulante: list[RubroNIF]
    total_activo_circulante_actual: float
    total_activo_circulante_anterior: float

    activo_no_circulante: list[RubroNIF]
    total_activo_no_circulante_actual: float
    total_activo_no_circulante_anterior: float

    total_activo_actual: float
    total_activo_anterior: float

    pasivo_corto_plazo: list[RubroNIF]
    total_pasivo_corto_plazo_actual: float
    total_pasivo_corto_plazo_anterior: float

    pasivo_largo_plazo: list[RubroNIF]
    total_pasivo_largo_plazo_actual: float
    total_pasivo_largo_plazo_anterior: float

    total_pasivo_actual: float
    total_pasivo_anterior: float

    capital_contribuido: list[RubroNIF]
    total_capital_contribuido_actual: float
    total_capital_contribuido_anterior: float

    capital_ganado: list[RubroNIF]
    total_capital_ganado_actual: float
    total_capital_ganado_anterior: float

    total_capital_contable_actual: float
    total_capital_contable_anterior: float

    total_pasivo_mas_capital_actual: float
    total_pasivo_mas_capital_anterior: float

    diferencia_actual: float
    diferencia_anterior: float
    cuadrado_actual: bool
    cuadrado_anterior: bool


# ---------------------------------------------------------------------------
# 3. CÁLCULO DEL ERI (idéntico en fondo a V2, cascada oficial 1° a 21°)
# ---------------------------------------------------------------------------

def _sumar_linea_eri(movimientos: list[MovimientoERI], linea: LineaERI) -> float:
    return round(sum(m.monto_con_signo for m in movimientos if m.cuenta.linea_eri == linea), 2)


def calcular_eri(movimientos: list[MovimientoERI]) -> ResultadoERI:
    ventas = _sumar_linea_eri(movimientos, LineaERI.VENTAS)
    costo_ventas = _sumar_linea_eri(movimientos, LineaERI.COSTO_VENTAS)
    utilidad_bruta = round(ventas + costo_ventas, 2)

    gastos_venta = _sumar_linea_eri(movimientos, LineaERI.GASTOS_VENTA)
    gastos_administracion = _sumar_linea_eri(movimientos, LineaERI.GASTOS_ADMINISTRACION)
    gastos_generales = round(gastos_venta + gastos_administracion, 2)

    utilidad_antes_otros = round(utilidad_bruta + gastos_generales, 2)

    otros_productos = _sumar_linea_eri(movimientos, LineaERI.OTROS_PRODUCTOS)
    otros_gastos = _sumar_linea_eri(movimientos, LineaERI.OTROS_GASTOS)
    neto_otros = round(otros_productos + otros_gastos, 2)

    utilidad_operacion = round(utilidad_antes_otros + neto_otros, 2)

    productos_financieros = _sumar_linea_eri(movimientos, LineaERI.PRODUCTOS_FINANCIEROS)
    gastos_financieros = _sumar_linea_eri(movimientos, LineaERI.GASTOS_FINANCIEROS)
    rif = round(productos_financieros + gastos_financieros, 2)

    utilidad_antes_impuestos = round(utilidad_operacion + rif, 2)

    isr = _sumar_linea_eri(movimientos, LineaERI.ISR)
    ptu = _sumar_linea_eri(movimientos, LineaERI.PTU)
    impuestos_utilidad = round(isr + ptu, 2)

    utilidad_neta = round(utilidad_antes_impuestos + impuestos_utilidad, 2)

    ori = _sumar_linea_eri(movimientos, LineaERI.ORI)
    utilidad_integral = round(utilidad_neta + ori, 2)

    return ResultadoERI(
        ventas=ventas, costo_ventas=costo_ventas, utilidad_bruta=utilidad_bruta,
        gastos_venta=gastos_venta, gastos_administracion=gastos_administracion,
        gastos_generales=gastos_generales, utilidad_antes_otros=utilidad_antes_otros,
        otros_productos=otros_productos, otros_gastos=otros_gastos,
        neto_otros_productos_gastos=neto_otros, utilidad_operacion=utilidad_operacion,
        productos_financieros=productos_financieros, gastos_financieros=gastos_financieros,
        rif=rif, utilidad_antes_impuestos=utilidad_antes_impuestos,
        isr=isr, ptu=ptu, impuestos_utilidad=impuestos_utilidad,
        utilidad_neta=utilidad_neta, ori=ori, utilidad_integral=utilidad_integral,
    )


# ---------------------------------------------------------------------------
# 4. CÁLCULO DEL ESF DE 5 COLUMNAS (agrupado por NIF, ambos años)
# ---------------------------------------------------------------------------

def _saldo_nif(movimientos: list[MovimientoESF], nif: NIF, anio: str) -> float:
    """
    Suma todas las cuentas normales de ese NIF y resta las complementarias
    del mismo NIF, tal como pide la especificación (cada cuenta ya trae su
    signo correcto vía CuentaV3.signo, así que aquí solo se suma).
    """
    return round(sum(m.monto(anio) for m in movimientos if m.cuenta.nif == nif), 2)


def _rubros_de(movimientos: list[MovimientoESF], nifs: list[NIF]) -> list[RubroNIF]:
    rubros = []
    for nif in nifs:
        actual = _saldo_nif(movimientos, nif, "actual")
        anterior = _saldo_nif(movimientos, nif, "anterior")
        if actual != 0 or anterior != 0:
            rubros.append(RubroNIF(nif=nif, saldo_actual=actual, saldo_anterior=anterior))
    return rubros


def calcular_esf(
    movimientos: list[MovimientoESF],
    utilidad_integral_actual: float = 0.0,
    utilidad_integral_anterior: float = 0.0,
) -> ResultadoESF:
    """
    utilidad_integral_actual / anterior: viene de calcular_eri().utilidad_integral
    de cada periodo, y se suma dentro de Capital Ganado (fila 'Utilidades
    acumuladas' conceptual), tal como indica la Guía General:
    'Consistencia del Resultado Integral: coincide con Capital Contable'.
    """
    activo_circulante = _rubros_de(movimientos, NIFS_POR_CLASIFICACION[Clasificacion.ACTIVO_CIRCULANTE])
    total_ac_actual = round(sum(r.saldo_actual for r in activo_circulante), 2)
    total_ac_anterior = round(sum(r.saldo_anterior for r in activo_circulante), 2)

    activo_no_circulante = _rubros_de(movimientos, NIFS_POR_CLASIFICACION[Clasificacion.ACTIVO_NO_CIRCULANTE])
    total_anc_actual = round(sum(r.saldo_actual for r in activo_no_circulante), 2)
    total_anc_anterior = round(sum(r.saldo_anterior for r in activo_no_circulante), 2)

    total_activo_actual = round(total_ac_actual + total_anc_actual, 2)
    total_activo_anterior = round(total_ac_anterior + total_anc_anterior, 2)

    pasivo_cp = _rubros_de(movimientos, NIFS_POR_CLASIFICACION[Clasificacion.PASIVO_CORTO_PLAZO])
    total_pcp_actual = round(sum(r.saldo_actual for r in pasivo_cp), 2)
    total_pcp_anterior = round(sum(r.saldo_anterior for r in pasivo_cp), 2)

    pasivo_lp = _rubros_de(movimientos, NIFS_POR_CLASIFICACION[Clasificacion.PASIVO_LARGO_PLAZO])
    total_plp_actual = round(sum(r.saldo_actual for r in pasivo_lp), 2)
    total_plp_anterior = round(sum(r.saldo_anterior for r in pasivo_lp), 2)

    total_pasivo_actual = round(total_pcp_actual + total_plp_actual, 2)
    total_pasivo_anterior = round(total_pcp_anterior + total_plp_anterior, 2)

    capital_contribuido = _rubros_de(movimientos, NIFS_CAPITAL_CONTRIBUIDO)
    total_cc_actual = round(sum(r.saldo_actual for r in capital_contribuido), 2)
    total_cc_anterior = round(sum(r.saldo_anterior for r in capital_contribuido), 2)

    capital_ganado_rubros = _rubros_de(movimientos, NIFS_CAPITAL_GANADO)
    total_cg_actual = round(sum(r.saldo_actual for r in capital_ganado_rubros) + utilidad_integral_actual, 2)
    total_cg_anterior = round(sum(r.saldo_anterior for r in capital_ganado_rubros) + utilidad_integral_anterior, 2)

    total_capital_actual = round(total_cc_actual + total_cg_actual, 2)
    total_capital_anterior = round(total_cc_anterior + total_cg_anterior, 2)

    total_pasivo_mas_capital_actual = round(total_pasivo_actual + total_capital_actual, 2)
    total_pasivo_mas_capital_anterior = round(total_pasivo_anterior + total_capital_anterior, 2)

    diferencia_actual = round(total_activo_actual - total_pasivo_mas_capital_actual, 2)
    diferencia_anterior = round(total_activo_anterior - total_pasivo_mas_capital_anterior, 2)

    return ResultadoESF(
        activo_circulante=activo_circulante,
        total_activo_circulante_actual=total_ac_actual,
        total_activo_circulante_anterior=total_ac_anterior,
        activo_no_circulante=activo_no_circulante,
        total_activo_no_circulante_actual=total_anc_actual,
        total_activo_no_circulante_anterior=total_anc_anterior,
        total_activo_actual=total_activo_actual,
        total_activo_anterior=total_activo_anterior,
        pasivo_corto_plazo=pasivo_cp,
        total_pasivo_corto_plazo_actual=total_pcp_actual,
        total_pasivo_corto_plazo_anterior=total_pcp_anterior,
        pasivo_largo_plazo=pasivo_lp,
        total_pasivo_largo_plazo_actual=total_plp_actual,
        total_pasivo_largo_plazo_anterior=total_plp_anterior,
        total_pasivo_actual=total_pasivo_actual,
        total_pasivo_anterior=total_pasivo_anterior,
        capital_contribuido=capital_contribuido,
        total_capital_contribuido_actual=total_cc_actual,
        total_capital_contribuido_anterior=total_cc_anterior,
        capital_ganado=capital_ganado_rubros,
        total_capital_ganado_actual=total_cg_actual,
        total_capital_ganado_anterior=total_cg_anterior,
        total_capital_contable_actual=total_capital_actual,
        total_capital_contable_anterior=total_capital_anterior,
        total_pasivo_mas_capital_actual=total_pasivo_mas_capital_actual,
        total_pasivo_mas_capital_anterior=total_pasivo_mas_capital_anterior,
        diferencia_actual=diferencia_actual,
        diferencia_anterior=diferencia_anterior,
        cuadrado_actual=abs(diferencia_actual) < _TOLERANCIA,
        cuadrado_anterior=abs(diferencia_anterior) < _TOLERANCIA,
    )


def formatear_moneda(monto: float) -> str:
    signo = "-" if monto < 0 else ""
    return f"{signo}${abs(monto):,.2f}"


def generar_banner_verificacion(resultado_esf: ResultadoESF) -> str:
    """Banner del año actual (el que interesa para la captura en curso)."""
    if resultado_esf.cuadrado_actual:
        return f"✓ BALANCE CUADRADO EXACTAMENTE — Diferencia: {formatear_moneda(0.0)}"
    return (
        "✕ DESBALANCE DETECTADO — Diferencia Monetaria Exacta: "
        f"{formatear_moneda(abs(resultado_esf.diferencia_actual))}"
    )


# ---------------------------------------------------------------------------
# 5. PRUEBA MANUAL RÁPIDA
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from catalog import obtener_cuenta, obtener_cuenta_por_linea_eri

    def mov_eri(linea: LineaERI, monto: float) -> MovimientoERI:
        return MovimientoERI(cuenta=obtener_cuenta_por_linea_eri(linea), monto=monto)

    def mov_esf(nombre: str, actual: float, anterior: float = 0.0) -> MovimientoESF:
        cuenta = obtener_cuenta(nombre)
        return MovimientoESF(cuenta=cuenta, monto_actual=actual, monto_anterior=anterior)

    # --- ERI ---
    eri = calcular_eri([
        mov_eri(LineaERI.VENTAS, 200000),
        mov_eri(LineaERI.COSTO_VENTAS, 80000),
        mov_eri(LineaERI.GASTOS_VENTA, 20000),
        mov_eri(LineaERI.GASTOS_ADMINISTRACION, 30000),
        mov_eri(LineaERI.ISR, 15000),
        mov_eri(LineaERI.PTU, 5000),
    ])
    print("Utilidad Bruta (3°):", eri.utilidad_bruta, "(esperado 120000)")
    print("Utilidad Neta (19°):", eri.utilidad_neta, "(esperado 50000)")
    print("Utilidad Integral (21°):", eri.utilidad_integral, "(esperado 50000, sin ORI)")

    # --- ESF con complementaria y dos años ---
    movimientos_esf = [
        mov_esf("Caja", actual=50000, anterior=30000),
        mov_esf("Clientes", actual=80000, anterior=60000),
        mov_esf("Estimación de cobros dudosos", actual=5000, anterior=3000),
        mov_esf("Edificios", actual=150000, anterior=150000),
        mov_esf("Depreciación acumulada de...", actual=20000, anterior=10000),
        mov_esf("Proveedores", actual=40000, anterior=35000),
        mov_esf("Capital social", actual=150000, anterior=150000),
        mov_esf("Utilidades acumuladas", actual=15000, anterior=2000),
    ]
    esf = calcular_esf(movimientos_esf, utilidad_integral_actual=eri.utilidad_integral, utilidad_integral_anterior=0)

    print("\nCuentas por Cobrar neto (actual):", [
        (r.nif.etiqueta, r.saldo_actual) for r in esf.activo_circulante if r.nif.codigo == "C3"
    ], "(esperado: 80000 - 5000 = 75000)")
    print("Total Activo actual:", esf.total_activo_actual)
    print("Total Pasivo + Capital actual:", esf.total_pasivo_mas_capital_actual)
    print(generar_banner_verificacion(esf))
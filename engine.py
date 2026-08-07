"""
engine.py — Motor de Cálculo Contable Unificado
Herramienta de Autoevaluación Financiera (FACPYA)

Consolida `engine_v2_1er_semestre.py` y `engine_v3_avanzado.py` en un único
motor que importa del catálogo unificado (`catalog.py`) y resuelve tanto el:

  - "Modo Simplificado (1er Semestre)": ERI de un solo periodo + ESF de un
    solo periodo agrupado por las 6 categorías del ESF, con "Práctica
    Aislada" (inyectar utilidad/pérdida sin pasar por el ERI).

  - "Modo Avanzado (NIF V3)": mismo ERI (la cascada 1°-21° no cambia entre
    versiones) + ESF comparativo de 5 columnas (Concepto, Notas, Año Actual,
    Notas, Año Anterior) agrupado por agrupador NIF (C1, C3, C4...), restando
    a nivel de NIF las cuentas complementarias de activo.

Este módulo NO conoce nada de interfaz; sólo recibe datos estructurados y
regresa dataclasses de resultado, listos para que la UI (NiceGUI, etc.) los
pinte.

Nota de diseño clave: en `catalog.py`, cada `Cuenta` ya trae sincronizados
`comportamiento` (suma/resta) y `signo` (+1/-1) — `Cuenta.signo_num()` es la
única fuente de verdad para "cómo afecta esta cuenta a su grupo", y es lo
que usan AMBOS motores aquí. Esto es lo que permite que `MovimientoERI` (V3)
y `MovimientoCuenta` (V2) se conviertan, en la práctica, en la misma
estructura de datos.
"""

from dataclasses import dataclass

from catalog import (
    Clasificacion,
    Cuenta,
    LineaERI,
    NIF,
    NIFS_CAPITAL_CONTRIBUIDO,
    NIFS_CAPITAL_GANADO,
    NIFS_POR_CLASIFICACION,
    SeccionCapital,
    TipoEstado,
)

_TOLERANCIA = 0.005  # tolerancia por redondeo de centavos


# ---------------------------------------------------------------------------
# 1. ENTRADA: MOVIMIENTOS CAPTURADOS POR EL ALUMNO
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MovimientoCuenta:
    """
    Renglón de un solo periodo: una cuenta (predeterminada, personalizada, o
    dinámica) con su saldo. El saldo siempre se captura en positivo; el
    motor aplica el signo vía `cuenta.signo_num()`.

    Se usa tanto para movimientos del ERI (ambos modos: el ERI siempre es de
    un solo periodo) como para el ESF del modo simplificado de 1er semestre.

    Nota: el motor NO valida el signo de `monto`. Para todas las cuentas, la
    UI debe capturar montos en positivo (min=0) y dejar que el motor aplique
    el signo. La única excepción es ORI (Otros Resultados Integrales), que sí
    admite valores negativos capturados directamente, ya que puede
    representar una pérdida integral.
    """
    cuenta: Cuenta
    monto: float

    @property
    def monto_con_signo(self) -> float:
        return self.monto * self.cuenta.signo_num()


# Alias de compatibilidad: en el motor avanzado (NIF V3) este mismo renglón
# se llamaba `MovimientoERI`. Es la misma estructura (un solo periodo, un
# monto), así que se conserva el nombre como alias en vez de duplicar código.
MovimientoERI = MovimientoCuenta


@dataclass(frozen=True)
class MovimientoESF:
    """
    Renglón del balance del modo avanzado (NIF V3): lleva saldo del año
    actual y, opcionalmente, del año anterior (0.0 si no se captura
    comparativo). Es lo que dispara el cálculo del ESF de 5 columnas en
    `calcular_esf()`.
    """
    cuenta: Cuenta
    monto_actual: float
    monto_anterior: float = 0.0

    def monto(self, anio: str) -> float:
        crudo = self.monto_actual if anio == "actual" else self.monto_anterior
        return crudo * self.cuenta.signo_num()


# ---------------------------------------------------------------------------
# 2. SALIDA: RESULTADOS ESTRUCTURADOS
# ---------------------------------------------------------------------------

@dataclass
class ResultadoERI:
    """Cascada completa del Estado de Resultado Integral, líneas 1° a 21°. Común a ambos modos."""
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
    rif: float                           # 14°  Resultado Integral de Financiamiento

    utilidad_antes_impuestos: float      # 15°

    isr: float
    ptu: float
    impuestos_utilidad: float            # 18°

    utilidad_neta: float                 # 19°

    ori: float                           # 20°
    utilidad_integral: float             # 21°


@dataclass
class RubroNIF:
    """Un renglón del ESF avanzado: un NIF con su saldo año actual y año anterior."""
    nif: NIF
    saldo_actual: float
    saldo_anterior: float


@dataclass
class ResultadoESF:
    """
    ESF de 5 columnas (modo avanzado NIF V3). Cada sección trae la lista de
    RubroNIF que la componen (para poder imprimir 'Cuentas por cobrar ...
    $X / $Y' línea por línea) más los totales de la sección, en ambos años.
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


@dataclass
class ResultadoESFSimple:
    """
    Totales del ESF de un solo periodo (modo simplificado de 1er semestre),
    sin desglose por NIF. Verifica igualmente la ecuación contable
    Activo = Pasivo + Capital.
    """
    activo_circulante: float
    activo_no_circulante: float
    total_activo: float

    pasivo_corto_plazo: float
    pasivo_largo_plazo: float
    total_pasivo: float

    capital_contribuido: float
    capital_ganado: float          # ya incluye la utilidad/pérdida del ejercicio, si se proporcionó
    total_capital_contable: float

    total_pasivo_mas_capital: float
    diferencia: float
    cuadrado: bool


# ---------------------------------------------------------------------------
# 3. CÁLCULO DEL ERI (cascada rígida, plantilla oficial — 1 sola versión)
# ---------------------------------------------------------------------------

def _sumar_linea_eri(movimientos: list[MovimientoCuenta], linea: LineaERI) -> float:
    return round(
        sum(m.monto_con_signo for m in movimientos if m.cuenta.linea_eri == linea),
        2,
    )


def calcular_eri(movimientos: list[MovimientoCuenta]) -> ResultadoERI:
    """
    Ejecuta la cascada oficial del ERI, línea por línea, tal como la
    plantilla guía estructurada (idéntica en ambos modos: el ERI siempre es
    de un solo periodo, con o sin desglose NIF en el balance):

      1-2   Ventas − Costo de Ventas          = 3°  Utilidad/Pérdida Bruta
      4-5   Gtos. Venta + Gtos. Admón.        = 6°  Gastos Generales
      3-6   Utilidad Bruta − Gastos Generales = 7°  Utilidad A.O.P.G.
      8-9   Otros Productos − Otros Gastos    = 10° Neto Otros Prod./Gtos.
      7+10  Utilidad A.O.P.G. + Neto          = 11° Utilidad en Operación
      12-13 Prod. Fin. − Gtos. Fin.           = 14° RIF
      11+14 Utilidad Operación + RIF          = 15° Utilidad Antes de Impuestos
      16+17 ISR + PTU                         = 18° Impuestos a la Utilidad
      15-18 Utilidad Antes Imp. − Impuestos   = 19° Utilidad/Pérdida Neta
      19+20 Utilidad Neta + ORI               = 21° Utilidad/Pérdida Integral

    Acepta indistintamente `MovimientoCuenta` o su alias `MovimientoERI`
    (son la misma estructura), ya que ambos exponen `.cuenta.linea_eri` y
    `.monto_con_signo`.
    """
    ventas = _sumar_linea_eri(movimientos, LineaERI.VENTAS)
    costo_ventas = _sumar_linea_eri(movimientos, LineaERI.COSTO_VENTAS)
    utilidad_bruta = round(ventas + costo_ventas, 2)                          # 3°

    gastos_venta = _sumar_linea_eri(movimientos, LineaERI.GASTOS_VENTA)
    gastos_administracion = _sumar_linea_eri(movimientos, LineaERI.GASTOS_ADMINISTRACION)
    gastos_generales = round(gastos_venta + gastos_administracion, 2)          # 6°

    utilidad_antes_otros = round(utilidad_bruta + gastos_generales, 2)         # 7°

    otros_productos = _sumar_linea_eri(movimientos, LineaERI.OTROS_PRODUCTOS)
    otros_gastos = _sumar_linea_eri(movimientos, LineaERI.OTROS_GASTOS)
    neto_otros = round(otros_productos + otros_gastos, 2)                      # 10°

    utilidad_operacion = round(utilidad_antes_otros + neto_otros, 2)           # 11°

    productos_financieros = _sumar_linea_eri(movimientos, LineaERI.PRODUCTOS_FINANCIEROS)
    gastos_financieros = _sumar_linea_eri(movimientos, LineaERI.GASTOS_FINANCIEROS)
    rif = round(productos_financieros + gastos_financieros, 2)                 # 14°

    utilidad_antes_impuestos = round(utilidad_operacion + rif, 2)              # 15°

    isr = _sumar_linea_eri(movimientos, LineaERI.ISR)
    ptu = _sumar_linea_eri(movimientos, LineaERI.PTU)
    impuestos_utilidad = round(isr + ptu, 2)                                   # 18°

    utilidad_neta = round(utilidad_antes_impuestos + impuestos_utilidad, 2)    # 19°

    ori = _sumar_linea_eri(movimientos, LineaERI.ORI)
    utilidad_integral = round(utilidad_neta + ori, 2)                          # 21°

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
# 4a. CÁLCULO DEL ESF — MODO SIMPLIFICADO (1 periodo, agrupado por clasificación)
# ---------------------------------------------------------------------------

def _sumar_clasificacion_simple(movimientos: list[MovimientoCuenta], clasificacion: Clasificacion) -> float:
    """Suma cuentas de balance (ESF) de una clasificación dada, con signo ya aplicado."""
    return round(
        sum(
            m.monto_con_signo for m in movimientos
            if m.cuenta.tipo == TipoEstado.ESF and m.cuenta.clasificacion == clasificacion
        ),
        2,
    )


def _sumar_capital_simple(movimientos: list[MovimientoCuenta], contribuido: bool) -> float:
    """
    Suma la porción de Capital Contable correspondiente. `contribuido=True`
    suma sólo Capital Contribuido; `contribuido=False` suma Capital Ganado
    (Utilidades + Reservas), replicando el agrupador de 6 categorías del
    formulario de 1er semestre.
    """
    def _pertenece(cuenta: Cuenta) -> bool:
        if cuenta.clasificacion != Clasificacion.CAPITAL_CONTABLE:
            return False
        es_contribuido = cuenta.seccion_capital == SeccionCapital.CAPITAL_CONTRIBUIDO
        return es_contribuido if contribuido else not es_contribuido

    return round(sum(m.monto_con_signo for m in movimientos if _pertenece(m.cuenta)), 2)


def _calcular_esf_simple(
    movimientos: list[MovimientoCuenta],
    resultado_del_ejercicio: float,
) -> ResultadoESFSimple:
    activo_circulante = _sumar_clasificacion_simple(movimientos, Clasificacion.ACTIVO_CIRCULANTE)
    activo_no_circulante = _sumar_clasificacion_simple(movimientos, Clasificacion.ACTIVO_NO_CIRCULANTE)
    total_activo = round(activo_circulante + activo_no_circulante, 2)

    pasivo_corto_plazo = _sumar_clasificacion_simple(movimientos, Clasificacion.PASIVO_CORTO_PLAZO)
    pasivo_largo_plazo = _sumar_clasificacion_simple(movimientos, Clasificacion.PASIVO_LARGO_PLAZO)
    total_pasivo = round(pasivo_corto_plazo + pasivo_largo_plazo, 2)

    capital_contribuido = _sumar_capital_simple(movimientos, contribuido=True)
    capital_ganado_base = _sumar_capital_simple(movimientos, contribuido=False)
    capital_ganado = round(capital_ganado_base + resultado_del_ejercicio, 2)
    total_capital_contable = round(capital_contribuido + capital_ganado, 2)

    total_pasivo_mas_capital = round(total_pasivo + total_capital_contable, 2)
    diferencia = round(total_activo - total_pasivo_mas_capital, 2)

    return ResultadoESFSimple(
        activo_circulante=activo_circulante,
        activo_no_circulante=activo_no_circulante,
        total_activo=total_activo,
        pasivo_corto_plazo=pasivo_corto_plazo,
        pasivo_largo_plazo=pasivo_largo_plazo,
        total_pasivo=total_pasivo,
        capital_contribuido=capital_contribuido,
        capital_ganado=capital_ganado,
        total_capital_contable=total_capital_contable,
        total_pasivo_mas_capital=total_pasivo_mas_capital,
        diferencia=diferencia,
        cuadrado=abs(diferencia) < _TOLERANCIA,
    )


# ---------------------------------------------------------------------------
# 4b. CÁLCULO DEL ESF — MODO AVANZADO (5 columnas, agrupado por NIF)
# ---------------------------------------------------------------------------

def _saldo_nif(movimientos: list[MovimientoESF], nif: NIF, anio: str) -> float:
    """
    Suma todas las cuentas de ese NIF (las complementarias ya restan, porque
    cada `Cuenta` trae su signo correcto vía `signo_num()`, aplicado dentro
    de `MovimientoESF.monto()`).
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


def _calcular_esf_comparativo(
    movimientos: list[MovimientoESF],
    utilidad_integral_actual: float,
    utilidad_integral_anterior: float,
) -> ResultadoESF:
    """
    utilidad_integral_actual / anterior: viene de calcular_eri().utilidad_integral
    de cada periodo, y se suma dentro de Capital Ganado (fila 'Utilidades
    acumuladas' conceptual), tal como indica la Guía General: 'Consistencia
    del Resultado Integral: coincide con Capital Contable'.
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


# ---------------------------------------------------------------------------
# 4c. FUNCIÓN VERSÁTIL ÚNICA: calcular_esf()
# ---------------------------------------------------------------------------

def calcular_esf(
    movimientos: "list[MovimientoESF] | list[MovimientoCuenta]",
    resultado_del_ejercicio: float = 0.0,
    resultado_del_ejercicio_anterior: float = 0.0,
) -> "ResultadoESF | ResultadoESFSimple":
    """
    Función versátil para ambos modos:

      - Si `movimientos` es una lista de `MovimientoESF` (traen
        monto_actual/monto_anterior), genera el ESF comparativo de 5
        columnas agrupado por NIF (modo avanzado) y regresa `ResultadoESF`.
      - Si `movimientos` es una lista de `MovimientoCuenta` (traen un solo
        monto), genera el balance simple de un solo periodo agrupado por
        clasificación (modo simplificado) y regresa `ResultadoESFSimple`.
      - Una lista vacía se resuelve como modo simplificado (no hay forma de
        distinguir el modo sin movimientos; el balance simple con todo en
        cero es el resultado más seguro).

    En ambos casos se puede inyectar el resultado del ejercicio (Utilidad o
    Pérdida, Neta o Integral según el modo) dentro del Capital Ganado:
    `resultado_del_ejercicio` es el año actual y, sólo aplica en modo
    avanzado, `resultado_del_ejercicio_anterior` es el año anterior.
    """
    if movimientos and isinstance(movimientos[0], MovimientoESF):
        return _calcular_esf_comparativo(
            movimientos,  # type: ignore[arg-type]
            utilidad_integral_actual=resultado_del_ejercicio,
            utilidad_integral_anterior=resultado_del_ejercicio_anterior,
        )
    return _calcular_esf_simple(movimientos, resultado_del_ejercicio=resultado_del_ejercicio)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5. FLUJO INTEGRAL (ERI -> ESF) Y PRÁCTICA AISLADA
# ---------------------------------------------------------------------------

def resolver_ejercicio_integral(
    movimientos_eri: list[MovimientoCuenta],
    movimientos_esf: "list[MovimientoESF] | list[MovimientoCuenta]",
    resultado_del_ejercicio_anterior: float = 0.0,
) -> "tuple[ResultadoERI, ResultadoESF | ResultadoESFSimple]":
    """
    Modo "Ejercicio Integral": calcula el ERI y usa su Utilidad/Pérdida
    Integral (21°) como resultado del ejercicio dentro del Capital Ganado
    del ESF. Funciona tanto con `movimientos_esf` de un solo periodo (modo
    simplificado) como comparativos (modo avanzado); en este último caso,
    `resultado_del_ejercicio_anterior` permite inyectar la utilidad integral
    del año anterior si también se resolvió su ERI.
    """
    resultado_eri = calcular_eri(movimientos_eri)
    resultado_esf = calcular_esf(
        movimientos_esf,
        resultado_del_ejercicio=resultado_eri.utilidad_integral,
        resultado_del_ejercicio_anterior=resultado_del_ejercicio_anterior,
    )
    return resultado_eri, resultado_esf


def resolver_practica_aislada(
    movimientos_esf: "list[MovimientoESF] | list[MovimientoCuenta]",
    utilidad_o_perdida: float,
) -> "ResultadoESF | ResultadoESFSimple":
    """
    Modo "Práctica Aislada": exclusiva de Balance General. El alumno captura
    la Utilidad (positiva) o Pérdida (negativa) directamente, sin resolver
    la cascada del ERI. Válido en ambos modos (simplificado y avanzado).
    """
    return calcular_esf(movimientos_esf, resultado_del_ejercicio=utilidad_o_perdida)


# ---------------------------------------------------------------------------
# 6. HELPERS DE PRESENTACIÓN
# ---------------------------------------------------------------------------

def formatear_moneda(monto: float) -> str:
    """Formatea un monto como moneda MXN: $1,250.00 / -$1,250.00"""
    signo = "-" if monto < 0 else ""
    return f"{signo}${abs(monto):,.2f}"


def generar_banner_verificacion(resultado_esf: "ResultadoESF | ResultadoESFSimple") -> str:
    """
    Genera el texto del banner dinámico, tal como los ejemplos oficiales:
      ✓ BALANCE CUADRADO EXACTAMENTE — Diferencia: $0.00
      ✕ DESBALANCE DETECTADO — Diferencia Monetaria Exacta: $1,250.00

    Funciona con ambos tipos de resultado: en el modo avanzado (`ResultadoESF`,
    5 columnas) se reporta el año actual, que es el que interesa para la
    captura en curso.
    """
    if isinstance(resultado_esf, ResultadoESF):
        cuadrado = resultado_esf.cuadrado_actual
        diferencia = resultado_esf.diferencia_actual
    else:
        cuadrado = resultado_esf.cuadrado
        diferencia = resultado_esf.diferencia

    if cuadrado:
        return f"✓ BALANCE CUADRADO EXACTAMENTE — Diferencia: {formatear_moneda(0.0)}"
    return (
        "✕ DESBALANCE DETECTADO — Diferencia Monetaria Exacta: "
        f"{formatear_moneda(abs(diferencia))}"
    )


# ---------------------------------------------------------------------------
# 7. PRUEBAS MANUALES RÁPIDAS
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from catalog import obtener_cuenta, obtener_cuenta_por_linea_eri, crear_cuenta_personalizada

    def mov(nombre: str, monto: float) -> MovimientoCuenta:
        cuenta = obtener_cuenta(nombre)
        if cuenta is None:
            raise ValueError(f"Cuenta no encontrada en catálogo: {nombre}")
        return MovimientoCuenta(cuenta=cuenta, monto=monto)

    def mov_eri(linea: LineaERI, monto: float) -> MovimientoERI:
        return MovimientoERI(cuenta=obtener_cuenta_por_linea_eri(linea), monto=monto)

    def mov_esf(nombre: str, actual: float, anterior: float = 0.0) -> MovimientoESF:
        cuenta = obtener_cuenta(nombre)
        return MovimientoESF(cuenta=cuenta, monto_actual=actual, monto_anterior=anterior)

    print("=" * 70)
    print("PRUEBA 1 — ERI (misma cascada, ambos modos)")
    print("=" * 70)
    movimientos_eri_avanzado = [
        mov("Ventas", 200000),
        mov("Costo de venta", 80000),
        mov("Gasto de venta", 20000),
        mov("Gasto de administración", 30000),
        mov("ISR", 15000),
        mov("PTU", 5000),
    ]
    eri = calcular_eri(movimientos_eri_avanzado)
    assert eri.utilidad_bruta == 120000, eri.utilidad_bruta
    assert eri.utilidad_neta == 50000, eri.utilidad_neta
    assert eri.utilidad_integral == 50000, eri.utilidad_integral
    print("Utilidad Bruta (3°):", eri.utilidad_bruta, "(esperado 120000) OK")
    print("Utilidad Neta (19°):", eri.utilidad_neta, "(esperado 50000) OK")
    print("Utilidad Integral (21°):", eri.utilidad_integral, "(esperado 50000, sin ORI) OK")

    print("\n" + "=" * 70)
    print("PRUEBA 2 — ESF MODO SIMPLIFICADO (1er semestre, 1 periodo)")
    print("=" * 70)
    movimientos_eri_simple = [
        mov("Ventas", 100000),
        mov("Costo de venta", 40000),
        mov("Gasto de venta", 10000),
        mov("Gasto de administración", 15000),
        mov("Otros productos", 2000),
        mov("Otros gastos", 500),
        mov("Productos financieros", 1000),
        mov("Gastos financieros", 3000),
        mov("ISR", 8000),
        mov("PTU", 2000),
    ]
    eri_simple = calcular_eri(movimientos_eri_simple)

    movimientos_esf_simple = [
        mov("Caja", 20000),
        mov("Bancos", 30000),
        mov("Clientes", 15000),
        mov("Edificios", 100000),
        mov("Proveedores", 25000),
        mov("Capital social", 90000),
    ]
    esf_simple = calcular_esf(movimientos_esf_simple, resultado_del_ejercicio=eri_simple.utilidad_integral)
    assert isinstance(esf_simple, ResultadoESFSimple)
    print("Total Activo:", esf_simple.total_activo)
    print("Total Pasivo + Capital:", esf_simple.total_pasivo_mas_capital)
    print(generar_banner_verificacion(esf_simple))
    # Nota: esta balanza de prueba es ilustrativa (heredada del motor V2
    # original) y no fue construida para cuadrar exactamente; lo que se
    # verifica aquí es que el cálculo sea determinístico y consistente
    # entre las distintas rutas de entrada, no que el banner diga "cuadrado".

    # Vía resolver_ejercicio_integral (atajo ERI -> ESF) — debe dar el mismo resultado
    eri2, esf2 = resolver_ejercicio_integral(movimientos_eri_simple, movimientos_esf_simple)
    assert esf2 == esf_simple, "resolver_ejercicio_integral debe coincidir con el cálculo manual"

    # Vía resolver_practica_aislada (sin ERI): si se inyecta la utilidad
    # exacta que hace falta para cuadrar, el banner debe confirmarlo.
    faltante_para_cuadrar = round(
        esf_simple.total_activo - esf_simple.total_pasivo - esf_simple.capital_contribuido
        - (esf_simple.capital_ganado - eri_simple.utilidad_integral),
        2,
    )
    esf_aislada = resolver_practica_aislada(movimientos_esf_simple, utilidad_o_perdida=faltante_para_cuadrar)
    assert isinstance(esf_aislada, ResultadoESFSimple)
    assert esf_aislada.cuadrado, "Con la utilidad exacta inyectada, la práctica aislada debe cuadrar"
    print("Práctica aislada (utilidad ajustada para cuadrar) — cuadrado:", esf_aislada.cuadrado)

    # Cuenta personalizada del modo simplificado
    cuenta_custom = crear_cuenta_personalizada(
        nombre="Marcas y patentes", categoria_esf="Activo No Circulante", comportamiento="suma"
    )
    mov_custom = MovimientoCuenta(cuenta=cuenta_custom, monto=5000)
    print("Cuenta personalizada:", mov_custom.cuenta.nombre, "-> monto con signo:", mov_custom.monto_con_signo)
    assert mov_custom.monto_con_signo == 5000

    print("\n" + "=" * 70)
    print("PRUEBA 3 — ESF MODO AVANZADO (NIF V3, comparativo 5 columnas)")
    print("=" * 70)
    movimientos_esf_avanzado = [
        mov_esf("Caja", actual=50000, anterior=30000),
        mov_esf("Clientes", actual=80000, anterior=60000),
        mov_esf("Estimación de cobros dudosos", actual=5000, anterior=3000),
        mov_esf("Edificios", actual=150000, anterior=150000),
        mov_esf("Depreciación acumulada de...", actual=20000, anterior=10000),
        mov_esf("Proveedores", actual=40000, anterior=35000),
        mov_esf("Capital social", actual=150000, anterior=150000),
        mov_esf("Utilidades acumuladas", actual=15000, anterior=2000),
    ]
    esf_avanzado = calcular_esf(
        movimientos_esf_avanzado,
        resultado_del_ejercicio=eri.utilidad_integral,
        resultado_del_ejercicio_anterior=0,
    )
    assert isinstance(esf_avanzado, ResultadoESF)

    cxc_actual = [
        (r.nif.etiqueta, r.saldo_actual) for r in esf_avanzado.activo_circulante if r.nif.codigo == "C3"
    ]
    print("Cuentas por Cobrar neto (actual):", cxc_actual, "(esperado: 80000 - 5000 = 75000)")
    assert cxc_actual[0][1] == 75000

    print("Total Activo actual:", esf_avanzado.total_activo_actual)
    print("Total Pasivo + Capital actual:", esf_avanzado.total_pasivo_mas_capital_actual)
    print(generar_banner_verificacion(esf_avanzado))
    # Con la utilidad integral exacta inyectada, este balance sí fue diseñado
    # para cuadrar en el año actual (replica la prueba del motor V3 original).
    assert esf_avanzado.cuadrado_actual, "El ESF avanzado debería cuadrar en el año actual"

    # Vía resolver_ejercicio_integral en modo avanzado — mismo resultado
    # (usando el mismo ERI con el que se armó movimientos_esf_avanzado)
    eri3, esf3 = resolver_ejercicio_integral(movimientos_eri_avanzado, movimientos_esf_avanzado)
    assert isinstance(esf3, ResultadoESF)
    assert esf3 == esf_avanzado, "resolver_ejercicio_integral debe coincidir con el cálculo manual"

    # Vía resolver_practica_aislada en modo avanzado
    esf_aislada_avanzada = resolver_practica_aislada(movimientos_esf_avanzado, utilidad_o_perdida=50000)
    assert isinstance(esf_aislada_avanzada, ResultadoESF)

    print("\nTodas las pruebas pasaron correctamente. ✓")
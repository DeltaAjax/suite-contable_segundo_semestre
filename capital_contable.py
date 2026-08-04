"""
capital_contable.py — Estado de Cambios en el Capital Contable
Herramienta de Autoevaluación Financiera — Motor Contable NIF

Genera el reporte de 5 columnas exactas [Concepto, Notas, Capital
Contribuido, Capital Ganado, Totales], con las filas fijas del catálogo
(Capital social, Aportaciones, Utilidades acumuladas, Utilidad integral,
Reserva legal, Reserva de reinversión) y soporte para cuentas dinámicas
que el alumno agregue vía el catálogo complementario de Capital Contable
(cada una en su propia fila, dentro de la sección que le corresponda).

Nota de diseño sobre 'Saldo al 31 de diciembre del año anterior': ese
renglón toma directamente los saldos anteriores capturados por el alumno
en cada cuenta de Capital (no se le suma una 'utilidad integral anterior'
por separado), porque se asume que el saldo anterior de 'Utilidades
acumuladas' ya es el saldo de cierre del periodo previo — es decir, ya
incluye cualquier utilidad de años pasados. Solo la 'Utilidad integral'
del año EN CURSO (que viene del ERI) se agrega como movimiento del periodo.
"""

from dataclasses import dataclass, field

from catalog import Clasificacion, NIF, SeccionCapital
from engine import MovimientoESF, ResultadoESF

_TOLERANCIA = 0.005

# Nombres de las cuentas "fijas" del catálogo V3 para cada sección del
# Estado de Cambios. Cualquier cuenta de Capital Contable que NO esté en
# estas listas se trata como cuenta dinámica y se renderiza en su propia fila.
NOMBRES_FIJOS_CAPITAL_CONTRIBUIDO = [NIF.CAPITAL_SOCIAL.etiqueta, NIF.APORTACIONES_FUTUROS_AUMENTOS.etiqueta]
NOMBRES_FIJOS_UTILIDADES = [NIF.UTILIDADES_ACUMULADAS.etiqueta, NIF.PERDIDAS_ACUMULADAS.etiqueta]
NOMBRES_FIJOS_RESERVAS = [NIF.RESERVA_LEGAL.etiqueta, NIF.RESERVA_REINVERSION.etiqueta]


@dataclass
class FilaCambiosCapital:
    concepto: str
    notas: str | None = None
    capital_contribuido: float | None = None
    capital_ganado: float | None = None
    totales: float | None = None
    es_encabezado_categoria: bool = False  # filas "Utilidades" / "Reservas": todo vacío salvo concepto


@dataclass
class EstadoCambiosCapital:
    filas: list[FilaCambiosCapital] = field(default_factory=list)
    total_capital_contribuido_actual: float = 0.0
    total_capital_ganado_actual: float = 0.0
    total_capital_contable_actual: float = 0.0


def _suma_por_nombre(movimientos: list[MovimientoESF], nombre: str, anio: str) -> float:
    return round(sum(m.monto(anio) for m in movimientos if m.cuenta.nombre == nombre), 2)


def generar_estado_cambios_capital(
    movimientos_esf: list[MovimientoESF],
    utilidad_integral_actual: float,
) -> EstadoCambiosCapital:
    """
    movimientos_esf: la MISMA lista que se le pasa a engine.calcular_esf().
    utilidad_integral_actual: engine.calcular_eri(...).utilidad_integral del
                               periodo en curso.
    """
    movs_capital = [m for m in movimientos_esf if m.cuenta.clasificacion == Clasificacion.CAPITAL_CONTABLE]

    filas: list[FilaCambiosCapital] = []

    # ---------------------------------------------------------------
    # Saldo al 31 de diciembre del año anterior
    # ---------------------------------------------------------------
    saldo_ant_contribuido = round(sum(m.monto("anterior") for m in movs_capital), 2)
    # OJO: aquí SÍ se puede sumar todo (fijas + dinámicas) porque el saldo
    # anterior no distingue fila individual, es un solo total de arranque.
    saldo_ant_ganado = 0.0  # se recalcula abajo tras separar contribuido/ganado por sección
    ganado_ant = round(sum(
        m.monto("anterior") for m in movs_capital if m.cuenta.seccion_capital in (SeccionCapital.UTILIDADES, SeccionCapital.RESERVAS)
    ), 2)
    contribuido_ant = round(sum(
        m.monto("anterior") for m in movs_capital if m.cuenta.seccion_capital == SeccionCapital.CAPITAL_CONTRIBUIDO
    ), 2)
    filas.append(FilaCambiosCapital(
        concepto="Saldo al 31 de diciembre del (año anterior)",
        capital_contribuido=contribuido_ant,
        capital_ganado=ganado_ant,
        totales=round(contribuido_ant + ganado_ant, 2),
    ))

    # ---------------------------------------------------------------
    # CAPITAL CONTRIBUIDO
    # ---------------------------------------------------------------
    total_contribuido_actual = 0.0
    for nombre_fijo in NOMBRES_FIJOS_CAPITAL_CONTRIBUIDO:
        monto = _suma_por_nombre(movs_capital, nombre_fijo, "actual")
        filas.append(FilaCambiosCapital(concepto=nombre_fijo, capital_contribuido=monto, totales=monto))
        total_contribuido_actual += monto

    dinamicas_contribuido = [
        m for m in movs_capital
        if m.cuenta.seccion_capital == SeccionCapital.CAPITAL_CONTRIBUIDO
        and m.cuenta.nombre not in NOMBRES_FIJOS_CAPITAL_CONTRIBUIDO
    ]
    for m in dinamicas_contribuido:
        monto = round(m.monto("actual"), 2)
        filas.append(FilaCambiosCapital(concepto=m.cuenta.nombre, capital_contribuido=monto, totales=monto))
        total_contribuido_actual += monto

    # ---------------------------------------------------------------
    # UTILIDADES (encabezado + filas)
    # ---------------------------------------------------------------
    total_ganado_actual = 0.0
    filas.append(FilaCambiosCapital(concepto="Utilidades", es_encabezado_categoria=True))

    monto_utilidades_acum = _suma_por_nombre(movs_capital, NIF.UTILIDADES_ACUMULADAS.etiqueta, "actual")
    filas.append(FilaCambiosCapital(
        concepto=NIF.UTILIDADES_ACUMULADAS.etiqueta, capital_ganado=monto_utilidades_acum, totales=monto_utilidades_acum,
    ))
    total_ganado_actual += monto_utilidades_acum

    monto_perdidas_acum = _suma_por_nombre(movs_capital, NIF.PERDIDAS_ACUMULADAS.etiqueta, "actual")
    if monto_perdidas_acum:
        filas.append(FilaCambiosCapital(
            concepto=NIF.PERDIDAS_ACUMULADAS.etiqueta, capital_ganado=monto_perdidas_acum, totales=monto_perdidas_acum,
        ))
        total_ganado_actual += monto_perdidas_acum

    utilidad_integral_actual = round(utilidad_integral_actual, 2)
    filas.append(FilaCambiosCapital(
        concepto="Utilidad integral", capital_ganado=utilidad_integral_actual, totales=utilidad_integral_actual,
    ))
    total_ganado_actual += utilidad_integral_actual

    dinamicas_utilidades = [
        m for m in movs_capital
        if m.cuenta.seccion_capital == SeccionCapital.UTILIDADES
        and m.cuenta.nombre not in NOMBRES_FIJOS_UTILIDADES
    ]
    for m in dinamicas_utilidades:
        monto = round(m.monto("actual"), 2)
        filas.append(FilaCambiosCapital(concepto=m.cuenta.nombre, capital_ganado=monto, totales=monto))
        total_ganado_actual += monto

    # ---------------------------------------------------------------
    # RESERVAS (encabezado + filas)
    # ---------------------------------------------------------------
    filas.append(FilaCambiosCapital(concepto="Reservas", es_encabezado_categoria=True))

    monto_reserva_legal = _suma_por_nombre(movs_capital, NIF.RESERVA_LEGAL.etiqueta, "actual")
    filas.append(FilaCambiosCapital(
        concepto=NIF.RESERVA_LEGAL.etiqueta, capital_ganado=monto_reserva_legal, totales=monto_reserva_legal,
    ))
    total_ganado_actual += monto_reserva_legal

    monto_reserva_reinversion = _suma_por_nombre(movs_capital, NIF.RESERVA_REINVERSION.etiqueta, "actual")
    if monto_reserva_reinversion:
        filas.append(FilaCambiosCapital(
            concepto=NIF.RESERVA_REINVERSION.etiqueta, capital_ganado=monto_reserva_reinversion, totales=monto_reserva_reinversion,
        ))
        total_ganado_actual += monto_reserva_reinversion

    dinamicas_reservas = [
        m for m in movs_capital
        if m.cuenta.seccion_capital == SeccionCapital.RESERVAS
        and m.cuenta.nombre not in NOMBRES_FIJOS_RESERVAS
    ]
    for m in dinamicas_reservas:
        monto = round(m.monto("actual"), 2)
        filas.append(FilaCambiosCapital(concepto=m.cuenta.nombre, capital_ganado=monto, totales=monto))
        total_ganado_actual += monto

    # ---------------------------------------------------------------
    # Saldo al 31 de diciembre del año actual
    # ---------------------------------------------------------------
    total_contribuido_actual = round(total_contribuido_actual, 2)
    total_ganado_actual = round(total_ganado_actual, 2)
    total_capital_actual = round(total_contribuido_actual + total_ganado_actual, 2)

    filas.append(FilaCambiosCapital(
        concepto="Saldo al 31 de diciembre del (año actual)",
        capital_contribuido=total_contribuido_actual,
        capital_ganado=total_ganado_actual,
        totales=total_capital_actual,
    ))

    return EstadoCambiosCapital(
        filas=filas,
        total_capital_contribuido_actual=total_contribuido_actual,
        total_capital_ganado_actual=total_ganado_actual,
        total_capital_contable_actual=total_capital_actual,
    )


def validar_consistencia_con_esf(estado_cambios: EstadoCambiosCapital, resultado_esf: ResultadoESF) -> tuple[bool, float]:
    """
    Checklist de la Guía General: el Total de Capital Contable del Estado de
    Cambios debe coincidir exactamente con el del ESF (mismo periodo actual).
    Devuelve (coincide, diferencia).
    """
    diferencia = round(estado_cambios.total_capital_contable_actual - resultado_esf.total_capital_contable_actual, 2)
    return abs(diferencia) < _TOLERANCIA, diferencia


if __name__ == "__main__":
    from catalog import obtener_cuenta
    from engine import calcular_esf

    def mov(nombre: str, actual: float, anterior: float = 0.0) -> MovimientoESF:
        return MovimientoESF(cuenta=obtener_cuenta(nombre), monto_actual=actual, monto_anterior=anterior)

    movimientos = [
        mov("Caja", 50000, 30000),
        mov("Clientes", 80000, 60000),
        mov("Estimación de cobros dudosos", 5000, 3000),
        mov("Edificios", 150000, 150000),
        mov("Depreciación acumulada de...", 20000, 10000),
        mov("Proveedores", 40000, 35000),
        mov("Capital social", 150000, 150000),
        mov("Utilidades acumuladas", 15000, 2000),
    ]
    utilidad_integral_actual = 50000.0  # mismo valor usado en engine.py __main__

    resultado_esf = calcular_esf(movimientos, utilidad_integral_actual=utilidad_integral_actual)
    estado_cambios = generar_estado_cambios_capital(movimientos, utilidad_integral_actual)

    print(f"{'Concepto':45s} {'Cap.Contrib.':>14s} {'Cap.Ganado':>14s} {'Totales':>14s}")
    for fila in estado_cambios.filas:
        cc = f"{fila.capital_contribuido:,.2f}" if fila.capital_contribuido is not None else ""
        cg = f"{fila.capital_ganado:,.2f}" if fila.capital_ganado is not None else ""
        tt = f"{fila.totales:,.2f}" if fila.totales is not None else ""
        print(f"{fila.concepto:45s} {cc:>14s} {cg:>14s} {tt:>14s}")

    ok, diff = validar_consistencia_con_esf(estado_cambios, resultado_esf)
    print(f"\nTotal Capital Contable (Cambios): {estado_cambios.total_capital_contable_actual}")
    print(f"Total Capital Contable (ESF):     {resultado_esf.total_capital_contable_actual}")
    print(f"¿Coinciden? {ok} (diferencia: {diff})")
# pdf_exporter.py - Exportador PDF con estilo institucional FACPYA (Rojo y Gris)
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from engine import ResultadoESF, ResultadoERI, formatear_moneda
from capital_contable import EstadoCambiosCapital
from flujo_efectivo import ResultadoFlujoEfectivo

def generar_pdf_estados_financieros(
    empresa: str,
    periodo: str,
    esf: ResultadoESF,
    eri: ResultadoERI,
    flujo_indirecto: ResultadoFlujoEfectivo,
    flujo_directo: ResultadoFlujoEfectivo,
    estado_cambios: EstadoCambiosCapital
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, leading=20, alignment=1, textColor=colors.HexColor('#800000'))
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Heading2'], fontSize=11, leading=14, alignment=1, textColor=colors.HexColor('#4A5568'))
    section_style = ParagraphStyle('SectionStyle', parent=styles['Heading2'], fontSize=13, leading=16, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor('#800000'))
    normal_style = styles['Normal']
    
    # Estilo de tabla FACPYA: Encabezado Rojo Guinda (#800000) y bordes Gris
    estilo_tabla_facpya = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#800000')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
    ])

    elements = []

    def _encabezado(titulo_reporte: str):
        elements.append(Paragraph(f"<b>{empresa}</b>", title_style))
        elements.append(Paragraph(f"{titulo_reporte}", subtitle_style))
        elements.append(Paragraph(f"{periodo}", subtitle_style))
        elements.append(Spacer(1, 15))

    # --- 1. ESF ---
    _encabezado("Estado de Situación Financiera (NIF B-6)")
    data_esf = [["Concepto", "Año Actual", "Año Anterior"]]
    def _add_esf_rows(titulo: str, rubros: list, tot_act: float, tot_ant: float):
        data_esf.append([f"<b>{titulo}</b>", "", ""])
        for r in rubros:
            data_esf.append([f"  {r.nif.etiqueta}", formatear_moneda(r.saldo_actual), formatear_moneda(r.saldo_anterior)])
        data_esf.append([f"<b>Total {titulo}</b>", f"<b>{formatear_moneda(tot_act)}</b>", f"<b>{formatear_moneda(tot_ant)}</b>"])

    _add_esf_rows("Activo Circulante", esf.activo_circulante, esf.total_activo_circulante_actual, esf.total_activo_circulante_anterior)
    _add_esf_rows("Activo No Circulante", esf.activo_no_circulante, esf.total_activo_no_circulante_actual, esf.total_activo_no_circulante_anterior)
    data_esf.append(["<b>TOTAL ACTIVO</b>", f"<b>{formatear_moneda(esf.total_activo_actual)}</b>", f"<b>{formatear_moneda(esf.total_activo_anterior)}</b>"])
    _add_esf_rows("Pasivo a Corto Plazo", esf.pasivo_corto_plazo, esf.total_pasivo_corto_plazo_actual, esf.total_pasivo_corto_plazo_anterior)
    _add_esf_rows("Pasivo a Largo Plazo", esf.pasivo_largo_plazo, esf.total_pasivo_largo_plazo_actual, esf.total_pasivo_largo_plazo_anterior)
    data_esf.append(["<b>TOTAL PASIVO</b>", f"<b>{formatear_moneda(esf.total_pasivo_actual)}</b>", f"<b>{formatear_moneda(esf.total_pasivo_anterior)}</b>"])
    _add_esf_rows("Capital Contribuido", esf.capital_contribuido, esf.total_capital_contribuido_actual, esf.total_capital_contribuido_anterior)
    _add_esf_rows("Capital Ganado", esf.capital_ganado, esf.total_capital_ganado_actual, esf.total_capital_ganado_anterior)
    data_esf.append(["<b>TOTAL CAPITAL CONTABLE</b>", f"<b>{formatear_moneda(esf.total_capital_contable_actual)}</b>", f"<b>{formatear_moneda(esf.total_capital_contable_anterior)}</b>"])
    data_esf.append(["<b>TOTAL PASIVO + CAPITAL</b>", f"<b>{formatear_moneda(esf.total_pasivo_mas_capital_actual)}</b>", f"<b>{formatear_moneda(esf.total_pasivo_mas_capital_anterior)}</b>"])

    t_esf = Table([[Paragraph(cell, normal_style) for cell in row] for row in data_esf], colWidths=[280, 130, 130])
    t_esf.setStyle(estilo_tabla_facpya)
    elements.append(t_esf)
    elements.append(PageBreak())

    # --- 2. ERI ---
    _encabezado("Estado de Resultados Integral (NIF B-3)")
    data_eri = [
        ["Concepto", "Monto"],
        ["Ventas", formatear_moneda(eri.ventas)],
        ["Costo de Ventas", formatear_moneda(eri.costo_ventas)],
        ["<b>Utilidad Bruta (3°)</b>", f"<b>{formatear_moneda(eri.utilidad_bruta)}</b>"],
        ["Gastos de Venta", formatear_moneda(eri.gastos_venta)],
        ["Gastos de Administración", formatear_moneda(eri.gastos_administracion)],
        ["Gastos Generales (6°)", formatear_moneda(eri.gastos_generales)],
        ["<b>Utilidad antes de Otros (7°)</b>", f"<b>{formatear_moneda(eri.utilidad_antes_otros)}</b>"],
        ["Otros Productos / Gastos (Neto)", formatear_moneda(eri.neto_otros_productos_gastos)],
        ["<b>Utilidad de Operación (11°)</b>", f"<b>{formatear_moneda(eri.utilidad_operacion)}</b>"],
        ["RIF (14°)", formatear_moneda(eri.rif)],
        ["<b>Utilidad antes de Impuestos (15°)</b>", f"<b>{formatear_moneda(eri.utilidad_antes_impuestos)}</b>"],
        ["Impuestos a la Utilidad (18°)", formatear_moneda(eri.impuestos_utilidad)],
        ["<b>Utilidad Neta (19°)</b>", f"<b>{formatear_moneda(eri.utilidad_neta)}</b>"],
        ["Otros Resultados Integrales (ORI)", formatear_moneda(eri.ori)],
        ["<b>UTILIDAD INTEGRAL (21°)</b>", f"<b>{formatear_moneda(eri.utilidad_integral)}</b>"],
    ]
    t_eri = Table([[Paragraph(cell, normal_style) for cell in row] for row in data_eri], colWidths=[380, 160])
    t_eri.setStyle(estilo_tabla_facpya)
    elements.append(t_eri)
    elements.append(PageBreak())

    # --- 3. FLUJO DE EFECTIVO ---
    _encabezado("Estado de Flujos de Efectivo (NIF B-2)")
    def _build_flujo_table(resultado: ResultadoFlujoEfectivo):
        data_f = [["Concepto", "Monto"]]
        data_f.append(["<b>Actividades de Operación</b>", ""])
        for f in resultado.filas_operacion:
            data_f.append([f"  {f.concepto}", formatear_moneda(f.monto)])
        data_f.append(["<b>Total Operación</b>", f"<b>{formatear_moneda(resultado.total_operacion)}</b>"])
        data_f.append(["<b>Actividades de Inversión</b>", ""])
        for f in resultado.filas_inversion:
            data_f.append([f"  {f.concepto}", formatear_moneda(f.monto)])
        data_f.append(["<b>Total Inversión</b>", f"<b>{formatear_moneda(resultado.total_inversion)}</b>"])
        data_f.append(["<b>Actividades de Financiamiento</b>", ""])
        for f in resultado.filas_financiamiento:
            data_f.append([f"  {f.concepto}", formatear_moneda(f.monto)])
        data_f.append(["<b>Total Financiamiento</b>", f"<b>{formatear_moneda(resultado.total_financiamiento)}</b>"])
        data_f.append(["<b>Incremento de Efectivo</b>", f"<b>{formatear_moneda(resultado.incremento_efectivo)}</b>"])
        data_f.append(["Efectivo Inicial", formatear_moneda(resultado.efectivo_inicial)])
        data_f.append(["<b>Efectivo Final (real)</b>", f"<b>{formatear_moneda(resultado.efectivo_final_real)}</b>"])
        
        t_f = Table([[Paragraph(cell, normal_style) for cell in row] for row in data_f], colWidths=[380, 160])
        t_f.setStyle(estilo_tabla_facpya)
        return t_f

    elements.append(Paragraph("<b>Método Indirecto</b>", section_style))
    elements.append(_build_flujo_table(flujo_indirecto))
    elements.append(Spacer(1, 15))
    elements.append(Paragraph("<b>Método Directo</b>", section_style))
    elements.append(_build_flujo_table(flujo_directo))
    elements.append(PageBreak())

    # --- 4. CAMBIOS EN CAPITAL ---
    _encabezado("Estado de Cambios en el Capital Contable (NIF B-4)")
    data_c = [["Concepto", "Capital Contribuido", "Capital Ganado", "Totales"]]
    for f in estado_cambios.filas:
        cc = formatear_moneda(f.capital_contribuido) if f.capital_contribuido is not None else ""
        cg = formatear_moneda(f.capital_ganado) if f.capital_ganado is not None else ""
        tt = formatear_moneda(f.totales) if f.totales is not None else ""
        concepto = f"<b>{f.concepto.upper()}</b>" if f.es_encabezado_categoria else f.concepto
        data_c.append([concepto, cc, cg, tt])
        
    t_c = Table([[Paragraph(cell, normal_style) for cell in row] for row in data_c], colWidths=[240, 100, 100, 100])
    t_c.setStyle(estilo_tabla_facpya)
    elements.append(t_c)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
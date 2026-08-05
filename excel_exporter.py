# excel_exporter.py
import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def generar_excel_estados_financieros(esf, eri, flujo_indirecto, estado_cambios, empresa="Empresa Demo S.A.", periodo="Del 1 de enero al 31 de diciembre de 2025") -> bytes:
    wb = Workbook()
    
    # Estilos globales (Tema FACPYA - Guinda)
    font_titulo = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    font_subtitulo = Font(name="Calibri", size=11, italic=True, color="FFFFFF")
    font_seccion = Font(name="Calibri", size=11, bold=True, color="800000")
    font_bold = Font(name="Calibri", size=11, bold=True)
    font_normal = Font(name="Calibri", size=11)
    
    fill_header = PatternFill(start_color="800000", end_color="800000", fill_type="solid")
    fill_sub_header = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
    
    align_center = Alignment(horizontal="center", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    
    border_thin = Border(bottom=Side(style="thin", color="D3D3D3"))
    border_total = Border(top=Side(style="thin", color="000000"), bottom=Side(style="double", color="000000"))
    
    fmt_moneda = '"$"#,##0.00;("$"#,##0.00);"-"'

    def _encabezado(ws, titulo_reporte):
        ws.merge_cells("A1:C1")
        ws.merge_cells("A2:C2")
        ws.merge_cells("A3:C3")
        
        ws["A1"] = empresa
        ws["A2"] = titulo_reporte
        ws["A3"] = periodo
        
        for r in range(1, 4):
            for col in range(1, 4):
                cell = ws.cell(row=r, column=col)
                cell.fill = fill_header
                cell.alignment = align_center
                if r == 1:
                    cell.font = font_titulo
                elif r == 2:
                    cell.font = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
                else:
                    cell.font = font_subtitulo
        ws.row_dimensions[1].height = 25
        ws.row_dimensions[2].height = 20
        ws.row_dimensions[3].height = 18

    # ----------------------------------------------------
    # TAB 1: Estado de Situación Financiera (ESF)
    # ----------------------------------------------------
    ws_esf = wb.active
    ws_esf.title = "ESF"
    _encabezado(ws_esf, "ESTADO DE SITUACIÓN FINANCIERA")
    
    ws_esf.cell(row=5, column=1, value="Concepto").font = font_bold
    ws_esf.cell(row=5, column=2, value="Año Actual").font = font_bold
    ws_esf.cell(row=5, column=3, value="Año Anterior").font = font_bold
    for c in range(1, 4):
        ws_esf.cell(row=5, column=c).fill = fill_sub_header
        ws_esf.cell(row=5, column=c).alignment = align_center if c > 1 else align_left

    r_idx = 6
    def _escribir_bloque_esf(titulo, rubros):
        nonlocal r_idx
        ws_esf.cell(row=r_idx, column=1, value=titulo).font = font_seccion
        r_idx += 1
        inicio = r_idx
        for r in rubros:
            ws_esf.cell(row=r_idx, column=1, value=f"  {r.nif.etiqueta}").font = font_normal
            
            c_act = ws_esf.cell(row=r_idx, column=2, value=r.saldo_actual)
            c_act.number_format = fmt_moneda
            c_act.font = font_normal
            
            c_ant = ws_esf.cell(row=r_idx, column=3, value=r.saldo_anterior)
            c_ant.number_format = fmt_moneda
            c_ant.font = font_normal
            
            ws_esf.cell(row=r_idx, column=1).border = border_thin
            c_act.border = border_thin
            c_ant.border = border_thin
            r_idx += 1
        fin = r_idx - 1
        
        # Fórmulas de total por sección
        ws_esf.cell(row=r_idx, column=1, value=f"Total {titulo}").font = font_bold
        
        cell_tot_act = ws_esf.cell(row=r_idx, column=2, value=f"=SUM(B{inicio}:B{fin})" if fin >= inicio else 0)
        cell_tot_act.font = font_bold
        cell_tot_act.number_format = fmt_moneda
        cell_tot_act.border = border_total
        
        cell_tot_ant = ws_esf.cell(row=r_idx, column=3, value=f"=SUM(C{inicio}:C{fin})" if fin >= inicio else 0)
        cell_tot_ant.font = font_bold
        cell_tot_ant.number_format = fmt_moneda
        cell_tot_ant.border = border_total
        
        f_row = r_idx
        r_idx += 2
        return f_row

    r_act_circ = _escribir_bloque_esf("Activo Circulante", esf.activo_circulante)
    r_act_nocirc = _escribir_bloque_esf("Activo No Circulante", esf.activo_no_circulante)
    
    # TOTAL ACTIVO con FÓRMULA
    ws_esf.cell(row=r_idx, column=1, value="TOTAL ACTIVO").font = font_bold
    c_tot_act = ws_esf.cell(row=r_idx, column=2, value=f"=B{r_act_circ}+B{r_act_nocirc}")
    c_tot_act.font = font_bold
    c_tot_act.number_format = fmt_moneda
    c_tot_act.border = border_total
    
    c_tot_ant = ws_esf.cell(row=r_idx, column=3, value=f"=C{r_act_circ}+C{r_act_nocirc}")
    c_tot_ant.font = font_bold
    c_tot_ant.number_format = fmt_moneda
    c_tot_ant.border = border_total
    r_idx += 2

    r_pas_cp = _escribir_bloque_esf("Pasivo a Corto Plazo", esf.pasivo_corto_plazo)
    r_pas_lp = _escribir_bloque_esf("Pasivo a Largo Plazo", esf.pasivo_largo_plazo)
    
    # TOTAL PASIVO
    ws_esf.cell(row=r_idx, column=1, value="TOTAL PASIVO").font = font_bold
    c_tot_p_act = ws_esf.cell(row=r_idx, column=2, value=f"=B{r_pas_cp}+B{r_pas_lp}")
    c_tot_p_act.font = font_bold
    c_tot_p_act.number_format = fmt_moneda
    c_tot_p_act.border = border_total
    
    c_tot_p_ant = ws_esf.cell(row=r_idx, column=3, value=f"=C{r_pas_cp}+C{r_pas_lp}")
    c_tot_p_ant.font = font_bold
    c_tot_p_ant.number_format = fmt_moneda
    c_tot_p_ant.border = border_total
    r_tot_pasivo = r_idx
    r_idx += 2

    r_cap_contrib = _escribir_bloque_esf("Capital Contribuido", esf.capital_contribuido)
    r_cap_ganado = _escribir_bloque_esf("Capital Ganado", esf.capital_ganado)
    
    # TOTAL CAPITAL CONTABLE
    ws_esf.cell(row=r_idx, column=1, value="TOTAL CAPITAL CONTABLE").font = font_bold
    c_tot_c_act = ws_esf.cell(row=r_idx, column=2, value=f"=B{r_cap_contrib}+B{r_cap_ganado}")
    c_tot_c_act.font = font_bold
    c_tot_c_act.number_format = fmt_moneda
    c_tot_c_act.border = border_total
    
    c_tot_c_ant = ws_esf.cell(row=r_idx, column=3, value=f"=C{r_cap_contrib}+C{r_cap_ganado}")
    c_tot_c_ant.font = font_bold
    c_tot_c_ant.number_format = fmt_moneda
    c_tot_c_ant.border = border_total
    r_tot_cap = r_idx
    r_idx += 2

    # TOTAL PASIVO + CAPITAL
    ws_esf.cell(row=r_idx, column=1, value="TOTAL PASIVO + CAPITAL").font = font_bold
    c_sum_act = ws_esf.cell(row=r_idx, column=2, value=f"=B{r_tot_pasivo}+B{r_tot_cap}")
    c_sum_act.font = font_bold
    c_sum_act.number_format = fmt_moneda
    c_sum_act.border = border_total
    
    c_sum_ant = ws_esf.cell(row=r_idx, column=3, value=f"=C{r_tot_pasivo}+C{r_tot_cap}")
    c_sum_ant.font = font_bold
    c_sum_ant.number_format = fmt_moneda
    c_sum_ant.border = border_total

    # ----------------------------------------------------
    # TAB 2: Estado de Resultados Integrales (ERI)
    # ----------------------------------------------------
    ws_eri = wb.create_sheet(title="ERI")
    _encabezado(ws_eri, "ESTADO DE RESULTADOS INTEGRAL")
    
    filas_eri = [
        ("Ventas", eri.ventas),
        ("Costo de Ventas", eri.costo_ventas),
        ("Utilidad Bruta", eri.utilidad_bruta),
        ("Gastos de Venta", eri.gastos_venta),
        ("Gastos de Administración", eri.gastos_administracion),
        ("Gastos Generales", eri.gastos_generales),
        ("Utilidad antes de Otros", eri.utilidad_antes_otros),
        ("Otros Productos", eri.otros_productos),
        ("Otros Gastos", eri.otros_gastos),
        ("Neto Otros Productos/Gastos", eri.neto_otros_productos_gastos),
        ("Utilidad de Operación", eri.utilidad_operacion),
        ("Productos Financieros", eri.productos_financieros),
        ("Gastos Financieros", eri.gastos_financieros),
        ("RIF", eri.rif),
        ("Utilidad antes de Impuestos", eri.utilidad_antes_impuestos),
        ("ISR", eri.isr),
        ("PTU", eri.ptu),
        ("Impuestos a la Utilidad", eri.impuestos_utilidad),
        ("Utilidad Neta", eri.utilidad_neta),
        ("Otros Resultados Integrales (ORI)", eri.ori),
        ("Utilidad Integral", eri.utilidad_integral),
    ]
    
    ws_eri.cell(row=5, column=1, value="Concepto").font = font_bold
    ws_eri.cell(row=5, column=2, value="Monto").font = font_bold
    ws_eri.cell(row=5, column=1).fill = fill_sub_header
    ws_eri.cell(row=5, column=2).fill = fill_sub_header
    
    r_idx = 6
    for concepto, monto in filas_eri:
        es_res = "Utilidad" in concepto or "Neto" in concepto or "RIF" in concepto
        ws_eri.cell(row=r_idx, column=1, value=concepto).font = font_bold if es_res else font_normal
        c_monto = ws_eri.cell(row=r_idx, column=2, value=monto)
        c_monto.font = font_bold if es_res else font_normal
        c_monto.number_format = fmt_moneda
        if es_res:
            c_monto.border = border_total
        else:
            c_monto.border = border_thin
        r_idx += 1

    # Autoajuste de columnas en todas las pestañas
    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or '')
                if cell.coordinate in sheet.merged_cells:
                    continue
                if len(val) > max_len:
                    max_len = len(val)
            sheet.column_dimensions[col_letter].width = max(max_len + 4, 15)

    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()
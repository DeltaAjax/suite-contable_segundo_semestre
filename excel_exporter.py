import io
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

def generar_excel_balanza(datos_cuentas, nombre_empresa="Entidad Académica FACPYA"):
    # 1. Crear libro de trabajo
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Balanza de Comprobación"
    ws.views.sheetView[0].showGridLines = True

    # Estilos contables
    font_titulo = Font(name="Calibri", size=14, bold=True)
    font_subtitulo = Font(name="Calibri", size=11, italic=True)
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    font_bold = Font(name="Calibri", size=11, bold=True)
    
    fill_header = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid") # Azul institucional
    align_center = Alignment(horizontal="center", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")
    
    thin_border = Side(style='thin', color='D9D9D9')
    border_data = Border(left=thin_border, right=thin_border, top=thin_border, bottom=thin_border)
    border_total = Border(top=Side(style='thin'), bottom=Side(style='double')) # Raya arriba, doble raya abajo (cierre contable)

    FORMATO_MONEDA = '"$"#,##0.00;("$"#,##0.00);"-"'

    # 2. Encabezado Oficial NIF
    ws.merge_cells('A1:E1')
    ws['A1'] = nombre_empresa
    ws['A1'].font = font_titulo
    ws['A1'].alignment = align_center

    ws.merge_cells('A2:E2')
    ws['A2'] = "BALANZA DE COMPROBACIÓN"
    ws['A2'].font = font_bold
    ws['A2'].alignment = align_center

    # 3. Cabeceras de la Tabla
    headers = ["Cuenta / Concepto", "Mov. Deudor", "Mov. Acreedor", "Saldo Deudor", "Saldo Acreedor"]
    ws.append([]) # Renglón en blanco (Fila 3)
    ws.append(headers) # Fila 4
    
    for col in range(1, 6):
        cell = ws.cell(row=4, column=col)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center

    # 4. Inserción de Datos Dinámicos
    row_start = 5
    # Ejemplo de datos_cuentas: [{"concepto": "Bancos", "mov_deudor": 50000, "mov_acreedor": 10000}, ...]
    for idx, item in enumerate(datos_cuentas):
        r = row_start + idx
        ws.cell(row=r, column=1, value=item["concepto"]).border = border_data
        
        # Movimientos (valores ingresados)
        c_deudor = ws.cell(row=r, column=2, value=item.get("mov_deudor", 0))
        c_acreedor = ws.cell(row=r, column=3, value=item.get("mov_acreedor", 0))
        
        c_deudor.number_format = FORMATO_MONEDA
        c_acreedor.number_format = FORMATO_MONEDA
        c_deudor.border = border_data
        c_acreedor.border = border_data

        # FÓRMULAS DE EXCEL PARA SALDOS (Diferencia según naturaleza)
        # Saldo Deudor: IF(B - C > 0, B - C, 0)
        cell_saldo_d = ws.cell(row=r, column=4, value=f'=IF((B{r}-C{r})>0, B{r}-C{r}, 0)')
        cell_saldo_d.number_format = FORMATO_MONEDA
        cell_saldo_d.border = border_data

        # Saldo Acreedor: IF(C - B > 0, C - B, 0)
        cell_saldo_a = ws.cell(row=r, column=5, value=f'=IF((C{r}-B{r})>0, C{r}-B{r}, 0)')
        cell_saldo_a.number_format = FORMATO_MONEDA
        cell_saldo_a.border = border_data

    # 5. Renglón de Sumas Iguales con FÓRMULAS SUMA()
    row_end = row_start + len(datos_cuentas) - 1
    row_total = row_end + 1

    ws.cell(row=row_total, column=1, value="SUMAS IGUALES").font = font_bold
    
    # Fórmulas de totalización
    cols_letras = ['B', 'C', 'D', 'E']
    for idx, col_letra in enumerate(cols_letras, start=2):
        cell_tot = ws.cell(row=row_total, column=idx, value=f'=SUM({col_letra}{row_start}:{col_letra}{row_end})')
        cell_tot.font = font_bold
        cell_tot.number_format = FORMATO_MONEDA
        cell_tot.border = border_total

    # Ajustar ancho automático de columnas
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 18)

    # 6. Guardar en memoria para descarga rápida en navegador
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()
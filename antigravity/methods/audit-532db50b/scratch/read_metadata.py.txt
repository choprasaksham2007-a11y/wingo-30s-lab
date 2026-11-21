import openpyxl
import pandas as pd

for fname in ['Colour_Prediction_Dataset_v3.xlsx', 'Colour_Prediction_Dataset_corrected.xlsx']:
    path = rf"project_reports\{fname}"
    wb = openpyxl.load_workbook(path, data_only=True)
    print("="*60)
    print(f"FILE: {fname}")
    print("="*60)
    for sname in wb.sheetnames:
        ws = wb[sname]
        print(f"\n--- Sheet: {sname} (Rows: {ws.max_row}, Cols: {ws.max_column}) ---")
        if sname in ['Read_Me', 'Missing_Rounds', 'Audit', 'User_Provided', 'ID_Audit']:
            for r in range(1, min(ws.max_row+1, 25)):
                row_vals = [ws.cell(r, c).value for c in range(1, min(ws.max_column+1, 10))]
                if any(v is not None for v in row_vals):
                    print(f"  Row {r}: {row_vals}")
    wb.close()

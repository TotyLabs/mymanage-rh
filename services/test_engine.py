import logging, sys, os
sys.path.append(os.getcwd())

from payroll_core import SessionLocal
from services.legajo.import_service import ImportService
from services.legajo.parsers import ParserFactory

db = SessionLocal()
svc = ImportService(db)
parser = ParserFactory.get_parser('test.xls')
file_path = 'storage/imports/45ef0230-8b78-42ab-bb55-ebe3793af0d3_Modelo Legajo Ingreso 2012_Merida.xls'
sheets = parser.get_raw_sheets(file_path)

best_sheet = None
best_score = -9999
for name, rows in sheets.items():
    if not rows: continue
    score = svc._evaluate_sheet(name, rows)
    print(f"Sheet: {name:30} | Score: {score}")
    if score > best_score:
        best_score = score
        best_sheet = name

print(f"\nWINNER: {best_sheet} with {best_score} points!")

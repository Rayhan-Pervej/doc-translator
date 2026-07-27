import zipfile, glob, re

orig = 'design/【Looop_CIS】機能仕様書(CustomerProfile)_CP01_顧客情報マイページ取得API.xlsx'
out = glob.glob('design_english/*.xlsx')[0]
print('Output file:', out)

# Compare drawing1.xml
with zipfile.ZipFile(orig) as z:
    orig_d1 = z.read('xl/drawings/drawing1.xml').decode('utf-8')
with zipfile.ZipFile(out) as z:
    out_d1 = z.read('xl/drawings/drawing1.xml').decode('utf-8')

print('drawing1 orig length:', len(orig_d1))
print('drawing1 out  length:', len(out_d1))
print('Same?', orig_d1 == out_d1)

# Check sheet5 rels
with zipfile.ZipFile(orig) as z:
    s5rel = z.read('xl/worksheets/_rels/sheet5.xml.rels').decode('utf-8')
print('\nsheet5.xml.rels:', s5rel[:800])

# Check workbook sheet names
with zipfile.ZipFile(out) as z:
    wb = z.read('xl/workbook.xml').decode('utf-8')
sheets = re.findall(r'name="([^"]+)"', wb)
print('\nSheet names in output workbook.xml:', sheets)

# Check Content_Types
with zipfile.ZipFile(orig) as z:
    ct_orig = z.read('[Content_Types].xml').decode('utf-8')
with zipfile.ZipFile(out) as z:
    ct_out = z.read('[Content_Types].xml').decode('utf-8')
print('\nContent_Types same?', ct_orig == ct_out)

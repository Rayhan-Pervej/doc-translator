import zipfile, glob, re

def has_japanese(text):
    return any(0x3000 <= ord(c) <= 0x9FFF for c in text)

out = glob.glob('design_english/*CP02*.xlsx')[0]
print('File:', out)

with zipfile.ZipFile(out) as z:
    for fname in sorted(z.namelist()):
        if not fname.endswith('.xml') or fname.endswith('.rels'):
            continue
        try:
            content = z.read(fname).decode('utf-8')
        except:
            continue
        # strip XML tags, find text nodes
        texts = re.findall(r'>([^<]+)<', content)
        jp = [t.strip() for t in texts if t.strip() and has_japanese(t)]
        if jp:
            print(f'\n{fname}:')
            for t in jp[:10]:
                print(f'  {repr(t)}')

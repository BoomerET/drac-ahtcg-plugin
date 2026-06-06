#!/usr/bin/env python3
import csv, json, os, re, sys, urllib.request, zipfile
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
JSON_PATH = ROOT / 'BarkhamHorror.json'
OUT = ROOT / 'BarkhamHorror_export'
IMG = OUT / 'images'
JPG = OUT / 'jpg_originals'
OUT.mkdir(exist_ok=True); IMG.mkdir(exist_ok=True); JPG.mkdir(exist_ok=True)

def clean(v):
    if v is None: return ''
    if isinstance(v, (dict, list)): return json.dumps(v, ensure_ascii=False, separators=(',', ':'))
    return str(v).replace('\r\n','\n').replace('\r','\n')

def download(url, dest):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        dest.write_bytes(r.read())

def to_webp(src, dest):
    with Image.open(src) as im:
        im.save(dest, 'WEBP', quality=95, method=6)

with JSON_PATH.open(encoding='utf-8') as f:
    data = json.load(f)
cards = data['data']['cards']

# Wide metadata TSV, safe for import/mapping.
fields = [
    'code','name','subname','type_code','faction_code','encounter_code','encounter_position','position','quantity',
    'deck_limit','cost','xp','slot','traits','text','flavor','back_name','back_text','back_flavor',
    'health','sanity','shroud','clues','doom','stage','victory',
    'enemy_fight','enemy_health','enemy_evade','enemy_damage','enemy_horror','health_per_investigator',
    'skill_willpower','skill_intellect','skill_combat','skill_agility','skill_wild',
    'is_unique','subtype_code','restrictions','deck_requirements','illustrator',
    'image_file','back_image_file','image_url','back_image_url'
]
# Correct JSON enemy health uses 'health'. Keep enemy_health duplicated for enemy rows only.
with (OUT/'barkham_cards_full.tsv').open('w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fields, delimiter='\t', extrasaction='ignore')
    w.writeheader()
    for c in cards:
        row = dict(c)
        code = c['code']
        row['image_file'] = f'images/{code}.webp' if c.get('image_url') else ''
        row['back_image_file'] = f'images/{code}b.webp' if c.get('back_image_url') else ''
        row['enemy_health'] = c.get('health','') if c.get('type_code') == 'enemy' else ''
        w.writerow({k: clean(row.get(k,'')) for k in fields})

# Narrow append TSV commonly useful for DragnCards-style card DB ingestion.
append_fields = ['id','name','type','faction','encounter_set','encounter_position','quantity','front','back','width','height']
with (OUT/'barkham_dragncards_append.tsv').open('w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, append_fields, delimiter='\t')
    w.writeheader()
    for c in cards:
        code = c['code']
        w.writerow({
            'id': code,
            'name': clean(c.get('name')),
            'type': clean(c.get('type_code')),
            'faction': clean(c.get('faction_code')),
            'encounter_set': clean(c.get('encounter_code')),
            'encounter_position': clean(c.get('encounter_position')),
            'quantity': clean(c.get('quantity')),
            'front': f'images/{code}.webp' if c.get('image_url') else '',
            'back': f'images/{code}b.webp' if c.get('back_image_url') else '',
            'width': '0.74',
            'height': '1',
        })

# Download/convert images. This is intentionally repeatable.
failures=[]
for c in cards:
    for side, key, suffix in [('front','image_url',''), ('back','back_image_url','b')]:
        url = c.get(key)
        if not url: continue
        code = c['code'] + suffix
        jpg = JPG / f'{code}.jpg'
        webp = IMG / f'{code}.webp'
        try:
            if not jpg.exists():
                download(url, jpg)
            if not webp.exists():
                to_webp(jpg, webp)
            print('OK', code)
        except Exception as e:
            failures.append((c['code'], side, url, repr(e)))
            print('FAIL', code, e, file=sys.stderr)

with (OUT/'download_failures.tsv').open('w', encoding='utf-8', newline='') as f:
    w=csv.writer(f, delimiter='\t'); w.writerow(['code','side','url','error']); w.writerows(failures)

zip_path = ROOT/'BarkhamHorror_export.zip'
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in OUT.rglob('*'):
        z.write(p, p.relative_to(OUT.parent))
print(f'Wrote {zip_path}')
if failures:
    print(f'{len(failures)} image downloads failed; see download_failures.tsv', file=sys.stderr)


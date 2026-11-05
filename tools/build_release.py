"""Build updater assets and a clean Windows installer using an explicit allowlist."""
from pathlib import Path
import hashlib, json, re, zipfile
ROOT=Path(__file__).resolve().parents[1]
version=(ROOT/'version.txt').read_text(encoding='utf-8-sig').strip()
if not re.fullmatch(r'\d{1,6}\.\d{1,6}\.\d{1,6}',version):
    raise SystemExit('version.txt must contain MAJOR.MINOR.PATCH')
OUT=ROOT/'dist'
OUT.mkdir(exist_ok=True)
APP=['app.py','targeting.py','requirements.txt','README.md']
BOOTSTRAP=['launch.ps1','Start.cmd','updater.py','update-source.json','version.txt']
for name in APP+BOOTSTRAP:
    if name.endswith('.py'): compile((ROOT/name).read_bytes(),name,'exec')
package=f'hazmob-{version}.zip'
with zipfile.ZipFile(OUT/package,'w',zipfile.ZIP_DEFLATED) as archive:
    for name in APP: archive.write(ROOT/name,name)
manifest={'version':version,'package':package,'sha256':hashlib.sha256((OUT/package).read_bytes()).hexdigest()}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
with zipfile.ZipFile(OUT/'HazmobSnap-Windows.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for name in APP+BOOTSTRAP: archive.write(ROOT/name,'HazmobSnap/'+name)
for file in OUT.glob('*.zip'):
    with zipfile.ZipFile(file) as archive:
        if archive.testzip(): raise SystemExit('Archive failed integrity check')
print(f'Built release v{version}')

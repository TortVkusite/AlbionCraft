"""Create shareable archives from an explicit allowlist, never a project ZIP."""
from pathlib import Path
import hashlib
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.version import __version__

root=Path(__file__).resolve().parents[1]
out=root/'release';out.mkdir(exist_ok=True)
top={'README.md','USER_GUIDE.md','DATA_SOURCES.md','CHANGES.md','LICENSE',
     'THIRD_PARTY_NOTICES.md','PRIVACY.md','CONTRIBUTING.md','.gitignore','.gitattributes',
     'requirements.txt','requirements-build.txt','Start.cmd','Start.ps1',
     'Setup.cmd','AlbionCraft.spec'}
research={'items.json','names.json','achievements.json','full_gamedata.json','README.md'}
source=[]
for p in root.rglob('*'):
    if not p.is_file():continue
    rel=p.relative_to(root);first=rel.parts[0]
    if rel==Path('tools/albion-data-client/AODP-LICENSE.txt'):
        source.append(p);continue
    if first in {'.venv','release','dist','build','release_licenses','icons','logs','installers','tools'}:continue
    if '__pycache__' in rel.parts or p.suffix in {'.pyc','.pyo'}:continue
    if len(rel.parts)==1 and p.name in top:source.append(p)
    elif first=='research' and len(rel.parts)==2 and p.name in research:source.append(p)
    elif first in {'app','tests','docs','scripts','.github','vendor','licenses'}:source.append(p)
assert all(not any(name in p.relative_to(root).parts for name in ('settings.json','player.sqlite','prices.sqlite','LOCAL_BUILD.json')) for p in source)
assert all(not p.name.endswith(('.log','.sqlite','.db')) for p in source)
base=f'AlbionCraft-{__version__}'
source_zip=out/(base+'-source.zip')
with zipfile.ZipFile(source_zip,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
    for p in sorted(source):archive.write(p,Path(base)/p.relative_to(root))
(out/'SOURCE_MANIFEST.txt').write_text('\n'.join(str(p.relative_to(root)) for p in sorted(source))+'\n',encoding='utf-8')
if '--source-only' in sys.argv:
    print(f'{source_zip.name}: {len(source)} files, {source_zip.stat().st_size/1024/1024:.1f} MiB')
    sys.exit(0)
binary=root/'dist/AlbionCraft'
if not (binary/'AlbionCraft.exe').is_file():raise SystemExit('Build the EXE before packaging')
windows_zip=out/(base+'-windows-x64.zip')
with zipfile.ZipFile(windows_zip,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for p in sorted(binary.rglob('*')):
        if p.is_file():archive.write(p,Path('AlbionCraft')/p.relative_to(binary))
    for name in ['LICENSE','THIRD_PARTY_NOTICES.md','USER_GUIDE.md','PRIVACY.md']:
        archive.write(root/name,Path('AlbionCraft')/name)
    for name in ['QUICK_START.md','QUICK_START_EN.md','RELEASE_NOTES.md']:
        archive.write(root/'docs'/name,Path('AlbionCraft/docs')/name)
hashes=[]
for p in (source_zip,windows_zip):
    hashes.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name)
    print(f'{p.name}: {p.stat().st_size/1024/1024:.1f} MiB')
(out/'SHA256SUMS.txt').write_text('\n'.join(hashes)+'\n',encoding='utf-8')

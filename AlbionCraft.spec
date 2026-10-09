# Build with: .venv\Scripts\python.exe -m PyInstaller AlbionCraft.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

root = Path(SPECPATH)
data = [(str(root/'research'/name), 'research') for name in
        ('items.json','names.json','achievements.json','full_gamedata.json')]
data += [(str(root/'app/assets'), 'app/assets'), (str(root/'app/config'), 'app/config')]
data += [(str(root/'release_licenses'), 'licenses')]
data += [(str(root/name), '.') for name in ('LICENSE','THIRD_PARTY_NOTICES.md','USER_GUIDE.md')]
data += collect_data_files('rapidocr')
rapid_data, rapid_binaries, rapid_imports = collect_all('rapidocr')
data += rapid_data
client = root/'build/albioncraft-data-client.exe'
if not client.is_file():
    raise RuntimeError('Build the local capture client first; see docs/BUILDING.md')
data += [(str(client), 'tools/albion-data-client'),
         (str(root/'tools/albion-data-client/AODP-LICENSE.txt'), 'tools/albion-data-client')]
a = Analysis([str(root/'app/entry.py')], pathex=[str(root)], binaries=rapid_binaries,
             datas=data, hiddenimports=rapid_imports+['PySide6.QtSvg','onnxruntime'],
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtQml','PySide6.QtQuick','tkinter','matplotlib','IPython'], noarchive=False)
# Qt on Windows uses the OS ICU API. A developer machine may expose another ICU
# on PATH (e.g. an image tool); that DLL has different, version-suffixed exports.
# Use Windows' built-in ICU rather than accidentally distributing that copy.
a.binaries = [entry for entry in a.binaries if not
              (Path(entry[0]).name.lower().startswith('icu') and Path(entry[0]).suffix.lower()=='.dll')]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='AlbionCraft',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, icon=str(root/'app/assets/albioncraft.ico'),version=str(root/'scripts/windows_version.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='AlbionCraft')

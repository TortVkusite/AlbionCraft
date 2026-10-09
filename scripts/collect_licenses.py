"""Collect notices from installed Python distributions and local Go modules."""
import importlib.metadata as metadata
from pathlib import Path
import shutil
import sys
import subprocess
import stat

root=Path(__file__).resolve().parents[1]
target=root/'release_licenses';target.mkdir(exist_ok=True)
def copy_notice(source,output):
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():output.chmod(stat.S_IREAD|stat.S_IWRITE)
    shutil.copyfile(source,output)
if (root/'licenses').is_dir():shutil.copytree(root/'licenses',target,dirs_exist_ok=True)
rows=[]
for dist in metadata.distributions():
    name=dist.metadata['Name'];version=dist.version
    rows.append(f'{name} {version}')
    for file in dist.files or []:
        if any(part.lower().startswith(('license','licence','copying','notice','copyright')) for part in file.parts):
            source=dist.locate_file(file)
            if source.is_file():
                output=target/'python'/name/Path(str(file))
                copy_notice(source,output)
license_path=Path(sys.base_prefix)/'LICENSE.txt'
if license_path.is_file():shutil.copy2(license_path,target/'PYTHON-LICENSE.txt')
go=shutil.which('go') or str(root/'tools/dev/go/bin/go.exe')
if Path(go).is_file():
    go_root=Path(subprocess.check_output([go,'env','GOROOT'],text=True).strip())
    if (go_root/'LICENSE').is_file():shutil.copy2(go_root/'LICENSE',target/'GO-LICENSE.txt')
modules=root/'build/go-modules.txt'
if modules.is_file():
    for line in sorted(set(modules.read_text(encoding='utf-8-sig').splitlines())):
        folder=Path(line.strip())
        if not folder.is_dir():continue
        label=folder.name
        for source in folder.rglob('*'):
            if source.is_file() and source.name.lower().startswith(('license','licence','copying','notice','copyright')):
                output=target/'go'/label/source.relative_to(folder)
                copy_notice(source,output)
(target/'DEPENDENCIES.txt').write_text('\n'.join(sorted(rows))+'\n',encoding='utf-8')
print(f'Collected {sum(p.is_file() for p in target.rglob("*"))} license/notice files')

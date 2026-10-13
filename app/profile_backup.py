"""Private profile backups with SQLite snapshots and staged restore."""
import json,os,sqlite3,tempfile,zipfile,hashlib
from pathlib import Path,PurePosixPath
from datetime import datetime,timezone

FILES={'settings.json','player.sqlite','prices.sqlite'}
REGIONS={'europe','east','west'}

def valid_name(name):
    parts=PurePosixPath(name).parts
    return '\\' not in name and (parts==('app_preferences.json',) or len(parts)==2 and parts[0] in REGIONS and parts[1] in FILES)

def backup(base,target):
    from .regions import region_root
    base=Path(base);manifest={}
    with tempfile.TemporaryDirectory(prefix='albioncraft-backup-') as folder:
        stage=Path(folder)
        for region in sorted(REGIONS):
            root=base if region=='europe' else base/'servers'/region
            for name in FILES:
                source=root/name
                if not source.is_file():continue
                dest=stage/region/name;dest.parent.mkdir(parents=True,exist_ok=True)
                if name.endswith('.sqlite'):
                    src=sqlite3.connect(source,timeout=10);out=sqlite3.connect(dest)
                    try:src.backup(out)
                    finally:src.close();out.close()
                else:dest.write_bytes(source.read_bytes())
        if (base/'app_preferences.json').is_file():(stage/'app_preferences.json').write_bytes((base/'app_preferences.json').read_bytes())
        files=[p for p in stage.rglob('*') if p.is_file()]
        for p in files:manifest[p.relative_to(stage).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
        target=Path(target);temp=target.with_suffix('.tmp')
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as archive:
            for p in files:archive.write(p,p.relative_to(stage).as_posix())
            archive.writestr('manifest.json',json.dumps(dict(version=1,created=datetime.now(timezone.utc).isoformat(),files=manifest)))
        temp.replace(target)

def stage_restore(base,archive):
    base=Path(base);stage=base/'pending_restore';stage.mkdir(exist_ok=True)
    # Extract only validated allowlisted entries; no executable files or paths.
    values={}
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        if len(names)>12 or len(names)!=len(set(names)) or sum(i.file_size for i in z.infolist())>500_000_000:raise ValueError('Некорректный или слишком большой архив')
        manifest=json.loads(z.read('manifest.json'))
        if manifest.get('version')!=1 or set(names)!=(set(manifest['files'])|{'manifest.json'}):raise ValueError('Неверный формат резервной копии')
        for name,digest in manifest['files'].items():
            if not valid_name(name):raise ValueError('Недопустимый путь в резервной копии')
            value=z.read(name)
            if hashlib.sha256(value).hexdigest()!=digest:raise ValueError('Повреждённая резервная копия')
            if name.endswith('.json'):
                if not isinstance(json.loads(value),dict):raise ValueError('Неверные настройки')
            values[name]=value
    # Validate every database before staging any replacement.
    with tempfile.TemporaryDirectory(prefix='albioncraft-validate-') as folder:
        for name,value in values.items():
            if not name.endswith('.sqlite'):continue
            path=Path(folder)/'validate.sqlite';path.write_bytes(value);db=sqlite3.connect(path)
            try:
                if db.execute('PRAGMA quick_check').fetchone()[0]!='ok' or db.execute("SELECT count(*) FROM sqlite_master WHERE type IN ('trigger','view')").fetchone()[0]:raise ValueError('Неверная база данных')
            finally:db.close()
    for name,value in values.items():
        dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(value)
    checkpoint=stage/'checkpoint.json'
    if checkpoint.exists():checkpoint.unlink()
    (stage/'ready.json').write_text(json.dumps(list(values)),encoding='utf-8')

def apply_restore(base):
    base=Path(base);stage=base/'pending_restore';ready=stage/'ready.json'
    if not ready.is_file():return False
    names=json.loads(ready.read_text(encoding='utf-8'))
    if not all(valid_name(name) for name in names):raise ValueError('Некорректное восстановление')
    # Keep a recoverable copy of the pre-restore state.
    from .regions import preferences
    checkpoint=stage/'checkpoint.json'
    if not checkpoint.is_file():
        backup(base,base/'before-restore.zip')
        checkpoint.write_text(json.dumps(dict(desktop=preferences(base).get('desktop',{}))),encoding='utf-8')
    desktop=json.loads(checkpoint.read_text(encoding='utf-8')).get('desktop',{})
    for name in names:
        parts=PurePosixPath(name).parts
        dest=base/name if len(parts)==1 else (base if parts[0]=='europe' else base/'servers'/parts[0])/parts[1]
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.suffix=='.sqlite':
            for suffix in ('-wal','-shm'):
                side=Path(str(dest)+suffix)
                if side.is_file():side.unlink()
        value=(stage/name).read_bytes()
        if name=='app_preferences.json':
            options=json.loads(value);options['desktop']=desktop;value=json.dumps(options,ensure_ascii=False).encode('utf-8')
        temporary=dest.with_suffix(dest.suffix+'.restore.tmp');temporary.write_bytes(value);temporary.replace(dest)
    # Restoring data cannot opt the user into Windows startup/capture.
    from .regions import save_preferences
    save_preferences(base,desktop=desktop);ready.unlink();checkpoint.unlink();return True

def diagnostic(base):
    from .version import __version__
    from PySide6.QtCore import qVersion
    result=dict(app='AlbionCraft',version=__version__,qt=qVersion(),created=datetime.now(timezone.utc).isoformat(),profiles={})
    base=Path(base)
    for region in REGIONS:
        root=base if region=='europe' else base/'servers'/region;tables={}
        for name in ('player.sqlite','prices.sqlite'):
            if not (root/name).is_file():continue
            db=sqlite3.connect(f'{(root/name).as_uri()}?mode=ro',uri=True)
            try:
                counts={}
                for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                    allowed={'player_nodes','journal','trip_stock','trip_runs','trip_run_revisions','trip_reservations','trip_stock_watch','trip_stock_receipts','trip_bank_scans','requests','observations','stream_orders','local_quotes','local_histories','price_history','volume_history','order_history','production_bonuses','own_orders','own_order_events'}
                    if table in allowed:counts[table]=db.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0]
                health=db.execute('PRAGMA quick_check').fetchone()[0]
                tables[name]=dict(integrity='ok' if health=='ok' else 'failed',rows=counts)
            finally:db.close()
        result['profiles'][region]=tables
    return result

"""Isolated calculations with bounded lifetime and cooperative cancellation.

Pickle IPC is exclusively between this app and its child, in a private temporary
directory. These files are not imports and must never accept downloaded input.
"""
import os
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path
from PySide6.QtCore import QThread, Signal


class ProcessWorker(QThread):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, kind, payload, parent=None, timeout=120):
        super().__init__(parent)
        from .i18n import get_language
        self.kind = kind
        self.payload = dict(payload, language=get_language())
        self.timeout = timeout

    def run(self):
        import time
        from .paths import resource_root
        process = None
        try:
            with tempfile.TemporaryDirectory(prefix='albioncraft-task-') as folder:
                request = Path(folder) / 'request.pickle'
                response = Path(folder) / 'response.pickle'
                request.write_bytes(pickle.dumps((self.kind, self.payload), protocol=5))
                if self.isInterruptionRequested():
                    return
                command = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'app.entry']
                environment = dict(os.environ)
                # Avoid multiple numerical libraries each creating a full CPU pool.
                environment.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
                process = subprocess.Popen(command + ['--task-worker', str(request), str(response)],
                    cwd=str(resource_root()), env=environment,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = time.monotonic() + self.timeout
                while process.poll() is None:
                    if self.isInterruptionRequested():
                        process.terminate()
                        process.wait(timeout=5)
                        return
                    if time.monotonic() > deadline:
                        raise TimeoutError('Расчёт превысил допустимое время. Уменьши набор или значения и повтори.')
                    self.msleep(20)
                if self.isInterruptionRequested():
                    return
                if not response.is_file():
                    raise RuntimeError('Процесс расчёта завершился без результата. Предыдущие данные сохранены.')
                result = pickle.loads(response.read_bytes())
                if process.returncode or 'error' in result:
                    raise RuntimeError(result.get('error', 'Ошибка процесса расчёта'))
                self.ready.emit(result['result'])
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            self.payload=None


def task(kind, data):
    from .i18n import set_language
    set_language(data['language'])
    if kind == 'scan':
        from .scan_result import calculate_view
        return calculate_view(data)
    if kind == 'trip':
        from .trip_task import calculate_trip
        return calculate_trip(data)
    if kind == 'bonus_ocr':
        from .research_dialog import bonus_ocr
        return bonus_ocr(data)
    if kind == 'profile_data':
        from .profile_backup import backup,stage_restore,diagnostic
        import json
        if data['action']=='backup':backup(data['root'],data['path'])
        elif data['action']=='restore':
            stage_restore(data['root'],data['path']);return 'Восстановление подготовлено. Закрой AlbionCraft через «Выйти» и запусти снова.'
        elif data['action']=='report':Path(data['path']).write_text(json.dumps(diagnostic(data['root']),ensure_ascii=False,indent=2),encoding='utf-8')
        else:raise ValueError('Неизвестная операция с данными')
        return 'Сохранено.'
    if kind == 'island':
        from .island import calculate_islands
        return calculate_islands(data)
    if kind == 'island_layout':
        from .island_layout import solve_layout
        return solve_layout(data)
    if kind == 'builds':
        from .builds import evaluate
        context={}
        results=[evaluate(b,data['prices'],data['histories'],data['city'],t,e,data['quality'],
            data['recipes'],data['settings'],context) for b,t,e in data['scenarios']]
        rows=[r for r in results if (r['complete'] and (not data['budget'] or r['cost']<=data['budget'])) or (not r['complete'] and data['incomplete'])]
        rows.sort(key=lambda r:(not r['complete'],r['cost'] if data['sort']=='cheap' else -r['build']['votes'],r['cost'] if r['complete'] else float('inf'),r['build']['id'],r['tier'],r['enchantment']))
        return dict(rows=rows,count=len(results),complete=sum(r['complete'] for r in results))
    if kind == 'fame':
        from .fame_optimizer import solve_groups
        return solve_groups(data['groups'],data['budget'])
    if kind == 'recommendations':
        from .recommendations import build_recommendations
        return build_recommendations(data['rows'],data['settings'])
    raise ValueError('Unknown calculation')


def child(request, response):
    try:
        kind, data = pickle.loads(Path(request).read_bytes())
        result = {'result': task(kind, data)}
        code = 0
    except Exception as exc:
        result = {'error': str(exc)}
        code = 1
    Path(response).write_bytes(pickle.dumps(result, protocol=5))
    return code

"""Executable entry point, including file-based IPC for the isolated solver."""
import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) == 4 and sys.argv[1] == '--task-worker':
        from app.background import child
        return child(sys.argv[2], sys.argv[3])
    if len(sys.argv) == 4 and sys.argv[1] == '--fame-worker':
        output = Path(sys.argv[3])
        try:
            from app.fame_optimizer import solve_groups
            data = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
            output.write_text(json.dumps(solve_groups(data['groups'], data['budget']), ensure_ascii=False), encoding='utf-8')
            return 0
        except Exception as exc:
            output.write_text(json.dumps({'error': str(exc)}, ensure_ascii=False), encoding='utf-8')
            return 1
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        from app.release_smoke import check
        return check(Path(sys.argv[2]))
    if len(sys.argv)>1:
        return 2
    from app.main import main as run
    return run()


if __name__ == '__main__':
    sys.exit(main())

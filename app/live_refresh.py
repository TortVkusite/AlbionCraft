"""Coalesce capture bursts and read market databases outside the UI process."""
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, Signal
from .background import ProcessWorker


def snapshot(data):
    from .cache import Cache
    from .local_market import LocalStore, merge_local
    from .market_stream import supplement
    path=Path(data['path']);prices=data['prices']
    histories={(h['item_id'],h['location'],h['quality']):h for h in data['histories']}
    if data['live']:
        cache=Cache(path)
        try:prices=supplement(prices,cache.stream_prices(data['ids']))
        finally:cache.close()
    if data['local']:
        store=LocalStore(path)
        try:
            prices=merge_local(prices,store.prices())
            for h in store.histories(data['history_ids']):histories[(h['item_id'],h['location'],h['quality'])]=h
        finally:store.close()
    return dict(prices=prices,histories=list(histories.values()),context=data['context'])


class LiveRefresh(QObject):
    ready=Signal(object)
    failed=Signal(str)

    def __init__(self,parent=None,delay=250):
        super().__init__(parent);self.worker=None;self.latest=None;self.pending=False;self.stopped=False
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(delay);self.timer.timeout.connect(self.start)

    def request(self,data):
        if self.stopped:return
        self.latest=data;self.pending=True
        # Keep one job and one newest request. A continuous stream must not
        # postpone the first refresh or launch a process for every packet.
        if self.worker is None and not self.timer.isActive():self.timer.start()

    def start(self):
        if self.stopped or self.worker is not None or not self.pending:return
        self.pending=False;self.worker=ProcessWorker('live_market',self.latest,self,timeout=30)
        self.worker.ready.connect(lambda data:self.ready.emit(data) if not self.stopped else None)
        self.worker.failed.connect(lambda message:self.failed.emit(message) if not self.stopped else None)
        self.worker.finished.connect(self.finished);self.worker.start()

    def finished(self):
        worker=self.sender()
        if worker is self.worker:self.worker=None
        if worker:worker.deleteLater()
        if self.pending and not self.stopped:self.timer.start()

    def stop(self):
        self.stopped=True;self.pending=False;self.timer.stop()
        if self.worker:self.worker.requestInterruption()

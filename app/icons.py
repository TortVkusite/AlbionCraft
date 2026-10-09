from pathlib import Path
from urllib.parse import quote
from PySide6.QtCore import QObject,Signal,QUrl
from PySide6.QtGui import QIcon,QPixmap
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkRequest

class Icons(QObject):
    ready=Signal(str)
    def __init__(self,root,parent=None):
        super().__init__(parent); self.root=root/'icons'; self.root.mkdir(exist_ok=True)
        self.network=QNetworkAccessManager(self); self.pending=set(); self.icons={}; self.failed=set()
    def get(self,uid,quality=1):
        key=uid+'__'+str(quality)
        if key in self.icons:return self.icons[key]
        path=self.root/(key+'.png')
        if path.exists():
            icon=QIcon(str(path))
            if not icon.isNull(): self.icons[key]=icon;return icon
        if key not in self.pending and key not in self.failed:
            self.pending.add(key)
            request=QNetworkRequest(QUrl('https://render.albiononline.com/v1/item/'+quote(uid,safe='@')+'.png?size=96&quality='+str(quality)))
            request.setTransferTimeout(15000)
            reply=self.network.get(request)
            reply.finished.connect(lambda:self.done(reply,key,path))
        return QIcon()
    def done(self,reply,key,path):
        pixmap=QPixmap(); payload=bytes(reply.readAll())
        if reply.error()==reply.NetworkError.NoError and pixmap.loadFromData(payload):
            try:path.write_bytes(payload)
            except OSError:pass
            self.icons[key]=QIcon(pixmap); self.ready.emit(key)
        else:self.failed.add(key)
        self.pending.discard(key);reply.deleteLater()

"""Download official packages on demand; install the client locally, launch Npcap's wizard."""
import base64,gzip,hashlib,os,subprocess
from pathlib import Path
from urllib.request import Request,urlopen
from PySide6.QtCore import QThread,Signal

PACKAGES={
    'client':('update-windows-amd64.exe.gz','https://github.com/ao-data/albiondata-client/releases/download/0.1.59/update-windows-amd64.exe.gz','21edb421b28d38104822317d623d57bf8784fbc8deb219c99dfad06dcd9d5c42'),
    'npcap':('npcap-1.89.exe','https://npcap.com/dist/npcap-1.89.exe','8aed85e900d783d1308506e919587d3e540451947af8a82f2d04f819e44305cc'),
}

def capture_ready():
    # The client links wpcap.dll; Npcap's isolated subdirectory alone does not guarantee compatibility.
    return (Path(os.environ.get('WINDIR','C:/Windows'))/'System32/wpcap.dll').is_file()

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def download_package(kind,folder,progress=lambda text:None):
    name,url,expected=PACKAGES[kind];folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);target=folder/name
    if target.is_file() and digest(target)==expected:return target
    part=target.with_suffix(target.suffix+'.part');total=0
    try:
        with urlopen(Request(url,headers={'User-Agent':'AlbionCraft-local/setup'}),timeout=30) as response,part.open('wb') as out:
            length=int(response.headers.get('Content-Length','0'))
            while chunk:=response.read(262144):
                total+=len(chunk)
                if total>100_000_000:raise ValueError('Размер загрузки превышает ожидаемый')
                out.write(chunk)
                progress(f'Скачиваю {name}: '+(f'{total*100//length}%' if length else f'{total//1024} КБ'))
        if digest(part)!=expected:raise ValueError('Контрольная сумма загрузки не совпала. Установка остановлена.')
        part.replace(target);return target
    finally:
        if part.exists():part.unlink()

def install_client(archive,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);target=folder/'albiondata-client.exe'
    data=gzip.decompress(Path(archive).read_bytes())
    if not data.startswith(b'MZ') or len(data)>120_000_000:raise ValueError('Неверный формат программы клиента')
    if target.exists() and target.read_bytes()==data:return target
    part=target.with_suffix('.exe.part');part.write_bytes(data);part.replace(target);return target

def run_driver_installer(path):
    # Free Npcap does not permit a silent installation. User accepts its license in the official wizard.
    literal="'"+str(Path(path).resolve()).replace("'","''")+"'"
    script=f"$ErrorActionPreference='Stop'; $p=Start-Process -FilePath {literal} -ArgumentList '/winpcap_mode=enforced' -Verb RunAs -WindowStyle Normal -Wait -PassThru; exit $p.ExitCode"
    encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode==3010:raise ValueError('Npcap установлен. Перезагрузи Windows, затем снова нажми кнопку подключения.')
    if result.returncode!=0:raise ValueError('Установка Npcap отменена или не завершилась. Нажми кнопку снова, когда будешь готов подтвердить установку.')

class SetupWorker(QThread):
    progress=Signal(str)
    ready=Signal(str)
    failed=Signal(str)
    def __init__(self,root):super().__init__();self.root=Path(root)
    def run(self):
        try:
            archive=download_package('client',self.root/'installers',self.progress.emit)
            self.progress.emit('Устанавливаю Albion Data Client в папку приложения…')
            executable=install_client(archive,self.root/'tools'/'albion-data-client')
            from .paths import resource_root
            enhanced=resource_root()/'tools'/'albion-data-client'/'albioncraft-data-client.exe'
            if enhanced.is_file():executable=enhanced
            if not capture_ready():
                installer=download_package('npcap',self.root/'installers',self.progress.emit)
                self.progress.emit('Открыт мастер Npcap: подтверди запрос Windows, затем I Agree → Install → Finish. Режим совместимости уже выбран.')
                run_driver_installer(installer)
                if not capture_ready():raise ValueError('Npcap не готов. Заверши установку с режимом WinPcap; если Windows просит перезагрузку, перезагрузи её.')
            self.ready.emit(str(executable))
        except Exception as exc:self.failed.emit(str(exc))

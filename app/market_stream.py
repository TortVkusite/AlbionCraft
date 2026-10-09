"""Optional public Europe NATS observations, independent of REST fetch lifecycle."""
import json
import socket
import time
from datetime import datetime,timezone,timedelta
from PySide6.QtCore import QThread,Signal
from .cache import Cache
from .item_ids import market_item_id

LOCATIONS={'1002':'Lymhurst','2004':'Bridgewatch','3008':'Martlock',
    '4002':'Fort Sterling','0007':'Thetford','7':'Thetford','3005':'Caerleon'}

def normalized_order(data,now=None):
    now=now or datetime.now(timezone.utc)
    try:
        city=LOCATIONS.get(str(data['LocationId']))
        uid=market_item_id(data['ItemTypeId'],data.get('EnchantmentLevel',0))
        side={'offer':'sell_price_min','request':'buy_price_max'}.get(data['AuctionType'])
        price=int(data['UnitPriceSilver']);amount=int(data['Amount']);quality=int(data['QualityLevel'])
        expiry=datetime.fromisoformat(data['Expires'].replace('Z','+00:00'))
        if expiry.tzinfo is None:expiry=expiry.replace(tzinfo=timezone.utc)
        if not city or not side or price<=0 or amount<=0 or quality not in range(1,6) or expiry<=now:return None
        return (str(data['Id']),uid,city,quality,side,price,amount,now.isoformat(),expiry.astimezone(timezone.utc).isoformat())
    except (KeyError,TypeError,ValueError,AttributeError):return None

def supplement(primary,observed):
    """REST remains primary; fill missing sides only, retain separate observations."""
    from .models import quote
    result={(p['item_id'],p['city'],p['quality']):dict(p) for p in primary}
    for p in observed:
        key=(p['item_id'],p['city'],p['quality']);r=result.setdefault(key,dict(item_id=key[0],city=key[1],quality=key[2]))
        r['nats_observations']=p
        for side in ('sell_price_min','buy_price_max'):
            value,_,status=quote(r,side,None)
            if value is None or 'будущем' in status:
                if p.get(side):
                    r[side]=p[side];r[side+'_date']=p[side+'_date'];r[side+'_source']='AODP NATS: наблюдавшийся ордер'
    return list(result.values())

class OrderStream(QThread):
    status=Signal(str)
    updated=Signal()
    def __init__(self,path,ids):
        super().__init__();self.path=path;self.ids=set(ids);self.total=0
    def run(self):
        cache=Cache(self.path);pending=[];backoff=2
        try:
            while not self.isInterruptionRequested():
                try:
                    self.status.emit('NATS: подключение…')
                    with socket.create_connection(('nats.albion-online-data.com',34222),timeout=5) as sock:
                        sock.settimeout(1)
                        payload=json.dumps({'verbose':False,'user':'public','pass':'thenewalbiondata','name':'AlbionCraft-Europe'})
                        sock.sendall(('CONNECT '+payload+'\r\nSUB marketorders.deduped 1\r\nPING\r\n').encode())
                        buffer=b'';size=None;flush=time.monotonic();ping=flush;backoff=2
                        while not self.isInterruptionRequested():
                            try:
                                incoming=sock.recv(65536)
                                if not incoming:raise ConnectionError('Сервер закрыл соединение')
                                buffer+=incoming
                            except socket.timeout:pass
                            while True:
                                if size is not None:
                                    if len(buffer)<size+2:break
                                    body=buffer[:size];buffer=buffer[size+2:];size=None
                                    try:
                                        data=json.loads(body)
                                        for entry in data if isinstance(data,list) else data.get('Orders',[data]) if isinstance(data,dict) else []:
                                            order=normalized_order(entry)
                                            if order and order[1] in self.ids:pending.append(order)
                                    except (ValueError,TypeError):pass
                                    continue
                                if b'\r\n' not in buffer:break
                                line,buffer=buffer.split(b'\r\n',1)
                                if line==b'PING':sock.sendall(b'PONG\r\n')
                                elif line==b'PONG':self.status.emit(f'NATS: подключён • ордеров сохранено: {self.total}')
                                elif line.startswith(b'-ERR'):raise ConnectionError(line.decode(errors='replace'))
                                elif line.startswith(b'MSG '):
                                    size=int(line.split()[-1])
                                    if size>4_000_000:raise ValueError('NATS message too large')
                            if time.monotonic()-flush>=2:
                                if pending:
                                    cache.save_stream_orders(pending);self.total+=len(pending);pending=[];self.updated.emit()
                                    self.status.emit(f'NATS: подключён • ордеров сохранено: {self.total}')
                                flush=time.monotonic()
                            if time.monotonic()-ping>=20:sock.sendall(b'PING\r\n');ping=time.monotonic()
                except (OSError,ValueError,ConnectionError) as exc:
                    self.status.emit('NATS недоступен; REST работает • '+str(exc))
                    end=time.monotonic()+backoff
                    while time.monotonic()<end and not self.isInterruptionRequested():self.msleep(100)
                    backoff=min(backoff*2,60)
        finally:
            if pending:cache.save_stream_orders(pending)
            cache.close()

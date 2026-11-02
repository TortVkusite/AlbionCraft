"""Durable, bounded market-only mailbox. No profile or raw capture export."""
import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import iroh

MAX_RECORD = 900_000
MAX_EVENTS = 10_000
MAX_BYTES = 64 * 1024 * 1024
TTL = timedelta(hours=24)


def now():
    return datetime.now(timezone.utc)


def stamp(value):
    if not isinstance(value, str) or len(value)>40:
        raise ValueError('Invalid timestamp')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Missing timezone')
    return dt.astimezone(timezone.utc)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def protect(data, decrypt=False):
    """Keep secrets user-bound on Windows; portable test environments use mode 0600."""
    if os.name != 'nt':
        return data
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    dest = Blob()
    api = ctypes.windll.crypt32
    if decrypt:
        ok = api.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(dest))
    else:
        ok = api.CryptProtectData(ctypes.byref(source), 'AlbionCraft peer secrets', None, None, None, 1, ctypes.byref(dest))
    if not ok:
        raise OSError('Cannot protect peer credentials')
    try:
        return ctypes.string_at(dest.data, dest.size)
    finally:
        ctypes.windll.kernel32.LocalFree(dest.data)


def validate_market(kind, data, observed):
    from .models import CITIES
    if not isinstance(data, dict):
        raise ValueError('Invalid market record')
    common = {'item', 'city', 'quality'}
    if not isinstance(data.get('item'), str) or not re.fullmatch(r'[A-Z0-9_@]{1,160}', data['item']):
        raise ValueError('Invalid item')
    if data.get('city') not in CITIES or type(data.get('quality')) is not int or data['quality'] not in range(1, 6):
        raise ValueError('Invalid market')
    if kind == 'orders':
        if set(data) != common | {'side', 'orders'} or data['side'] not in ('sell_price_min', 'buy_price_max'):
            raise ValueError('Invalid order page')
        orders = data['orders']
        if not isinstance(orders, list) or not 1 <= len(orders) <= 5000:
            raise ValueError('Invalid page size')
        ids = set()
        for o in orders:
            if not isinstance(o, dict) or set(o) != {'id','price','amount','expires'}:
                raise ValueError('Invalid order')
            if not isinstance(o['id'], str) or not 1 <= len(o['id']) <= 160 or o['id'] in ids:
                raise ValueError('Invalid order id')
            ids.add(o['id'])
            if any(type(o[k]) is not int or not 0 < o[k] <= 10**15 for k in ('price','amount')):
                raise ValueError('Invalid price/amount')
            if stamp(o['expires']) <= observed:
                raise ValueError('Expired order')
        suffix = data['side']
    elif kind == 'history':
        if set(data) != common | {'period_days','bucket_hours','points'}:
            raise ValueError('Invalid history')
        period, bucket = data['period_days'], data['bucket_hours']
        if type(period) is not int or type(bucket) is not int or (period,bucket) not in ((1,1),(7,6),(28,24)):
            raise ValueError('Invalid history window')
        if not isinstance(data['points'], list) or not 1 <= len(data['points']) <= 1000:
            raise ValueError('Invalid history size')
        dates=set()
        for p in data['points']:
            if not isinstance(p,dict) or set(p) != {'timestamp','item_count','avg_price'}:
                raise ValueError('Invalid history point')
            dt=stamp(p['timestamp'])
            if dt in dates or not observed-timedelta(days=period,hours=bucket) <= dt <= observed:
                raise ValueError('Invalid history date')
            dates.add(dt)
            if type(p['item_count']) is not int or not 0 <= p['item_count'] <= 10**15:
                raise ValueError('Invalid volume')
            if type(p['avg_price']) not in (int,float) or not 0 <= p['avg_price'] <= 10**15:
                raise ValueError('Invalid history price')
        suffix = str(period)
    else:
        raise ValueError('Unknown record kind')
    return ':'.join((kind, data['item'], data['city'], str(data['quality']), suffix))


class PeerStore:
    def __init__(self, root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.root/'peer-sync.sqlite',timeout=0.25)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY,value BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS peers (id TEXT PRIMARY KEY,ticket TEXT NOT NULL,blocked INTEGER DEFAULT 0,last_seen TEXT);
        CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY,slot TEXT NOT NULL,observed TEXT NOT NULL,origin TEXT NOT NULL,seq INTEGER NOT NULL,body BLOB NOT NULL,received TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS event_slot ON events(slot,observed,id);
        CREATE TABLE IF NOT EXISTS receipts (peer TEXT,id TEXT,at TEXT,PRIMARY KEY(peer,id));
        CREATE TABLE IF NOT EXISTS captured (slot TEXT PRIMARY KEY,digest TEXT);
        ''')
        self.db.commit()

    def close(self):
        self.db.close()

    def get(self,key,default=None):
        row=self.db.execute('SELECT value FROM config WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self,key,value):
        with self.db:self.db.execute('INSERT OR REPLACE INTO config VALUES(?,?)',(key,json.dumps(value)))

    def identity(self):
        if hasattr(self,'_identity'):return self._identity
        data=self.get('identity')
        if data is None:
            data=base64.b64encode(protect(iroh.SecretKey.generate().to_bytes())).decode()
            self.set('identity',data)
        self._identity=iroh.SecretKey.from_bytes(protect(base64.b64decode(data),True))
        if self.get('identity_public') is None:self.set('identity_public',str(self._identity.public()))
        return self._identity

    def group(self):
        data=self.get('group')
        return json.loads(protect(base64.b64decode(data),True)) if data else None

    def set_group(self,group):
        old=self.group()
        if old and old['id'] != group['id']:
            raise ValueError('Leave the current group first')
        self.set('group',base64.b64encode(protect(canonical(group))).decode())

    def create_group(self):
        group=self.group()
        if group is None:
            group=dict(id=secrets.token_hex(16),key=secrets.token_hex(32))
            self.set_group(group)
        return group

    def leave(self):
        self.set('enabled',False)
        with self.db:
            for table in ('peers','events','receipts','captured'):
                self.db.execute('DELETE FROM '+table)
            self.db.execute("DELETE FROM config WHERE key IN ('group','ticket')")

    def add_peer(self,ticket):
        if not isinstance(ticket,str) or len(ticket)>4096:
            raise ValueError('Invalid peer ticket')
        addr=iroh.EndpointTicket.from_string(ticket).endpoint_addr()
        peer=str(addr.id())
        if peer==str(self.identity().public()):return peer
        with self.db:
            if self.db.execute('SELECT count(*) FROM peers').fetchone()[0]>=32 and not self.db.execute('SELECT 1 FROM peers WHERE id=?',(peer,)).fetchone():
                raise ValueError('Peer limit reached (32)')
            self.db.execute('INSERT INTO peers(id,ticket) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET ticket=excluded.ticket',(peer,ticket))
        return peer

    def peers(self):
        return [dict(id=r[0],ticket=r[1],blocked=bool(r[2]),last_seen=r[3]) for r in self.db.execute('SELECT * FROM peers ORDER BY id')]

    def blocked(self,peer):
        return bool(self.db.execute('SELECT 1 FROM peers WHERE id=? AND blocked=1',(peer,)).fetchone())

    def invitation(self):
        ticket=self.get('ticket')
        if not ticket:raise ValueError('Start exchange before copying an invitation')
        return 'albioncraft-peer:'+base64.urlsafe_b64encode(canonical(dict(v=1,group=self.create_group(),ticket=ticket))).decode()

    def join(self,text):
        if not isinstance(text,str) or not text.startswith('albioncraft-peer:') or len(text)>8192:
            raise ValueError('Invalid invitation')
        value=json.loads(base64.b64decode(text.split(':',1)[1],altchars=b'-_',validate=True))
        group=value['group']
        if value.get('v')!=1 or set(group)!={'id','key'} or not re.fullmatch('[0-9a-f]{32}',group['id']) or not re.fullmatch('[0-9a-f]{64}',group['key']):
            raise ValueError('Invalid group')
        iroh.EndpointTicket.from_string(value['ticket'])
        self.set_group(group);self.add_peer(value['ticket'])

    def publish(self,region,kind,data,observed):
        group=self.group()
        if not group:raise ValueError('No group')
        from .regions import region_key
        region=region_key(region);dt=stamp(observed)
        slot=region+':'+validate_market(kind,data,dt)
        if not now()-TTL <= dt <= now()+timedelta(minutes=2):raise ValueError('Stale observation')
        key=self.identity()
        with self.db:
            seq=self.get('sequence',0)+1
            self.db.execute('INSERT OR REPLACE INTO config VALUES(?,?)',('sequence',json.dumps(seq)))
            body=dict(v=1,group=group['id'],origin=str(key.public()),seq=seq,region=region,kind=kind,observed=dt.isoformat(),data=data)
            body['signature']=key.sign(canonical(body)).to_bytes().hex()
            body['id']=hashlib.sha256(canonical(body)).hexdigest()
            raw=canonical(body)
            if len(raw)>MAX_RECORD:raise ValueError('Market page too large')
            self._insert(body,raw,slot)
        return body

    def _insert(self,event,raw,slot):
        self.db.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?)',(event['id'],slot,event['observed'],event['origin'],event['seq'],raw,now().isoformat()))

    def receive(self,event):
        raw=canonical(event)
        if len(raw)>MAX_RECORD or not isinstance(event,dict) or set(event)!={'v','group','origin','seq','region','kind','observed','data','signature','id'}:
            raise ValueError('Invalid envelope')
        group=self.group()
        if not group or event['group']!=group['id'] or event['v']!=1:
            raise ValueError('Wrong group/protocol')
        if type(event['seq']) is not int or not 0 < event['seq'] < 2**63:
            raise ValueError('Invalid sequence')
        unsigned=dict(event);event_id=unsigned.pop('id')
        if hashlib.sha256(canonical(unsigned)).hexdigest()!=event_id:raise ValueError('Invalid message id')
        signature=unsigned.pop('signature')
        iroh.EndpointId.from_string(event['origin']).verify(canonical(unsigned),iroh.Signature.from_bytes(bytes.fromhex(signature)))
        from .regions import region_key
        if region_key(event['region'])!=event['region']:raise ValueError('Invalid server')
        dt=stamp(event['observed'])
        if not now()-TTL <= dt <= now()+timedelta(minutes=2):raise ValueError('Stale observation')
        slot=event['region']+':'+validate_market(event['kind'],event['data'],dt)
        with self.db:
            exists=self.has(event_id)
            self._insert(event,raw,slot)
        return not exists

    def has(self,event_id):
        return self.db.execute('SELECT 1 FROM events WHERE id=?',(event_id,)).fetchone() is not None

    def inventory(self):
        # Advertise only the latest version per market page, across all authors.
        return [r[0] for r in self.db.execute('''SELECT id FROM (
          SELECT id,observed,ROW_NUMBER() OVER(PARTITION BY slot ORDER BY observed DESC,id DESC) AS n FROM events
          WHERE observed>=?) WHERE n=1 ORDER BY id''',((now()-TTL).isoformat(),))]

    def event(self,event_id):
        row=self.db.execute('SELECT body FROM events WHERE id=?',(event_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def ack(self,peer,event_id):
        with self.db:self.db.execute('INSERT OR REPLACE INTO receipts VALUES(?,?,?)',(peer,event_id,now().isoformat()))

    def prune(self):
        with self.db:
            self.db.execute('DELETE FROM events WHERE observed<?',((now()-TTL).isoformat(),))
            # Superseded pages need not occupy an offline delivery queue forever.
            self.db.execute('DELETE FROM events WHERE id NOT IN (SELECT id FROM (SELECT id,ROW_NUMBER() OVER(PARTITION BY slot ORDER BY observed DESC,id DESC) n FROM events) WHERE n=1)')
            while True:
                count,size=self.db.execute('SELECT count(*),coalesce(sum(length(body)),0) FROM events').fetchone()
                if count<=MAX_EVENTS and size<=MAX_BYTES:break
                self.db.execute('DELETE FROM events WHERE id IN (SELECT id FROM events ORDER BY observed LIMIT 100)')
            self.db.execute('DELETE FROM receipts WHERE id NOT IN (SELECT id FROM events)')

    def stats(self):
        count,size=self.db.execute('SELECT count(*),coalesce(sum(length(body)),0) FROM events').fetchone()
        return dict(records=count,bytes=size,peers=len(self.peers()),identity=str(self.identity().public()))

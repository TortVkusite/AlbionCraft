"""Encrypted Iroh transport; inventories first, durable receive before ACK."""
import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import sqlite3
import struct
import time

import iroh

from .peer_store import PeerStore, canonical, now
from .peer_market import CapturePublisher

ALPN=b'albioncraft/market-sync/1'
MAX_FRAME=1_000_000


async def send(stream,value):
    data=canonical(value)
    if len(data)>MAX_FRAME:raise ValueError('Frame too large')
    await asyncio.wait_for(stream.write_all(struct.pack('!I',len(data))+data),15)


async def receive(stream):
    header=await asyncio.wait_for(stream.read_exact(4),20)
    size=struct.unpack('!I',header)[0]
    if not 0<size<=MAX_FRAME:raise ValueError('Frame too large')
    data=await asyncio.wait_for(stream.read_exact(size),20)
    value=json.loads(data)
    if not isinstance(value,dict):raise ValueError('Invalid protocol message')
    return value


class PeerNode:
    def __init__(self,root,region='europe',local_only=False,status=lambda value:None,changed=lambda:None):
        self.store=PeerStore(root);self.region=region;self.local_only=local_only
        self.status=status;self.changed=changed;self.endpoint=None;self.tasks=set();self.dialing=set();self.inflight=set()
        self.received=0;self.sent=0;self.stop_event=asyncio.Event();self.publisher=CapturePublisher(self.store,self.store.root/'prices.sqlite',region)
        self.active=set();self.last_errors={}
        self.dirty=False

    async def start(self):
        if not self.store.group():raise ValueError('Create or join a group first')
        self.group=self.store.group()
        preset=iroh.preset_minimal() if self.local_only else iroh.preset_n0()
        self.endpoint=await iroh.Endpoint.bind(iroh.EndpointOptions(preset=preset,secret_key=self.store.identity().to_bytes(),
            alpns=[ALPN],bind_addr='127.0.0.1:0' if self.local_only else None))
        self.update_ticket()
        self.spawn(self.accept_loop());self.spawn(self.maintenance())

    def spawn(self,coro):
        task=asyncio.create_task(coro);self.tasks.add(task);task.add_done_callback(self.tasks.discard)
        return task

    def update_ticket(self):
        ticket=str(iroh.EndpointTicket.from_addr(self.endpoint.addr()))
        if self.store.get('ticket')!=ticket:self.store.set('ticket',ticket)

    def proof(self,nonce,role,client,server):
        return hmac.new(bytes.fromhex(self.group['key']),canonical([self.group['id'],nonce,role,client,server]),hashlib.sha256).hexdigest()

    def blocked(self,peer):
        return self.store.blocked(peer)

    async def accept_loop(self):
        while not self.stop_event.is_set():
            incoming=await self.endpoint.accept_next()
            if incoming is None:break
            if len(self.tasks)>=40:incoming.refuse();continue
            self.spawn(self.handle_incoming(incoming))

    async def handle_incoming(self,incoming):
        conn=None
        try:
            accepting=await asyncio.wait_for(incoming.accept(),10)
            conn=await asyncio.wait_for(accepting.connect(),10)
            peer=str(conn.remote_id())
            if self.blocked(peer):return
            stream=await asyncio.wait_for(conn.accept_bi(),10)
            tx,rx=stream.send(),stream.recv();nonce=secrets.token_hex(32);own=str(self.endpoint.id())
            if await asyncio.wait_for(rx.read_exact(1),10)!=b'\x01':raise ValueError('Invalid stream prelude')
            await send(tx,dict(type='challenge',nonce=nonce,group=self.group['id']))
            auth=await receive(rx)
            if auth.get('type')!='auth' or not hmac.compare_digest(str(auth.get('proof','')),self.proof(nonce,'client',peer,own)):
                raise ValueError('Group authentication failed')
            self.learn_ticket(auth.get('ticket'),peer)
            await send(tx,dict(type='authenticated',proof=self.proof(nonce,'server',peer,own),ticket=self.store.get('ticket')))
            self.active.add(peer)
            # A stable inventory for this session avoids paging races while capture runs.
            inventory=self.store.inventory()
            for _ in range(40000):
                if self.blocked(peer):break
                request=await receive(rx);kind=request.get('type')
                if kind=='inventory':
                    offset=request.get('offset',0)
                    if type(offset) is not int or not 0<=offset<=10000:raise ValueError('Invalid inventory offset')
                    await send(tx,dict(type='inventory',ids=inventory[offset:offset+128],more=offset+128<len(inventory)))
                elif kind=='get':
                    eid=request.get('id')
                    if not isinstance(eid,str) or len(eid)!=64:raise ValueError('Invalid requested id')
                    event=self.store.event(eid) if eid in inventory else None
                    await send(tx,dict(type='event',event=event));self.sent+=bool(event)
                elif kind=='ack':
                    eid=request.get('id')
                    if eid in inventory:self.store.ack(peer,eid)
                    await send(tx,dict(type='ack'))
                elif kind=='peers':
                    await send(tx,dict(type='peers',tickets=[p['ticket'] for p in self.store.peers() if not p['blocked']][:32]))
                elif kind=='done':break
                else:raise ValueError('Unknown message')
        except asyncio.CancelledError:raise
        except Exception as exc:
            logging.debug('Peer receive: %s',type(exc).__name__)
        finally:
            if conn:
                self.active.discard(str(conn.remote_id()));conn.close(0,b'finished')

    def learn_ticket(self,ticket,expected=None):
        addr=iroh.EndpointTicket.from_string(ticket).endpoint_addr()
        if expected and str(addr.id())!=expected:raise ValueError('Peer identity mismatch')
        peer=self.store.add_peer(ticket)
        with self.store.db:self.store.db.execute('UPDATE peers SET last_seen=? WHERE id=?',(now().isoformat(),peer))

    async def pull(self,peer):
        pid=peer['id'];conn=None;self.dialing.add(pid)
        try:
            addr=iroh.EndpointTicket.from_string(peer['ticket']).endpoint_addr()
            conn=await asyncio.wait_for(self.endpoint.connect(addr,ALPN),12)
            stream=await asyncio.wait_for(conn.open_bi(),10);tx,rx=stream.send(),stream.recv()
            # Opening a QUIC stream is lazy: send a byte so the server sees it.
            await tx.write_all(b'\x01')
            hello=await receive(rx)
            if hello.get('type')!='challenge' or hello.get('group')!=self.group['id']:raise ValueError('Wrong group')
            nonce=hello['nonce']
            if not isinstance(nonce,str) or len(nonce)!=64:raise ValueError('Invalid challenge')
            own=str(self.endpoint.id())
            await send(tx,dict(type='auth',proof=self.proof(nonce,'client',own,pid),ticket=self.store.get('ticket')))
            auth=await receive(rx)
            if auth.get('type')!='authenticated' or not hmac.compare_digest(str(auth.get('proof','')),self.proof(nonce,'server',own,pid)):
                raise ValueError('Group authentication failed')
            self.learn_ticket(auth['ticket'],pid);self.active.add(pid);self.last_errors.pop(pid,None)
            offset=0
            while offset<=10000 and not self.stop_event.is_set() and not self.blocked(pid):
                await send(tx,dict(type='inventory',offset=offset));page=await receive(rx)
                ids=page.get('ids')
                if not isinstance(ids,list) or len(ids)>128 or any(not isinstance(e,str) or len(e)!=64 for e in ids):raise ValueError('Invalid inventory')
                for eid in ids:
                    if self.store.has(eid) or eid in self.inflight:continue
                    self.inflight.add(eid)
                    try:
                        await send(tx,dict(type='get',id=eid));message=await receive(rx)
                        event=message.get('event')
                        if event is None:continue
                        if event.get('id')!=eid:raise ValueError('Wrong record')
                        if self.store.receive(event):self.received+=1;self.dirty=True
                        # receive() committed before this acknowledgement is sent.
                        await send(tx,dict(type='ack',id=eid));await receive(rx)
                    finally:self.inflight.discard(eid)
                offset+=len(ids)
                if not page.get('more'):break
                if not ids:raise ValueError('Empty inventory page')
            await send(tx,dict(type='peers'));message=await receive(rx)
            tickets=message.get('tickets',[])
            if not isinstance(tickets,list) or len(tickets)>32:raise ValueError('Invalid peer list')
            for ticket in tickets:
                try:self.store.add_peer(ticket)
                except (ValueError,TypeError,iroh.IrohError):pass
            await send(tx,dict(type='done'))
        except asyncio.CancelledError:raise
        except Exception as exc:
            self.last_errors[pid]=type(exc).__name__
        finally:
            self.active.discard(pid);self.dialing.discard(pid)
            if conn:conn.close(0,b'finished')

    async def maintenance(self):
        last_sync=0;last_prune=0
        while not self.stop_event.is_set():
            try:
                self.update_ticket()
                if self.store.get('publish',True):self.publisher.poll()
                if time.monotonic()-last_prune>60:self.store.prune();last_prune=time.monotonic()
                if time.monotonic()-last_sync>3:
                    for peer in self.store.peers():
                        if not peer['blocked'] and peer['id'] not in self.dialing and len(self.dialing)<4:
                            self.spawn(self.pull(peer))
                    last_sync=time.monotonic()
                state=self.store.stats();state.update(received=self.received,sent=self.sent,active=len(self.active),errors=len(self.last_errors),
                    peer_rows=self.store.peers(),group_id=self.group['id'])
                self.status(state)
                if self.dirty:self.dirty=False;self.changed()
            except sqlite3.Error:
                pass # Retry on the next tick; never stall the GUI or lose durable state.
            await asyncio.sleep(0.5)

    async def stop(self):
        self.stop_event.set()
        for task in list(self.tasks):task.cancel()
        await asyncio.gather(*list(self.tasks),return_exceptions=True)
        if self.endpoint:await self.endpoint.close()
        self.store.close()

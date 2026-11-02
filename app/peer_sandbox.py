"""Three real encrypted peer processes, isolated profiles and real HTTP capture.

Run: .venv/Scripts/python.exe scripts/peer_sandbox.py
No public traffic: endpoints use Iroh's minimal preset and loopback tickets.
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.peer_store import PeerStore,now


def write(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data),encoding='utf-8');temp.replace(path)


async def node_main(root):
    from app.peer_network import PeerNode
    from app.local_market import make_server
    root=Path(root)
    # Same ingest parser as Albion Data Client, separate ephemeral loopback port.
    server=make_server(root/'prices.sqlite','sandbox',lambda n:None,port=0,region='europe')
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    node=PeerNode(root,local_only=True)
    try:
        await node.start()
        while not (root/'stop').exists():
            write(root/'state.json',dict(ticket=node.store.get('ticket'),invitation=node.store.invitation(),
                stats=node.store.stats(),errors=node.last_errors,port=server.server_address[1]))
            await asyncio.sleep(.2)
    finally:
        await node.stop();server.shutdown();thread.join(3);server.server_close()


def wait_for(predicate,description,timeout=25,cancel=lambda:False):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if cancel():raise InterruptedError('Sandbox cancelled')
        try:
            result=predicate()
            if result:return result
        except (OSError,ValueError,KeyError):pass
        time.sleep(.1)
    raise AssertionError('Timeout: '+description)


def read(root):return json.loads((root/'state.json').read_text(encoding='utf-8'))


def ingest(root,price,order_id='42'):
    state=read(root)
    payload=dict(Orders=[dict(Id=order_id,ItemTypeId='T4_MAIN_SWORD',LocationId='7',AuctionType='offer',
        UnitPriceSilver=price*10000,Amount=12,QualityLevel=1,EnchantmentLevel=0,Expires=(now()+timedelta(days=20)).isoformat())])
    request=urllib.request.Request(f"http://127.0.0.1:{state['port']}/sandbox/marketorders.ingest",data=json.dumps(payload).encode(),
        headers={'X-Albion-Server':'3','Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=5) as response:assert response.status==200


def events(root):
    store=PeerStore(root)
    try:return [store.event(eid) for eid in store.inventory()]
    finally:store.close()


def run(output=None,cancel=lambda:False):
    processes={};logs={};checks=[]
    with tempfile.TemporaryDirectory(prefix='albioncraft-peer-sandbox-') as directory:
        roots={name:Path(directory)/name for name in ('user1','user2','user3')}
        def wait(predicate,description):return wait_for(predicate,description,cancel=cancel)
        for root in roots.values():root.mkdir()
        def start(name):
            root=roots[name];(root/'stop').unlink(missing_ok=True);(root/'state.json').unlink(missing_ok=True)
            log=open(root/'process.log','a',encoding='utf-8');logs[name]=log
            command=([sys.executable,'--peer-node',str(root)] if getattr(sys,'frozen',False) else
                [sys.executable,'-m','app.peer_sandbox','--node',str(root)])
            processes[name]=subprocess.Popen(command,cwd=str(Path(__file__).resolve().parents[1]),
                stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            return wait(lambda:read(root),'start '+name)
        def stop(name):
            (roots[name]/'stop').touch();processes[name].wait(timeout=15);assert processes[name].returncode==0
            logs[name].close();processes.pop(name)
        try:
            store=PeerStore(roots['user1']);store.create_group();store.close();state1=start('user1')
            for name in ('user2','user3'):
                store=PeerStore(roots[name]);store.join(state1['invitation']);store.close()
            state2=start('user2')
            store=PeerStore(roots['user3']);store.add_peer(state2['ticket']);store.close()
            ingest(roots['user1'],1200)
            first=wait(lambda:events(roots['user2']),'HTTP capture -> signed encrypted delivery')
            assert len(first)==1 and first[0]['data']['orders'][0]['price']==1200
            original_id=first[0]['id'];original_time=first[0]['observed'];checks.append('real HTTP capture -> encrypted user1 to user2')
            stop('user1');start('user3')
            third=wait(lambda:events(roots['user3']),'offline user3 gets user1 data from user2')
            assert third[0]['id']==original_id and third[0]['observed']==original_time
            checks.append('offline forwarding preserves original ID, author and observation time')
            # Persisted records survive an ungraceful process exit too.
            processes['user3'].kill();processes['user3'].wait(5);logs['user3'].close();processes.pop('user3');start('user3')
            assert events(roots['user3'])[0]['id']==original_id
            checks.append('durable mailbox survives process kill and restart')
            start('user1');ingest(roots['user1'],1800)
            def updated():
                e=events(roots['user3'])
                return e if e and e[0]['data']['orders'][0]['price']==1800 else None
            newest=wait(updated,'latest price reaches user3')
            assert newest[0]['id']!=original_id
            store=PeerStore(roots['user3'])
            try:
                assert store.receive(first[0]) is False
                assert store.receive(newest[0]) is False
            finally:store.close()
            assert events(roots['user3'])[0]['data']['orders'][0]['price']==1800
            checks.append('duplicate delivery is idempotent; late old data cannot roll back price')
            # Same observations over two senders must not make a third page.
            wait(lambda: len(events(roots['user2']))==1 and events(roots['user2'])[0]['id']==newest[0]['id'],'convergence')
            checks.append('three peers converge on one latest page')
            sizes={name:read(root)['stats'] for name,root in roots.items()}
            report=dict(ok=True,checks=checks,profiles=3,transport='Iroh QUIC/TLS, loopback, separate OS processes',sizes=sizes)
            if output:write(Path(output),report)
            print(json.dumps(report,ensure_ascii=False,indent=2))
            return report
        except Exception:
            for root in roots.values():
                path=root/'process.log'
                if path.exists():print(root.name,path.read_text(encoding='utf-8',errors='replace')[-4000:])
            raise
        finally:
            for name,p in list(processes.items()):
                (roots[name]/'stop').touch()
                try:p.wait(12)
                except subprocess.TimeoutExpired:p.kill();p.wait(5)
            for log in logs.values():
                if not log.closed:log.close()


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--node':asyncio.run(node_main(sys.argv[2]))
    else:run(sys.argv[1] if len(sys.argv)>1 else None)

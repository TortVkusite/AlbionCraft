"""Targeted updates from confirmed game operations; never infer page deletion."""
import json
from datetime import datetime,timezone
from decimal import Decimal
from .order_time import utc_time
from .market_stream import LOCATIONS


def observe_event(store,payload):
    owner=payload.get('CharacterId');action=payload.get('Action')
    if not isinstance(owner,str) or not owner or action not in ('created','cancelled','modified','mail'):raise ValueError('Неверное событие заказа')
    if payload.get('Confirmed') is not True:raise ValueError('Заказ не подтверждён сервером')
    stamp=(utc_time(payload.get('Observed')) or datetime.now(timezone.utc)).isoformat()
    city=LOCATIONS.get(str(payload.get('LocationId')))
    side=payload.get('Side');updated=0
    def finish(row,status):
        nonlocal updated
        who,city,side,key,raw,cost=row;record=json.loads(raw)
        if record.get('terminal'):return
        record.update(status=status,terminal=True,closed=stamp,observed=stamp)
        store.db.execute('INSERT OR REPLACE INTO own_order_terminal VALUES(?,?,?)',(who,key,status))
        store.db.execute('UPDATE captured_own_orders SET payload=? WHERE owner=? AND city=? AND side=? AND order_id=?',(json.dumps(record,ensure_ascii=False),who,city,side,key));updated+=1
    with store.db:
        if action in ('created','modified') and payload.get('Orders'):
            from .own_orders import decode_own_orders
            orders=decode_own_orders(payload)
            for order in orders:
                key=(owner,order['city'],order['side'],order['order_id'])
                if store.db.execute('SELECT 1 FROM own_order_terminal WHERE owner=? AND order_id=?',(owner,order['order_id'])).fetchone():continue
                old=store.db.execute('SELECT payload FROM captured_own_orders WHERE owner=? AND city=? AND side=? AND order_id=?',key).fetchone()
                if old and json.loads(old[0]).get('terminal'):continue
                if old and json.loads(old[0]).get('observed','')>stamp:continue
                order['note']='Из игры • подтверждённое '+('создание' if action=='created' else 'изменение')+' заказа'
                store.db.execute('INSERT INTO captured_own_orders VALUES(?,?,?,?,?,NULL) ON CONFLICT(owner,city,side,order_id) DO UPDATE SET payload=excluded.payload',(*key,json.dumps(order,ensure_ascii=False)));updated+=1
        elif action=='cancelled':
            ids=payload.get('OrderIds',[])
            if not isinstance(ids,list) or len(ids)>100 or any(type(k) not in (str,int) or not str(k) for k in ids):raise ValueError('Неверный ID отмены')
            for key in ids:
                store.db.execute('INSERT OR REPLACE INTO own_order_terminal VALUES(?,?,?)',(owner,str(key),'cancelled'))
                matches=store.db.execute('SELECT * FROM captured_own_orders WHERE owner=? AND order_id=?',(owner,str(key))).fetchall()
                matches=[r for r in matches if (not city or r[1]==city) and (side not in ('buy','sell') or r[2]==side)]
                if len(matches)==1:finish(matches[0],'cancelled')
        elif action=='mail':
            mail=payload.get('Mail')
            if not isinstance(mail,dict) or type(mail.get('Id')) not in (int,str):raise ValueError('Неверное письмо рынка')
            event_id='mail:'+str(mail['Id'])
            if store.db.execute('SELECT 1 FROM own_order_events WHERE owner=? AND event_id=?',(owner,event_id)).fetchone():return 0
            received=utc_time(mail.get('Received'));body=mail.get('Body');kind=mail.get('Type')
            kinds={'MARKETPLACE_SELLORDER_FINISHED_SUMMARY':('sell','finished'),'MARKETPLACE_BUYORDER_FINISHED_SUMMARY':('buy','finished'),
                'MARKETPLACE_SELLORDER_EXPIRED_SUMMARY':('sell','finished'),'MARKETPLACE_BUYORDER_EXPIRED_SUMMARY':('buy','finished')}
            if not isinstance(body,str) or kind not in kinds:raise ValueError('Неизвестное письмо рынка')
            side,status=kinds[kind];parts=body.split('|');city=LOCATIONS.get(str(mail.get('LocationId')))
            if len(parts)<4:raise ValueError('Неполное письмо рынка')
            if 'FINISHED' in kind:quantity=int(parts[0]);uid=parts[1];price=Decimal(parts[3])/10000
            else:
                quantity=int(parts[1]);uid=parts[3];price=None
            if quantity<0 or (price is not None and (not price.is_finite() or price<0)):raise ValueError('Неверное содержимое письма рынка')
            matches=[]
            # Summary letters do not contain an order ID/quality. Only a unique,
            # dated exact match may close an order; ambiguous letters stay pending.
            if received and city:
                for row in store.db.execute('SELECT * FROM captured_own_orders WHERE owner=? AND city=? AND side=?',(owner,city,side)):
                    record=json.loads(row[4]);created=utc_time(record.get('created'))
                    if record.get('terminal') or not created or created>received:continue
                    if record.get('item_id')!=uid or record.get('original_quantity',record['quantity'])!=quantity:continue
                    if price is not None and Decimal(record['price'])!=price:continue
                    if 'EXPIRED' in kind and (not record.get('expires') or utc_time(record['expires'])>received):continue
                    matches.append(row)
            if len(matches)==1:
                finish(matches[0],status);store.db.execute('INSERT INTO own_order_events VALUES(?,?,?)',(owner,event_id,json.dumps(payload,ensure_ascii=False)))
        message='Обновлено заказов: '+str(updated)+'.' if updated else 'Событие получено, но точного заказа не определено. Открой свои заказы в игре для сверки.'
        store.db.execute('INSERT OR REPLACE INTO personal_meta VALUES(?,?)',('own_capture_status',message))
        store.db.execute('INSERT OR REPLACE INTO personal_meta VALUES(?,?)',('own_version',stamp))
        # Keep bounded market-only protocol diagnostics for formats not yet decoded.
        store.db.execute('INSERT OR REPLACE INTO personal_meta VALUES(?,?)',('own_last_event',json.dumps(payload,ensure_ascii=False)))
    return updated

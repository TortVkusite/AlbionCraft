import json
import logging
from PySide6.QtCore import QThread,Signal
from .models import CITIES
from .cache import Cache

class Fetch(QThread):
    ready=Signal(object)
    failed=Signal(str)
    progress=Signal(str)
    def __init__(self,api,recipes,quality,root,force,activity='craft',extra_price_ids=()):
        super().__init__();self.api=api;self.recipes=recipes;self.quality=quality;self.root=root;self.force=force;self.activity=activity;self.extra_price_ids=set(extra_price_ids)
    def run(self):
        cache=Cache(self.root/'prices.sqlite');self.api.cancel=self.isInterruptionRequested
        rows=[];histories=[];warnings=[];cached=True;loaded_ids=set();loaded_history=set()
        try:
            ids=sorted({r.item_id for r in self.recipes}|self.extra_price_ids|({i.item_id for r in self.recipes for i in r.ingredients} if self.activity in ('craft','enchant') else set()))
            missing=[]
            for uid in ids:
                data=None if self.force else cache.get(json.dumps(['prices_item_all',uid]))
                if data is None:missing.append(uid)
                else:rows.extend(data);loaded_ids.add(uid)
            chunks=[missing[i:i+100] for i in range(0,len(missing),100)]
            for n,part in enumerate(chunks,1):
                if self.isInterruptionRequested():raise InterruptedError('Сканирование отменено')
                self.progress.emit(f'Цены: пакет {n}/{len(chunks)}; предметов и ресурсов {len(ids)}')
                cached=False
                try:
                    data=self.api.prices(part,CITIES,None)
                    data=cache.merge_prices(data,part,CITIES,range(1,6))
                    for uid in part:cache.put(json.dumps(['prices_item_all',uid]),[p for p in data if p['item_id']==uid])
                    loaded_ids.update(part)
                except InterruptedError:raise
                except Exception as exc:
                    logging.exception('Price batch failed');warnings.append(f'Пакет цен {n}: {exc}')
                    for uid in part:
                        data=cache.get(json.dumps(['prices_item_all',uid]),ttl=10**12)
                        if data is not None:rows.extend(data);loaded_ids.add(uid)
                    break
                rows.extend(data)
            from datetime import datetime,timezone
            items=sorted({r.item_id for r in self.recipes})
            day=str(datetime.now(timezone.utc).date());missing=[]
            for uid in items:
                data=cache.get(json.dumps(['history_item_all',uid,day]),ttl=1800)
                if data is None:missing.append(uid)
                else:histories.extend(data);loaded_history.add(uid)
            chunks=[missing[i:i+30] for i in range(0,len(missing),30)]
            for n,part in enumerate(chunks,1):
                if self.isInterruptionRequested():raise InterruptedError('Сканирование отменено')
                self.progress.emit(f'История: пакет {n}/{len(chunks)}; за 7 дней')
                try:
                    data=self.api.history(part,CITIES,None)
                    for uid in part:cache.put(json.dumps(['history_item_all',uid,day]),[h for h in data if h['item_id']==uid])
                    loaded_history.update(part)
                except InterruptedError:raise
                except Exception as exc:
                    logging.exception('History batch failed');warnings.append(f'История: {exc}');break
                histories.extend(data)
            if not rows and warnings:raise RuntimeError('; '.join(warnings))
            self.ready.emit(dict(recipes=self.recipes,quality=None,prices=rows,histories=histories,cached=cached,warning='; '.join(warnings),activity=self.activity,loaded_ids=loaded_ids,loaded_history=loaded_history))
        except InterruptedError:self.progress.emit('Сканирование отменено. Завершённые пакеты сохранены в кэш.')
        except Exception as exc:logging.exception('Fetch failed');self.failed.emit(str(exc))
        finally:cache.close();self.api.cancel=lambda:False

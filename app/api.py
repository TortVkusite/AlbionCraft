import gzip
import json
import logging
import time
from collections import deque
from urllib.request import Request, urlopen
from urllib.parse import quote, urlencode
from urllib.error import HTTPError, URLError

BASE = 'https://europe.albion-online-data.com'

class AlbionAPI:
    def __init__(self):
        self.requests = deque()
        self.cancel = lambda:False

    def get(self, url):
        for attempt in range(3):
            if self.cancel():raise InterruptedError('Сканирование отменено')
            while True:
                if self.cancel():raise InterruptedError('Сканирование отменено')
                now = time.monotonic()
                while self.requests and now-self.requests[0] >= 300:
                    self.requests.popleft()
                recent = [t for t in self.requests if now-t < 60]
                if len(self.requests) < 290 and len(recent) < 170:
                    break
                time.sleep(1)
            self.requests.append(time.monotonic())
            try:
                logging.info('GET %s', url)
                with urlopen(Request(url, headers={'Accept-Encoding':'gzip', 'User-Agent':'AlbionCraft-local/0.1'}), timeout=25) as res:
                    payload = res.read()
                    if res.headers.get('Content-Encoding') == 'gzip':
                        payload = gzip.decompress(payload)
                rows = json.loads(payload)
                if not isinstance(rows, list):
                    raise ValueError('API response must be a list')
                return rows
            except HTTPError as exc:
                if exc.code not in (429,500,502,503,504) or attempt == 2:
                    raise
                try:
                    delay = min(30, max(1, int(exc.headers.get('Retry-After','2'))))
                except ValueError:
                    delay = 2
                time.sleep(delay * (attempt+1))
            except (URLError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(2**attempt)

    def prices(self, ids, cities, quality):
        query = urlencode({'locations':','.join(cities), 'qualities':','.join(map(str, range(1,6) if quality is None else sorted({1,quality})))})
        prefix = BASE + '/api/v2/stats/prices/'
        batches, batch = [], []
        for uid in sorted(set(ids)):
            candidate = prefix + quote(','.join(batch+[uid]), safe=',@') + '.json?' + query
            if len(candidate) >= 4000 and batch:
                batches.append(batch)
                batch = []
            batch.append(uid)
        if batch:
            batches.append(batch)
        result = []
        for part in batches:
            result.extend(self.get(prefix + quote(','.join(part),safe=',@') + '.json?' + query))
        return result

    def history(self, ids, cities, quality):
        from datetime import datetime, timezone, timedelta
        end=datetime.now(timezone.utc).date()
        query=urlencode({'locations':','.join(cities),'qualities':','.join(map(str,range(1,6))) if quality is None else quality,'time-scale':24,
                         'date':str(end-timedelta(days=7)),'end_date':str(end)})
        result=[]
        # Small batches also limit payload sizes for multi-city history.
        ordered=sorted(set(ids))
        for n in range(0,len(ordered),30):
            url=BASE+'/api/v2/stats/history/'+quote(','.join(ordered[n:n+30]),safe=',@')+'.json?'+query
            result.extend(self.get(url))
        return result

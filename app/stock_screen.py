"""Read only visible, complete resource cells. All inference stays local."""
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage


def pixels(image):
    image=image.convertToFormat(QImage.Format_RGBA8888)
    buf=np.frombuffer(image.bits(),np.uint8).reshape(image.height(),image.bytesPerLine())
    return buf[:,:image.width()*4].reshape(image.height(),image.width(),4).copy()


def vector(image):
    a=pixels(image.scaled(48,48,Qt.IgnoreAspectRatio,Qt.SmoothTransformation))[:,:,:3].astype(float)
    result=[]
    # The tier badge must contribute independently: resource art repeats across tiers.
    for region,weight in [(a[15:39,9:40],.65),(a[5:14,5:14],.35)]:
        v=region.ravel().copy();v-=v.mean();v/=max(np.linalg.norm(v),1e-9)
        result.extend(v*weight**.5)
    return np.array(result)


def quantity_reader():
    from rapidocr import RapidOCR
    return RapidOCR(params={'Global.use_det':False,'Global.use_cls':False})


def border_enchantment(image):
    a=pixels(image.scaled(48,48,Qt.IgnoreAspectRatio,Qt.SmoothTransformation))[:,:,:3].astype(float)
    mask=np.zeros((48,48),bool);mask[2:7,9:40]=True;mask[12:32,2:7]=True;mask[12:32,41:46]=True
    r,g,b=a[mask].T
    green=np.mean((g-r>25)&(g-b>25));blue=np.mean((b-r>25)&(b>g*.94))
    purple=np.mean((r-g>25)&(b-g>25));gold=np.mean((r-b>40)&(g-b>40))
    if purple>.14:return 3
    if gold>.2:return 4
    if green>.14:return 1
    if blue>.14:return 2
    return 0 if max(green,blue,purple,gold)<.12 else None


def recognize_grid(image,columns,templates,reader=None):
    if not 1<=columns<=12 or image.isNull():raise ValueError('Неверная область банка')
    step=image.width()/columns;rows=int(image.height()/step)
    if not rows or not templates:return [],['Нет полных ячеек или шаблонов ресурсов.']
    if rows*columns>300:raise ValueError('Выдели только видимые полные ячейки банка.')
    a=pixels(image);samples=np.array([a[round(r*step),round(c*step),:3] for r in range(rows) for c in range(columns)],dtype=float)
    r,g,b=np.median(samples,axis=0)
    if not (r>180 and g>130 and b>90 and r-g>15 and g-b>15 and np.max(samples.std(axis=0))<24):
        raise ValueError('Область не похожа на сетку открытого банка. Выдели полные клетки с отступами по краям.')
    reader=reader or quantity_reader()
    ids=list(templates);matrix=np.stack([vector(templates[k]) for k in ids]);accepted=[];warnings=[]
    shift=max(1,round(step*.05));size=round(step)
    for row in range(rows):
        for col in range(columns):
            x=round(col*step);y=round(row*step);variants=[];positions=[]
            for dx in range(-shift,shift+1):
                for dy in range(-shift,shift+1):
                    variants.append(vector(image.copy(x+dx,y+dy,size,size)));positions.append((dx,dy))
            scores=matrix@np.stack(variants).T;top=scores.max(axis=1);best=np.argsort(top)[-2:][::-1]
            enchantment=border_enchantment(image.copy(x,y,size,size))
            if enchantment is None:
                if top.max()>=.65:warnings.append(f'Ячейка {row*columns+col+1}: зачарование не определено уверенно.')
                continue
            for k,uid in enumerate(ids):
                if (int(uid.rsplit('@',1)[1]) if '@' in uid else 0)!=enchantment:top[k]=-1
            best=np.argsort(top)[-2:][::-1]
            a=best[0];score=float(top[a]);gap=float(top[a]-top[best[1]]) if len(best)>1 else 1
            n=row*columns+col
            if score<.72 or gap<.025:
                if score>=.65:warnings.append(f'Ячейка {n+1}: предмет или тир не определён уверенно.')
                continue
            dx,dy=positions[int(scores[a].argmax())]
            q=image.copy(x+dx+round(step*54/82),y+dy+round(step*54/82),round(step*24/82),max(8,round(step*12/82)))
            p=pixels(q)[:,:,:3];neutral=(np.max(p,axis=2)-np.min(p,axis=2)<35)&(np.mean(p,axis=2)>80)
            gray=np.mean(p,axis=2).astype(np.uint8);gray[~neutral]=30
            result=reader(np.repeat(gray[:,:,None],3,axis=2),use_det=False,use_cls=False,use_rec=True)
            text=result.txts[0].strip() if result.txts else ''
            confidence=float(result.scores[0]) if result.scores else 0
            if not text.isdecimal() or confidence<.95 or not 1<=int(text)<=999:
                warnings.append(f'Ячейка {n+1}: количество не распознано для {ids[a]}');continue
            accepted.append(dict(item_id=ids[a],quantity=int(text),cell=n,confidence=score,quantity_confidence=confidence))
    return accepted,warnings

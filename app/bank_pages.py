"""Join bank viewports by absolute slots; ambiguous overlaps require an anchor."""
import hashlib,re


def page_key(kind,container):
    if not container.strip():raise ValueError('Укажи имя контейнера')
    return kind if container.strip()=='Банк' else kind+':container:'+hashlib.sha256(container.strip().encode()).hexdigest()[:16]


def page_vector(rows,cells):
    if type(cells) is not int or cells<1 or any(type(r.get('cell')) is not int or not 0<=r['cell']<cells or type(r.get('quantity')) is not int or r['quantity']<1 or not re.fullmatch(r'[A-Z0-9_@]+',r.get('item_id','')) for r in rows):raise ValueError('Неверный ресурс, количество или координаты ячеек')
    if len({r['cell'] for r in rows})!=len(rows):raise ValueError('Повтор ячейки в снимке')
    data={r['cell']:[r['item_id'],r['quantity']] for r in rows}
    return [data.get(n) for n in range(cells)]


def locate_page(state,vector,columns,first_row=None):
    if columns<1 or len(vector)%columns:raise ValueError('Область должна содержать целые строки')
    if first_row is not None:
        if first_row<0:raise ValueError('Первая строка не может быть отрицательной')
        return first_row*columns
    if not state or not state.get('slots'):return 0
    if state['columns']!=columns:raise ValueError('Число столбцов изменилось. Начни новый снимок контейнера.')
    if state.get('last_vector')==vector:
        if len({tuple(v) for v in vector if v is not None})<2:raise ValueError('Одинаковые стопки не позволяют определить прокрутку. Выключи автопозицию и укажи первую строку области.')
        return state['last_offset']
    slots={int(n):value for n,value in state['slots'].items()};matches=[]
    end=max(slots)+1
    for offset in range(0,end,columns):
        overlap=[(n,value) for n,value in enumerate(vector) if offset+n in slots]
        if len(overlap)<columns*2:continue
        if any(value!=slots[offset+n] for n,value in overlap):continue
        anchors={tuple(value) for n,value in overlap if value is not None}
        if len(anchors)<2:continue
        matches.append(offset)
    if len(matches)!=1:raise ValueError('Положение неоднозначно: оставь минимум две перекрывающиеся строки с разными ресурсами либо выключи автопозицию и укажи первую строку области. При сортировке банка начни новый снимок.')
    return matches[0]


def joined_state(state,vector,columns,offset,container,warnings=()):
    if state and state['columns']!=columns:raise ValueError('Число столбцов изменилось. Начни новый снимок.')
    result=dict(state or {},columns=columns,container=container,complete=False,last_vector=vector,last_offset=offset)
    result['slots']=dict(result.get('slots',{}));result['uncertain']=dict(result.get('uncertain',{}))
    for n,value in enumerate(vector):result['slots'][str(offset+n)]=value;result['uncertain'].pop(str(offset+n),None)
    for warning in warnings:
        match=re.match(r'Ячейка (\d+):',warning)
        if match:result['uncertain'][str(offset+int(match[1])-1)]=warning
    return result


def complete_state(state):
    if not state or not state.get('slots'):raise ValueError('Сначала прочитай контейнер')
    if state.get('uncertain'):raise ValueError('Есть сомнительные ячейки. Прочитай их ещё раз перед завершением снимка.')
    seen={int(n) for n in state['slots']}
    if seen!=set(range(max(seen)+1)):raise ValueError('Между прочитанными участками есть пропуски. Прочитай их перед завершением снимка.')
    return dict(state,complete=True)

from datetime import datetime,timezone


def utc_time(value):
    if not value:return None
    value=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def remaining_time(order,now=None):
    now=now or datetime.now(timezone.utc)
    expires=utc_time(order.get('expires'))
    if not expires:return 'Неизвестно','Срок заказа ещё не получен из игры.',float('inf')
    seconds=max(0,int((expires-now).total_seconds()))
    days,rest=divmod(seconds,86400);hours,rest=divmod(rest,3600);minutes,secs=divmod(rest,60)
    tip=f'Истекает: {expires.astimezone():%d.%m.%Y %H:%M:%S %Z}\nОсталось: {days} д {hours} ч {minutes} мин {secs} с'
    if order.get('created'):tip+='\nСоздан: '+utc_time(order['created']).astimezone().strftime('%d.%m.%Y %H:%M:%S %Z')
    return f'{days} д {hours} ч',tip,seconds

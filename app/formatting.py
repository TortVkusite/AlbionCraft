from datetime import datetime

def timestamp(value):
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        return dt.strftime('%d.%m.%y %H:%M') if dt.year>1 else '—'
    except (ValueError,TypeError,AttributeError): return '—'

def money(value):
    if isinstance(value,str):
        from decimal import Decimal
        value=Decimal(value)
    return f'{value:,.0f}'.replace(',',' ') if value is not None else '—'

def roi(value):
    return f'{value:+.1f}%' if value is not None else '—'

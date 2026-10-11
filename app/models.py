from dataclasses import dataclass
from datetime import datetime, timezone

CITIES = ('Bridgewatch', 'Martlock', 'Thetford', 'Fort Sterling', 'Lymhurst', 'Caerleon', 'Brecilien')

@dataclass(frozen=True)
class Ingredient:
    item_id: str
    amount: int
    returnable: bool
    preserve_quality: bool = False

@dataclass(frozen=True)
class Recipe:
    item_id: str
    name: str
    variant: int
    ingredients: tuple[Ingredient, ...]
    category: str = ''
    family: str = ''
    base_id: str = ''
    tier: int = 4
    enchantment: int = 0
    path: str = 'Прямой крафт'
    recipe_silver: int = 0
    output_count: int = 1
    warnings: tuple[str, ...] = ()
    crafting_category: str = ''
    nutrition: str | None = None
    max_quality: int = 5

def quote(row, side, max_age=30, now=None):
    """Never substitute zero for an absent quote. Naive API times are flagged."""
    value = row.get(side)
    stamp = row.get(side + '_date')
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return None, None, 'нет цены'
    try:
        dt = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        if dt.year == 1:
            return None, None, 'нет даты'
    except (TypeError, ValueError, AttributeError):
        return None, None, 'неверная дата'
    naive = dt.tzinfo is None
    # Explicit provisional UTC interpretation, never rated as verified fresh.
    dt = dt.replace(tzinfo=timezone.utc) if naive else dt.astimezone(timezone.utc)
    age = ((now or datetime.now(timezone.utc)) - dt).total_seconds() / 60
    if age < -2:
        return value, age, 'дата в будущем'
    status = 'устарело; возраст не ограничен' if max_age is None and age > 30 else 'возраст не ограничен' if max_age is None else 'устарело' if age > max_age else 'свежее'
    if naive:
        status += '; UTC требует проверки'
    return value, age, status

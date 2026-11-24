from datetime import date

from src.utils.serialize import canonical


def stations(cursor):
    cursor.execute('SELECT * FROM stations ORDER BY code')
    return cursor.fetchall()


def list_closures(cursor, period, station_code):
    where = 'c.end_date >= %s AND c.start_date <= %s'
    args = [period.start, period.end]
    if station_code:
        where += ' AND c.station_code = %s'
        args.append(station_code)
    cursor.execute(f'SELECT c.*, s.name FROM station_closures c JOIN stations s '
                   f'ON c.station_code=s.code WHERE {where} '
                   'ORDER BY c.start_date, c.start_hour, c.station_code, c.id', args)
    return cursor.fetchall()


def active_closures(cursor, start, end):
    """窗口内与分型区间相交的闭站登记，按自然键排序，保证快照稳定。

    返回日期对象供小时切分计算；落快照时由调用方转成 ISO 字符串。
    """
    cursor.execute('SELECT id,station_code,start_date,start_hour,end_date,end_hour,reason '
                   'FROM station_closures WHERE end_date >= %s AND start_date <= %s '
                   'ORDER BY start_date,start_hour,end_date,end_hour,station_code,id',
                   (start, end))
    return cursor.fetchall()


def serialize_closure(row):
    return {**row,
            'start_date': row['start_date'].isoformat(),
            'end_date': row['end_date'].isoformat()}


def closure_marks(cursor, period, station_code):
    """返回窗口内落在闭站半开区间中的 (station, day, hour) 集合，用于冲突凭据标记。"""
    closures = list_closures(cursor, period, station_code)
    marks = set()
    for closure in closures:
        start_h = closure['start_date'].toordinal() * 24 + closure['start_hour']
        end_h = closure['end_date'].toordinal() * 24 + closure['end_hour']
        for hour_index in range(start_h, end_h):
            day_ord, hour = divmod(hour_index, 24)
            marks.add((closure['station_code'], date.fromordinal(day_ord), hour))
    return marks


def list_records(cursor, period, station_code, page):
    where = 'r.day BETWEEN %s AND %s'
    args = [period.start, period.end]
    if station_code:
        where += ' AND r.station_code = %s'
        args.append(station_code)
    cursor.execute(f'SELECT COUNT(*) AS total, COALESCE(SUM(r.quantity),0) AS quantity '
                   f'FROM return_records r WHERE {where}', args)
    totals = cursor.fetchone()
    cursor.execute(f'SELECT r.*, s.name FROM return_records r JOIN stations s '
                   f'ON r.station_code=s.code WHERE {where} '
                   'ORDER BY r.day DESC, r.station_code, r.hour LIMIT 12 OFFSET %s',
                   [*args, (page - 1) * 12])
    items = cursor.fetchall()
    closed_hours = closure_marks(cursor, period, station_code)
    for item in items:
        # 闭站时段内的归还不删除、不改写，只在台账上标记为闭站冲突凭据。
        item['during_closure'] = (item['station_code'], item['day'], item['hour']) in closed_hours
    return {**totals, 'page': page, 'items': items}


def audit(cursor, actor, action, entity_key, payload):
    cursor.execute('INSERT INTO audit_events(actor,action,entity_key,payload) VALUES(%s,%s,%s,%s)',
                   (actor, action, entity_key, canonical(payload)))

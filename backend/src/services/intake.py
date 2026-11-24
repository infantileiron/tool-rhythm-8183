from fastapi import HTTPException
from pymysql.err import IntegrityError

from src.config.database import database
from src.models.ledger import audit, list_closures, list_records, stations


def station_list():
    with database() as cursor:
        return stations(cursor)


def create_station(data, actor):
    try:
        with database() as cursor:
            cursor.execute('INSERT INTO stations(code,name,address,steward) VALUES(%s,%s,%s,%s)',
                           (data.code, data.name, data.address, data.steward))
            audit(cursor, actor, 'station.create', data.code, data.model_dump())
    except IntegrityError as error:
        if error.args[0] == 1062:
            raise HTTPException(409, '站点编号已登记') from error
        raise
    return data


def records(period, station_code, page):
    with database() as cursor:
        return list_records(cursor, period, station_code, page)


def closures(period, station_code):
    with database() as cursor:
        return list_closures(cursor, period, station_code)


def _hour_index(day, hour):
    return day.toordinal() * 24 + hour


def create_closure(data, actor):
    start_h = _hour_index(data.start_date, data.start_hour)
    end_h = _hour_index(data.end_date, data.end_hour)
    try:
        with database() as cursor:
            # 同站闭站区间不得交叠，保证闭站小时数可准确切分到各归还时段。
            cursor.execute('SELECT id,start_date,start_hour,end_date,end_hour FROM station_closures '
                           'WHERE station_code=%s AND end_date >= %s AND start_date <= %s FOR UPDATE',
                           (data.station_code, data.start_date, data.end_date))
            for row in cursor.fetchall():
                existing_start = _hour_index(row['start_date'], row['start_hour'])
                existing_end = _hour_index(row['end_date'], row['end_hour'])
                if existing_start < end_h and start_h < existing_end:
                    raise HTTPException(409, '该站点已有交叠的闭站登记，请先核对或删除原登记')
            cursor.execute('INSERT INTO station_closures(station_code,start_date,start_hour,'
                           'end_date,end_hour,reason) VALUES(%s,%s,%s,%s,%s,%s)',
                           (data.station_code, data.start_date, data.start_hour,
                            data.end_date, data.end_hour, data.reason))
            closure_id = cursor.lastrowid
            audit(cursor, actor, 'closure.create', str(closure_id), data.model_dump(mode='json'))
    except IntegrityError as error:
        if error.args[0] == 1452:
            raise HTTPException(422, '站点尚未登记') from error
        raise
    return {**data.model_dump(mode='json'), 'id': closure_id}


def delete_closure(closure_id, actor):
    with database() as cursor:
        cursor.execute('SELECT * FROM station_closures WHERE id=%s FOR UPDATE', (closure_id,))
        before = cursor.fetchone()
        if not before:
            raise HTTPException(404, '闭站登记不存在')
        # 只删除闭站登记本身；闭站时段内的归还记录原样保留，继续作为冲突凭据。
        cursor.execute('DELETE FROM station_closures WHERE id=%s', (closure_id,))
        audit(cursor, actor, 'closure.delete', str(closure_id), {
            'station_code': before['station_code'],
            'start_date': before['start_date'].isoformat(), 'start_hour': before['start_hour'],
            'end_date': before['end_date'].isoformat(), 'end_hour': before['end_hour'],
            'reason': before['reason'],
        })
    return {'id': closure_id, 'deleted': True}


def create_record(data, actor):
    try:
        with database() as cursor:
            cursor.execute('INSERT INTO return_records(station_code,day,hour,quantity,source) '
                           'VALUES(%s,%s,%s,%s,%s)',
                           (data.station_code, data.day, data.hour, data.quantity, data.source))
            record_id = cursor.lastrowid
            audit(cursor, actor, 'record.create', str(record_id), data.model_dump(mode='json'))
    except IntegrityError as error:
        if error.args[0] == 1062:
            raise HTTPException(409, '该站点日期和小时已有记录，可在台账中校正') from error
        if error.args[0] == 1452:
            raise HTTPException(422, '站点尚未登记') from error
        raise
    return {**data.model_dump(), 'id': record_id, 'revision': 1}


def correct_record(record_id, data, actor):
    with database() as cursor:
        cursor.execute('SELECT * FROM return_records WHERE id=%s FOR UPDATE', (record_id,))
        before = cursor.fetchone()
        if not before:
            raise HTTPException(404, '归还记录不存在')
        if before['revision'] != data.revision:
            raise HTTPException(409, '有其他同事更新了这条记录，请刷新台账后再校正')
        cursor.execute('UPDATE return_records SET quantity=%s,source=%s,revision=revision+1 WHERE id=%s',
                       (data.quantity, data.source, record_id))
        audit(cursor, actor, 'record.correct', str(record_id), {
            'old': {'quantity': before['quantity'], 'source': before['source']},
            'new': data.model_dump(),
        })
        return {**before, 'quantity': data.quantity, 'source': data.source, 'revision': data.revision + 1}

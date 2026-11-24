import csv
import io
import logging

from fastapi import HTTPException
from redis.exceptions import RedisError

from src.config.database import database
from src.config.queue import QUEUE_KEY, redis
from src.constants.domain import ALGORITHM, BANDS, EXCEPTIONS, Role, RunStatus
from src.models.ledger import active_closures, audit, serialize_closure, stations
from src.models.runs import list_runs, run_record
from src.utils.serialize import canonical, fingerprint


def _hour_index(day, hour):
    return day.toordinal() * 24 + hour


def _band_hour_index(bands):
    mapping = {}
    for index, (a, b) in enumerate(bands):
        for hour in range(a, b):
            mapping[hour] = index
    return mapping


def snapshot(cursor, params):
    sites = stations(cursor)
    if len(sites) > 250:
        raise HTTPException(422, '当前站点超过单次计算上限 250 个')
    window_days = (params.end - params.start).days + 1
    band_count = len(BANDS)
    # 闭站登记与归还在同一个事务、同一个时点读取：同次分型对两类数据取一致快照，
    # 「闭站登记和归还同时提交」的场景也会落在同一版本里。
    closures = active_closures(cursor, params.start, params.end)
    band_of_hour = _band_hour_index(BANDS)
    nominal_hours = [window_days * (b - a) for a, b in BANDS]

    # 每站各时段落入闭站半开区间的小时数；闭站区间在录入时已保证同站互不交叠。
    closed_hours = {site['code']: [0] * band_count for site in sites}
    # 全局闭站小时标记 (station, 绝对小时序号)，用于把闭站时段归还识别为冲突凭据。
    closed_marks = set()
    window_start = _hour_index(params.start, 0)
    window_end = _hour_index(params.end, 24)
    for closure in closures:
        start_h = max(_hour_index(closure['start_date'], closure['start_hour']), window_start)
        end_h = min(_hour_index(closure['end_date'], closure['end_hour']), window_end)
        for hour_index in range(start_h, end_h):
            closed_hours[closure['station_code']][band_of_hour[hour_index % 24]] += 1
            closed_marks.add((closure['station_code'], hour_index))

    raw_counts = {site['code']: [0] * band_count for site in sites}
    closed_counts = {site['code']: [0] * band_count for site in sites}
    cursor.execute('SELECT station_code,day,hour,SUM(quantity) AS quantity FROM return_records '
                   'WHERE day BETWEEN %s AND %s GROUP BY station_code,day,hour',
                   (params.start, params.end))
    record_rows = cursor.fetchall()
    for row in record_rows:
        code = row['station_code']
        band_index = band_of_hour[row['hour']]
        quantity = int(row['quantity'])
        raw_counts[code][band_index] += quantity
        # 闭站时段内的归还不删除：单独累计为冲突件数，节律计算中剔除，原记录留作凭据。
        if (code, _hour_index(row['day'], row['hour'])) in closed_marks:
            closed_counts[code][band_index] += quantity

    snapshot_sites = []
    for site in sites:
        code = site['code']
        closed = closed_hours[code]
        open_hours = [nominal_hours[i] - closed[i] for i in range(band_count)]
        counts = [raw_counts[code][i] - closed_counts[code][i] for i in range(band_count)]
        snapshot_sites.append({'code': code, 'name': site['name'], 'counts': counts,
                               'raw_counts': raw_counts[code], 'closed_counts': closed_counts[code],
                               'closed_hours': closed, 'open_hours': open_hours})
    return {'algorithm': ALGORITHM, 'bands': BANDS, 'window_days': window_days,
            'nominal_hours': nominal_hours,
            'closures': [serialize_closure(closure) for closure in closures],
            'params': params.model_dump(mode='json', exclude={'title'}),
            'stations': snapshot_sites}


def queue_run(params, actor):
    with database() as cursor:
        inputs = snapshot(cursor, params)
        checksum = fingerprint(inputs)
        cursor.execute('INSERT INTO runs(title,creator,snapshot,checksum) VALUES(%s,%s,%s,%s)',
                       (params.title, actor, canonical(inputs), checksum))
        run_id = cursor.lastrowid
        audit(cursor, actor, 'run.queue', str(run_id), {'checksum': checksum})
    try:
        with redis.pipeline() as signals:
            signals.lpush(QUEUE_KEY, run_id).ltrim(QUEUE_KEY, 0, 99).execute()
    except RedisError:
        logging.warning('Redis wake failed for run %s; database polling remains active', run_id)
    return {'id': run_id, 'checksum': checksum, 'status': RunStatus.QUEUED}


def summaries(viewer):
    with database() as cursor:
        return list_runs(cursor, viewer['role'] == Role.OBSERVER)


def details(run_id, viewer):
    with database() as cursor:
        run = run_record(cursor, run_id)
    if not run or (viewer['role'] == Role.OBSERVER and run['status'] != RunStatus.PUBLISHED):
        raise HTTPException(404, '找不到可查看的方案版本')
    return run


def publish(run_id, data, actor):
    with database() as cursor:
        run = run_record(cursor, run_id, lock=True)
        if not run:
            raise HTTPException(404, '找不到方案版本')
        if run['status'] != RunStatus.READY:
            raise HTTPException(409, '仅待复核的版本可以发布')
        expected_groups = {group['key'] for group in run['result']['groups']}
        expected_exceptions = {m['code'] for m in run['result']['members'] if m['status'] in EXCEPTIONS}
        if expected_groups != data.groups.keys() or expected_exceptions != data.exceptions.keys():
            raise HTTPException(422, '请填写全部分组的值守安排及全部例外站点的处理意见')
        decision = {**data.model_dump(), 'reviewer': actor}
        cursor.execute("UPDATE runs SET status='published',decision=%s,published_at=UTC_TIMESTAMP() WHERE id=%s",
                       (canonical(decision), run_id))
        audit(cursor, actor, 'run.publish', str(run_id), {'checksum': run['checksum'], **decision})
    return details(run_id, {'role': Role.ADMIN})


def spreadsheet_text(value):
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


def export_csv(run):
    if run['status'] != RunStatus.PUBLISHED:
        raise HTTPException(409, '发布后可以导出值班单')
    params = run['snapshot']['params']
    decision = run['decision']
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(['版本', '输入校验值', '起日', '止日', '站点编号', '站点名称', '类型', '分组',
                     '开放时段归还件数', *[f'{a:02d}:00–{b:02d}:00' for a, b in run['snapshot']['bands']],
                     '闭站时长(小时)', '闭站时段冲突件数', '值守或复核处置', '发布人', '复核说明'])
    for member in run['result']['members']:
        action = (decision['groups'][member['group']] if member['group'] else
                  decision['exceptions'][member['code']])
        writer.writerow([run['id'], run['checksum'], params['start'], params['end'], member['code'],
                         spreadsheet_text(member['name']), member['status'], member['group'],
                         member['total'], *member['counts'],
                         member['closed_total_hours'], member['conflict_returns'],
                         spreadsheet_text(action), decision['reviewer'],
                         spreadsheet_text(decision['memo'])])
    return '\ufeff' + out.getvalue()

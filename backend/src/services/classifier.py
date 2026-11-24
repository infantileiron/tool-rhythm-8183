from collections import deque
from math import sqrt

from src.constants.domain import StationStatus as Status


def unit_vector(values):
    norm = sqrt(sum(value * value for value in values))
    # 合格站至少有一个开放时段有归还，范数必然为正；零向量在调用前已被低样本门槛拦截。
    return [value / norm for value in values]


def open_bands(site):
    return {index for index, hours in enumerate(site['open_hours']) if hours > 0}


def rate_vector(site):
    # 节律按「每开放小时归还件数」衡量：闭站时段的件数与小时同时剔除，
    # 闭站半天的站点不会因为分母虚小而被抬高峰值。
    return [site['counts'][i] / site['open_hours'][i] if site['open_hours'][i] else 0.0
            for i in range(len(site['counts']))]


def neighborhoods(vectors, open_band_map, eps):
    adjacent = {code: {code} for code in vectors}
    points = list(vectors.items())
    for index, (left, a) in enumerate(points):
        for right, b in points[index + 1:]:
            # 两站只在彼此共同开放的时段上比较形状；完全没有共同开放时段则不相邻。
            common = open_band_map[left] & open_band_map[right]
            if not common:
                continue
            dot = sum(a[i] * b[i] for i in common)
            left_norm = sqrt(sum(a[i] * a[i] for i in common))
            right_norm = sqrt(sum(b[i] * b[i] for i in common))
            similarity = dot / (left_norm * right_norm) if left_norm and right_norm else 0.0
            distance = max(0.0, 1.0 - similarity)
            if distance <= eps + 1e-12:
                adjacent[left].add(right)
                adjacent[right].add(left)
    return {code: sorted(neighbors) for code, neighbors in adjacent.items()}


def common_basis(codes, open_band_map):
    if not codes:
        return set()
    basis = set(open_band_map[codes[0]])
    for code in codes[1:]:
        basis &= open_band_map[code]
    return basis


def dbscan(adjacent, min_points, open_band_map):
    """余弦 DBSCAN，并在密度连通之上叠加共同开放时段门槛。

    核心站仍按闭邻域人数（含本站）判定；扩展新成员时要求该站与组内全体成员
    至少有一个共同开放时段，保证每个成组都能指出各站共同开放的时段。
    """
    core = {code for code, links in adjacent.items() if len(links) >= min_points}
    labels = {}
    blocked = {}
    cluster = 0
    for root in sorted(core):
        if root in labels:
            continue
        cluster += 1
        label = f'G{cluster:02}'
        labels[root] = label
        members = [root]
        queue = deque([root])
        while queue:
            for neighbor in adjacent[queue.popleft()]:
                if neighbor in labels:
                    continue
                # 共同开放时段门槛：与组内现有成员逐站求交集，交集为空则拒绝入组。
                if not common_basis(members + [neighbor], open_band_map):
                    blocked.setdefault(neighbor, label)
                    continue
                labels[neighbor] = label
                members.append(neighbor)
                if neighbor in core:
                    queue.append(neighbor)
    return labels, core, blocked


def classify(snapshot):
    params = snapshot['params']
    sites = sorted(snapshot['stations'], key=lambda site: site['code'])
    open_band_map = {site['code']: open_bands(site) for site in sites}
    eligible = [site for site in sites if sum(site['counts']) >= params['min_returns']
                and open_band_map[site['code']]]
    vectors = {site['code']: unit_vector(rate_vector(site)) for site in eligible}
    adjacent = neighborhoods(vectors, open_band_map, params['eps'])
    labels, core, blocked = dbscan(adjacent, params['min_points'], open_band_map)
    members = []
    for site in sites:
        code, counts = site['code'], site['counts']
        total = sum(counts)
        conflict_total = sum(site['closed_counts'])
        closed_total_hours = sum(site['closed_hours'])
        group = labels.get(code)
        if not total and not conflict_total:
            status = Status.EMPTY
            reason = '窗口内没有归还记录，请确认是休站、漏录还是确实无人归还。'
        elif not total:
            # 有闭站冲突件数但开放时段零归还，仍按无记录处理，冲突件数留作凭据。
            status = Status.EMPTY
            reason = '开放时段无归还；闭站时段另有冲突归还，请先核对闭站登记与联单。'
        elif code not in vectors:
            status = Status.LOW
            reason = f'开放时段归还 {total} 件，低于 {params["min_returns"]} 件门槛，延长采样后再算。'
        elif not group:
            status = Status.NOISE
            if code in blocked:
                reason = (f'邻域节律相近，但与 {blocked[code]} 组内各站没有共同开放时段，'
                          '暂不分组，需逐站核实闭站安排。')
            else:
                reason = '闭邻域内合格站点不足最少邻居数，节律失群，需逐站核实。'
        else:
            status = Status.CORE if code in core else Status.BORDER
            reason = ''
        profile = [counts[i] / site['open_hours'][i] if site['open_hours'][i] else None
                   for i in range(len(counts))]
        members.append({**site, 'total': total, 'group': group, 'status': status,
                        'noise_reason': reason,
                        'conflict_returns': conflict_total,
                        'closed_total_hours': closed_total_hours,
                        'neighbors': len(adjacent[code]) if code in adjacent else None,
                        'profile': profile})
    groups = []
    for label in sorted(set(labels.values())):
        cohort = [member for member in members if member['group'] == label]
        basis = sorted(common_basis([member['code'] for member in cohort], open_band_map))
        # 组画像只在各站共同开放的时段上等权平均，其余时段不参与峰段判定。
        profile = []
        for index in range(len(snapshot['bands'])):
            if index in basis:
                profile.append(sum(member['profile'][index] for member in cohort) / len(cohort))
            else:
                profile.append(None)
        peak = max(basis, key=lambda index: (profile[index], -index))
        start, end = snapshot['bands'][peak]
        action = (f'优先安排 {start:02d}:00–{end:02d}:00 值守，按开放小时件数核定人手。'
                  if start >= 8 and start < 20 else
                  f'核对 {start:02d}:00–{end:02d}:00 自助柜记录，确认峰值后安排巡检。')
        groups.append({'key': label, 'station_codes': [m['code'] for m in cohort],
                       'profile': profile, 'common_bands': basis, 'peak': peak, 'advice': action,
                       'returns': sum(m['total'] for m in cohort),
                       'conflict_returns': sum(m['conflict_returns'] for m in cohort)})
    return {'groups': groups, 'members': members,
            'diagnostics': {'eligible': len(vectors), 'stations': len(sites),
                            'returns': sum(m['total'] for m in members),
                            'conflict_returns': sum(m['conflict_returns'] for m in members),
                            'closures': len(snapshot['closures']),
                            'open_hour_basis': True}}

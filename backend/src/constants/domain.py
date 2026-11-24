from enum import StrEnum


class Role(StrEnum):
    ADMIN = 'admin'
    ANALYST = 'analyst'
    OBSERVER = 'observer'


class RunStatus(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    READY = 'ready'
    PUBLISHED = 'published'
    FAILED = 'failed'


class StationStatus(StrEnum):
    CORE = 'core'
    BORDER = 'border'
    NOISE = 'noise'
    LOW = 'low_sample'
    EMPTY = 'no_data'


BANDS = [(0, 8), (8, 11), (11, 14), (14, 17), (17, 20), (20, 24)]
# v2：节律向量改为每开放小时归还件数，并叠加组内共同开放时段门槛。
# v1 是按六段原始件数归一化，不识别闭站；旧快照仍按原样留存，不会被重算。
ALGORITHM = 'cosine-dbscan-v2'
EXCEPTIONS = {StationStatus.NOISE, StationStatus.LOW, StationStatus.EMPTY}

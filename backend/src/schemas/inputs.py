from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


Code = Annotated[str, StringConstraints(pattern=r'^[A-Z][A-Z0-9-]{1,11}$')]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=240)]


class Login(Input):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class StationInput(Input):
    code: Code
    name: str = Field(min_length=2, max_length=60)
    address: str = Field(min_length=2, max_length=100)
    steward: str = Field(min_length=2, max_length=40)


class RecordInput(Input):
    station_code: Code
    day: date
    hour: int = Field(ge=0, le=23)
    quantity: int = Field(ge=1, le=9999)
    source: str = Field(min_length=2, max_length=80)


class Correction(Input):
    quantity: int = Field(ge=1, le=9999)
    source: str = Field(min_length=2, max_length=80)
    revision: int = Field(ge=1)


class Period(Input):
    start: date
    end: date

    @model_validator(mode='after')
    def check_period(self):
        if not 0 <= (self.end - self.start).days < 93:
            raise ValueError('日期窗口须为连续 1–93 天，含起止日')
        return self


class ClosureInput(Input):
    station_code: Code
    start_date: date
    start_hour: int = Field(ge=0, le=23)
    end_date: date
    end_hour: int = Field(ge=0, le=23)
    reason: str = Field(min_length=2, max_length=120)

    @model_validator(mode='after')
    def check_span(self):
        # 半开区间 [start_date start_hour, end_date end_hour)，起止时点必须严格递增，
        # 最长 93 天，与分型窗口上限保持一致。
        start = datetime.combine(self.start_date, datetime.min.time()).replace(hour=self.start_hour)
        end = datetime.combine(self.end_date, datetime.min.time()).replace(hour=self.end_hour)
        hours = (end - start).total_seconds() / 3600
        if not 1 <= hours <= 93 * 24:
            raise ValueError('闭站时段须为 1 小时至 93 天之间的半开区间')
        return self


class PlanInput(Period):
    title: str = Field(min_length=2, max_length=80)
    eps: float = Field(ge=0, le=1)
    min_points: int = Field(ge=2, le=20)
    min_returns: int = Field(ge=1, le=9999)


class PublishInput(Input):
    memo: Note
    groups: dict[str, Note] = Field(max_length=250)
    exceptions: dict[Code, Note] = Field(max_length=250)

"""Request models shared by FastAPI and the auction rules."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

Money = Annotated[Decimal, Field(ge=0, le=1_000_000_000, decimal_places=2, allow_inf_nan=False)]
Minutes = Annotated[int, Field(strict=True, ge=1, le=1440)]
Trigger = Literal['bid_received', 'rank_change', 'l1_change']


class RFQCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    name: str = Field(min_length=1, max_length=120)
    reference: str = Field(min_length=1, max_length=40)
    currency: Literal['INR', 'USD', 'EUR', 'GBP'] = 'INR'
    start_at: AwareDatetime
    close_at: AwareDatetime
    forced_close_at: AwareDatetime
    service_date: date
    british_enabled: bool = Field(default=True, strict=True)
    trigger_minutes: Minutes
    extension_minutes: Minutes
    triggers: list[Trigger]

    @field_validator('name', 'reference')
    @classmethod
    def normalize_text(cls, value):
        return ' '.join(value.split())

    @model_validator(mode='after')
    def validate_configuration(self):
        if not self.start_at < self.close_at < self.forced_close_at:
            raise ValueError('Start must be before bid close; forced close must be strictly later than bid close.')
        if self.british_enabled and not self.triggers:
            raise ValueError('Select at least one extension trigger for a British Auction.')
        return self


class QuoteCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    carrier: str = Field(min_length=1, max_length=80)
    freight: Money
    origin: Money
    destination: Money
    transit_days: int = Field(strict=True, ge=1, le=3650)
    valid_until: AwareDatetime

    @field_validator('carrier')
    @classmethod
    def normalize_carrier(cls, value):
        return ' '.join(value.split())

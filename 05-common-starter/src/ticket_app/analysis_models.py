from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    subject: str = Field(min_length=3, max_length=100)
    text: str = Field(min_length=10, max_length=4000)

    @field_validator("subject", "text")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Input must contain text")
        return value.strip()


class Analysis(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    summary: str = Field(min_length=10, max_length=240)
    category: str = Field(min_length=1, max_length=40)
    priority: Literal["low", "medium", "high"]
    next_action: str = Field(min_length=10, max_length=240)

    @field_validator("summary", "next_action", "category")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Output must contain text")
        return value.strip()


class Record(BaseModel):
    id: str
    scenario: str
    provider: str
    analysis: Analysis
    requires_review: bool = True

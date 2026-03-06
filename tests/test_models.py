from datetime import datetime
from typing import Optional

from clawops._models import BaseModel


class SampleModel(BaseModel):
    user_name: str
    created_at: datetime
    display_name: Optional[str] = None
    from_: Optional[str] = None


def test_camel_case_alias_deserialization():
    data = {"userName": "john", "createdAt": "2025-01-01T00:00:00Z", "displayName": "John Doe"}
    obj = SampleModel.model_validate(data)
    assert obj.user_name == "john"
    assert obj.display_name == "John Doe"


def test_snake_case_access():
    obj = SampleModel(user_name="john", created_at=datetime(2025, 1, 1))
    assert obj.user_name == "john"


def test_camel_case_serialization():
    obj = SampleModel(user_name="john", created_at=datetime(2025, 1, 1))
    dumped = obj.model_dump(by_alias=True)
    assert "userName" in dumped
    assert "createdAt" in dumped


def test_extra_fields_allowed():
    data = {"userName": "john", "createdAt": "2025-01-01T00:00:00Z", "newField": "ok"}
    obj = SampleModel.model_validate(data)
    assert obj.user_name == "john"


def test_trailing_underscore_alias():
    data = {"userName": "john", "createdAt": "2025-01-01T00:00:00Z", "from": "07012345678"}
    obj = SampleModel.model_validate(data)
    assert obj.from_ == "07012345678"
    dumped = obj.model_dump(by_alias=True)
    assert "from" in dumped
    assert dumped["from"] == "07012345678"

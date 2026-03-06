from clawops._utils import to_camel_case, strip_not_given, PropertyInfo


def test_to_camel_case_simple():
    assert to_camel_case("account_id") == "accountId"


def test_to_camel_case_single_word():
    assert to_camel_case("status") == "status"


def test_to_camel_case_multiple_underscores():
    assert to_camel_case("date_created_at") == "dateCreatedAt"


def test_to_camel_case_trailing_underscore():
    assert to_camel_case("from_") == "from"


def test_strip_not_given_removes_none():
    data = {"a": 1, "b": None, "c": "hello"}
    assert strip_not_given(data) == {"a": 1, "c": "hello"}


def test_strip_not_given_empty():
    assert strip_not_given({}) == {}


def test_property_info():
    info = PropertyInfo(alias="From")
    assert info.alias == "From"

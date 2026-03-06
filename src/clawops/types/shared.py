from __future__ import annotations

from .._models import BaseModel


class PaginationMeta(BaseModel):
    """페이지네이션 메타데이터.

    Attributes:
        total: 전체 항목 수.
        page: 현재 페이지 번호 (0부터 시작).
        page_size: 페이지당 항목 수.
    """

    total: int
    page: int
    page_size: int

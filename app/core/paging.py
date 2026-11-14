"""Shared paging and sorting for list endpoints.

Every list takes ?limit=&offset=&sort= and answers with
{"items": [...], "total": N, "limit": L, "offset": O}.
"""

from collections.abc import Callable, Mapping
from typing import Any, Literal

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session


class Page[Item](BaseModel):
    """One page of a list. total counts every matching row, not just this page."""

    items: list[Item]
    total: int
    limit: int
    offset: int


class Pagination:
    """limit (1 to 100, default 20) and offset (0 or more) query parameters.

    Values out of range are rejected with 422, so no list is ever unbounded.
    """

    def __init__(
        self,
        limit: int = Query(20, ge=1, le=100, description="Items per page (1 to 100)"),
        offset: int = Query(0, ge=0, description="How many items to skip"),
    ):
        self.limit = limit
        self.offset = offset


def sort_param(fields: Mapping[str, InstrumentedAttribute], default: str, tie_breaker: InstrumentedAttribute):
    """Build a dependency for a ?sort= parameter that only accepts the given fields.

    "name" sorts ascending, "-name" descending. Anything else is a 422 (FastAPI
    checks it against the allowed values, which also lists them in /docs).
    tie_breaker (the id) is always added last, so rows with equal values keep
    the same order on every page.
    """
    allowed = tuple(option for name in fields for option in (name, f"-{name}"))
    SortValue = Literal[allowed]  # noqa: N806  (a type, built from the allowed values)

    def dependency(
        sort: SortValue = Query(default, description="Field to sort by; a leading minus sorts descending"),  # type: ignore[valid-type]
    ) -> list[Any]:
        descending = sort.startswith("-")
        column = fields[sort.removeprefix("-")]
        return [column.desc() if descending else column.asc(), tie_breaker.asc()]

    return dependency


def count(db: Session, query: Select) -> int:
    """How many rows the query matches in all (ignoring limit, offset and order)."""
    return db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))


def paginate[Row, Item](
    db: Session,
    query: Select,
    page: Pagination,
    order_by: list[Any],
    to_item: Callable[[Row], Item] | None = None,
) -> Page[Item]:
    rows = db.scalars(query.order_by(*order_by).limit(page.limit).offset(page.offset)).all()
    items = [to_item(row) for row in rows] if to_item else list(rows)
    return Page(items=items, total=count(db, query), limit=page.limit, offset=page.offset)


def like_pattern(text: str) -> str:
    """A LIKE pattern matching text anywhere, with its own % and _ taken literally.

    Used with a bound parameter and escape="\\", never pasted into SQL.
    """
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"

"""Shared paging and sorting, tested through GET /api/v1/users."""

import pytest
from sqlalchemy import select, update

from app.models import Role, User
from tests.helpers import assert_error, headers_for


@pytest.fixture
def pharmacy_with_users(make_pharmacy, make_user):
    """A pharmacy with an owner plus 24 staff: 25 users in all.
    Returns (owner headers, every user)."""
    pharmacy = make_pharmacy()
    owner = make_user(pharmacy, role=Role.OWNER, full_name="Aaron Owner")
    staff = [make_user(pharmacy, full_name=f"Staff {n:02d}") for n in range(24)]
    return headers_for(owner), [owner, *staff]


def list_users(client, headers, **params):
    return client.get("/api/v1/users", headers=headers, params=params)


def test_defaults_limit_20_offset_0(client, pharmacy_with_users):
    headers, users = pharmacy_with_users

    body = list_users(client, headers).json()

    assert set(body) == {"items", "total", "limit", "offset"}
    assert (body["limit"], body["offset"]) == (20, 0)
    assert len(body["items"]) == 20
    assert body["total"] == 25  # every matching row, not just this page


def test_total_is_correct_on_every_page(client, pharmacy_with_users):
    headers, users = pharmacy_with_users
    seen = []

    for offset in (0, 10, 20):
        body = list_users(client, headers, limit=10, offset=offset).json()
        assert body["total"] == 25
        assert (body["limit"], body["offset"]) == (10, offset)
        seen += [item["id"] for item in body["items"]]

    assert len(seen) == 25 and len(set(seen)) == 25  # each user exactly once
    assert set(seen) == {str(u.id) for u in users}


def test_offset_past_the_end_gives_an_empty_page(client, pharmacy_with_users):
    headers, _ = pharmacy_with_users

    body = list_users(client, headers, offset=500).json()

    assert body["items"] == []
    assert body["total"] == 25


@pytest.mark.parametrize("limit", [1, 100])
def test_limit_bounds_are_allowed(client, pharmacy_with_users, limit):
    headers, _ = pharmacy_with_users

    body = list_users(client, headers, limit=limit).json()

    assert body["limit"] == limit
    assert len(body["items"]) == min(limit, 25)


@pytest.mark.parametrize(
    "params, field",
    [
        ({"limit": 0}, "limit"),
        ({"limit": 101}, "limit"),
        ({"limit": -1}, "limit"),
        ({"offset": -1}, "offset"),
        ({"sort": "password_hash"}, "sort"),
        ({"sort": "pharmacy_id"}, "sort"),
        ({"sort": "--full_name"}, "sort"),
        ({"sort": ""}, "sort"),
    ],
)
def test_out_of_range_paging_and_unknown_sort_return_422(client, pharmacy_with_users, params, field):
    headers, _ = pharmacy_with_users

    error = assert_error(list_users(client, headers, **params), 422, "validation_error")

    assert [(d["location"], d["field"]) for d in error["details"]] == [("query", field)]


def database_order(db, sort: str) -> list[str]:
    """User ids in the order PostgreSQL itself sorts them (its text collation
    can differ from Python's sorted() on punctuation), with id as tie breaker."""
    column = getattr(User, sort.removeprefix("-"))
    order = column.desc() if sort.startswith("-") else column.asc()
    return [str(i) for i in db.scalars(select(User.id).order_by(order, User.id))]


def test_default_sort_is_full_name(client, db, pharmacy_with_users):
    headers, _ = pharmacy_with_users

    ids = [item["id"] for item in list_users(client, headers, limit=100).json()["items"]]

    assert ids == database_order(db, "full_name")


def test_descending_sort(client, db, pharmacy_with_users):
    headers, _ = pharmacy_with_users

    items = list_users(client, headers, limit=100, sort="-full_name").json()["items"]

    assert [item["id"] for item in items] == database_order(db, "-full_name")
    assert items[0]["full_name"] == "Staff 23"
    assert items[-1]["full_name"] == "Aaron Owner"


@pytest.mark.parametrize("sort", ["full_name", "-full_name", "email", "-email", "created_at", "-created_at"])
def test_every_allowed_sort_field_works(client, db, pharmacy_with_users, sort):
    headers, _ = pharmacy_with_users

    items = list_users(client, headers, limit=100, sort=sort).json()["items"]

    assert [item["id"] for item in items] == database_order(db, sort)


def test_equal_values_keep_a_stable_order_across_pages(client, db, pharmacy_with_users):
    headers, users = pharmacy_with_users
    # Give everyone the same name and creation time, so only the id tie breaker orders them
    db.execute(update(User).values(full_name="Same Name", created_at=users[0].created_at))
    db.commit()

    for sort in ("full_name", "-full_name", "created_at", "-created_at"):
        paged = []
        for offset in range(0, 25, 7):
            paged += [i["id"] for i in list_users(client, headers, limit=7, offset=offset, sort=sort).json()["items"]]
        # No user skipped or repeated, and the order is by id
        assert paged == sorted(str(u.id) for u in users), sort

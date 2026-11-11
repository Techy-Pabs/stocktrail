"""Two owners demoting each other at the same moment must not leave the
pharmacy with no active owner. update_user locks the pharmacy row, so the
second change waits for the first, then sees only one owner left."""

import threading

import pytest
from sqlalchemy import select

from app.models import Pharmacy, Role, User
from app.services import users as service


def test_concurrent_demotions_leave_one_active_owner(session_factory, make_pharmacy, make_user):
    pharmacy = make_pharmacy()
    first = make_user(pharmacy, role=Role.OWNER)
    second = make_user(pharmacy, role=Role.OWNER)

    holder = session_factory()
    waiter = session_factory()
    try:
        # Request 1 has taken the lock and is about to demote the first owner
        holder.execute(select(Pharmacy.id).where(Pharmacy.id == pharmacy.id).with_for_update())

        # Request 2 tries to demote the second owner at the same time: it must wait
        result = {}

        def demote_second():
            try:
                service.update_user(waiter, waiter.get(User, second.id), role=Role.STAFF)
                result["outcome"] = "demoted"
            except service.LastActiveOwner:
                result["outcome"] = "refused"

        thread = threading.Thread(target=demote_second)
        thread.start()
        thread.join(timeout=1)
        assert thread.is_alive(), "the second demotion should be waiting for the lock"

        # Request 1 finishes: the first owner is demoted and the lock released
        service.update_user(holder, holder.get(User, first.id), role=Role.STAFF)
        thread.join(timeout=10)
        assert not thread.is_alive()

        # Request 2 counted again after waiting, and saw it was the last owner
        assert result["outcome"] == "refused"
    finally:
        holder.close()
        waiter.close()

    check = session_factory()
    active_owners = check.scalars(
        select(User).where(User.pharmacy_id == pharmacy.id, User.role == Role.OWNER, User.is_active.is_(True))
    ).all()
    check.close()
    assert [u.id for u in active_owners] == [second.id]


@pytest.mark.parametrize("change", [{"role": Role.MANAGER}, {"is_active": False}])
def test_service_refuses_last_owner_change(db, make_pharmacy, make_user, change):
    owner = make_user(make_pharmacy(), role=Role.OWNER)

    with pytest.raises(service.LastActiveOwner):
        service.update_user(db, owner, **change)

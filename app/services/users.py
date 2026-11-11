"""User management inside one pharmacy. Every function takes the pharmacy
from the caller (the logged in owner), never from the request."""

import uuid

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.paging import like_pattern
from app.core.security import hash_password
from app.models import Pharmacy, Role, User

# Name of the unique constraint on users.email (from the naming convention)
EMAIL_UNIQUE_CONSTRAINT = "uq_users_email"

LAST_OWNER_MESSAGE = (
    "This is the pharmacy's last active owner, so they can't be demoted or deactivated. "
    "Make another user an owner first."
)


class EmailAlreadyRegistered(Exception):
    pass


class LastActiveOwner(Exception):
    pass


def is_duplicate_email(error: IntegrityError) -> bool:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == EMAIL_UNIQUE_CONSTRAINT


def email_taken(db: Session, email: str) -> bool:
    # Across every pharmacy: one account per email
    return db.scalar(select(User.id).where(User.email == email.lower())) is not None


def commit_new_user(db: Session, user: User) -> User:
    """Add and commit a new user (and anything added with it) in one transaction.

    Raises EmailAlreadyRegistered if the email is taken, including when two
    requests race and the database's unique constraint stops the second.
    """
    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if is_duplicate_email(error):
            raise EmailAlreadyRegistered from None
        raise
    return user


def create_user(db: Session, *, pharmacy_id: uuid.UUID, email: str, full_name: str, role: Role, password: str) -> User:
    if email_taken(db, email):
        raise EmailAlreadyRegistered
    user = User(
        pharmacy_id=pharmacy_id,
        email=email,
        full_name=full_name,
        role=role,
        password_hash=hash_password(password),
    )
    commit_new_user(db, user)
    db.refresh(user)
    return user


def users_query(
    pharmacy_id: uuid.UUID, *, role: Role | None = None, is_active: bool | None = None, q: str | None = None
) -> Select:
    """The pharmacy's users matching the filters (no order: the caller sorts)."""
    query = select(User).where(User.pharmacy_id == pharmacy_id)
    if role is not None:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    if q:
        pattern = like_pattern(q)
        query = query.where(or_(User.full_name.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\")))
    return query


def get_pharmacy_user(db: Session, pharmacy_id: uuid.UUID, user_id: uuid.UUID) -> User | None:
    """The user, only if they belong to this pharmacy. A user from another
    pharmacy is treated exactly like one that doesn't exist."""
    return db.scalar(select(User).where(User.id == user_id, User.pharmacy_id == pharmacy_id))


def update_user(
    db: Session, user: User, *, full_name: str | None = None, role: Role | None = None, is_active: bool | None = None
) -> User:
    """Change a user's name, role or active flag. None means "leave as is".

    Raises LastActiveOwner if the change would leave the pharmacy without an
    active owner.
    """
    stays_active_owner = (role or user.role) == Role.OWNER and (user.is_active if is_active is None else is_active)
    if user.role == Role.OWNER and user.is_active and not stays_active_owner:
        # Lock the pharmacy row until this transaction ends, so two owners
        # demoting each other at the same moment can't both succeed: the
        # second waits, then counts again and sees only one owner left.
        db.execute(select(Pharmacy.id).where(Pharmacy.id == user.pharmacy_id).with_for_update())
        active_owners = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.pharmacy_id == user.pharmacy_id, User.role == Role.OWNER, User.is_active.is_(True))
        )
        if active_owners <= 1:
            db.rollback()
            raise LastActiveOwner

    if full_name is not None:
        user.full_name = full_name
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user


def set_password(db: Session, user: User, new_password: str) -> int:
    """Save a new password and revoke every token the user had. Returns the new token version.

    The version is raised in SQL (token_version + 1), so two changes at the
    same moment can't both write the same number.
    """
    new_version = db.scalar(
        update(User)
        .where(User.id == user.id)
        .values(password_hash=hash_password(new_password), token_version=User.token_version + 1)
        .returning(User.token_version)
    )
    db.commit()
    db.refresh(user)
    return new_version

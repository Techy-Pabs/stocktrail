from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Pharmacy, Role, User

# Name of the unique constraint on users.email (from the naming convention)
EMAIL_UNIQUE_CONSTRAINT = "uq_users_email"


class EmailAlreadyRegistered(Exception):
    pass


def _is_duplicate_email(error: IntegrityError) -> bool:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == EMAIL_UNIQUE_CONSTRAINT


def register_pharmacy_with_owner(db: Session, *, pharmacy_name: str, full_name: str, email: str, password: str) -> User:
    """Create a pharmacy and its owner in one database transaction.

    Both rows are saved by the same commit, so if either insert fails
    (for example the email is taken) the rollback removes both: there is
    never a pharmacy without an owner, or an owner without a pharmacy.
    """
    email = email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise EmailAlreadyRegistered

    # Hashing is slow on purpose, so do it before starting to write
    password_hash = hash_password(password)

    pharmacy = Pharmacy(name=pharmacy_name)
    owner = User(
        pharmacy=pharmacy,
        email=email,
        full_name=full_name,
        password_hash=password_hash,
        role=Role.OWNER,
    )
    # Adding the owner adds the pharmacy too (through the relationship)
    db.add(owner)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        # Two sign-ups with the same email at the same moment: the check above
        # passes for both, and the unique constraint stops the second one.
        if _is_duplicate_email(error):
            raise EmailAlreadyRegistered from None
        raise
    return owner

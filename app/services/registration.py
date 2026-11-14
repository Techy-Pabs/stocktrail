from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Pharmacy, Role, User
from app.services.users import EmailAlreadyRegistered, commit_new_user, email_taken


def register_pharmacy_with_owner(db: Session, *, pharmacy_name: str, full_name: str, email: str, password: str) -> User:
    """Create a pharmacy and its owner in one database transaction.

    Both rows are saved by the same commit, so if either insert fails
    (for example the email is taken) the rollback removes both: there is
    never a pharmacy without an owner, or an owner without a pharmacy.
    """
    if email_taken(db, email):
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
    return commit_new_user(db, owner)

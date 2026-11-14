# Import every model here so they all register on Base.metadata.
# Alembic imports this package to see the full set of tables.
from app.models.pharmacy import Pharmacy
from app.models.product import Product, ProductForm
from app.models.user import Role, User

__all__ = ["Pharmacy", "Product", "ProductForm", "Role", "User"]

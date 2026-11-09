# — demonstracijski materiali in dobavitelji.
"""Ročna priprava demonstracijskega šifranta, brez prejemov ali sprememb zaloge."""
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Material, MaterialType, Supplier


def main():
    created = 0
    with SessionLocal() as db:
        for name in ("Sadje d.o.o.", "Embalaža d.o.o."):
            if db.scalar(select(Supplier).where(Supplier.name == name)) is None:
                db.add(Supplier(name=name))
                created += 1
        for name, material_type, unit in (
            ("Jabolčni koncentrat", MaterialType.ingredient, "kg"),
            ("Sladkor", MaterialType.ingredient, "kg"),
            ("Plastenka 1 L", MaterialType.packaging, "kos"),
        ):
            if db.scalar(select(Material).where(
                Material.name == name, Material.type == material_type, Material.unit == unit,
            )) is None:
                db.add(Material(name=name, type=material_type, unit=unit, min_stock=Decimal("0")))
                created += 1
        db.commit()
    print(f"Šifrant je pripravljen. Dodanih zapisov: {created}.")


if __name__ == "__main__":
    main()

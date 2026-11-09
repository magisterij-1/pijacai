"""Priprava demonstracijskih parametrov brez spreminjanja obstoječih mej ali meritev."""
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Product, QualityParameter


def main():
    created = 0
    with SessionLocal() as db:
        product = db.scalar(select(Product).where(Product.sku == "SOK-JAB-1L"))
        if product is None:
            print("Najprej pripravi demonstracijski izdelek: python -m app.seed_production")
            return
        for name, unit, lower, upper in (
            ("pH", "pH", "2.8", "4.0"),
            ("CO₂", "g/L", "0", "1.0"),
            ("Nivo polnjenja", "ml", "990", "1010"),
        ):
            if db.scalar(select(QualityParameter.id).where(QualityParameter.product_id == product.id, QualityParameter.name == name)) is None:
                db.add(QualityParameter(product_id=product.id, name=name, unit=unit,
                                        min_value=Decimal(lower), max_value=Decimal(upper)))
                created += 1
        db.commit()
    print(f"Demonstracijski parametri kakovosti so pripravljeni. Dodanih: {created}.")


if __name__ == "__main__":
    main()

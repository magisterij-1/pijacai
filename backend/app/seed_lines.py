"""Ročna priprava začetnih linij; obstoječih linij ne aktivira ponovno."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import ProductionLine


def main():
    created = 0
    with SessionLocal() as db:
        for name in ("Linija 1", "Linija 2"):
            if db.scalar(select(ProductionLine).where(ProductionLine.name == name)) is None:
                db.add(ProductionLine(name=name))
                created += 1
        db.commit()
    print(f"Linije so pripravljene. Dodanih: {created}.")


if __name__ == "__main__":
    main()

"""Ročno ustvarjanje začetnega uporabnika za lokalni preizkus prijave."""
from getpass import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.database import SessionLocal
from app.models import Role, User


def main():
    email = input("E-pošta začetnega administratorja: ").strip()
    name = input("Ime: ").strip()
    if not email or "@" not in email or len(email) > 255 or not name or len(name) > 120:
        raise SystemExit("Vnesi veljavno e-pošto in ime.")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit("Uporabnik s to e-pošto že obstaja; podatki niso bili spremenjeni.")
        password = getpass("Geslo (najmanj 8 znakov, največ 72 UTF-8 bajtov): ")
        if len(password) < 8 or len(password.encode("utf-8")) > 72:
            raise SystemExit("Geslo mora imeti najmanj 8 znakov in največ 72 UTF-8 bajtov.")
        if password != getpass("Ponovi geslo: "):
            raise SystemExit("Gesli se ne ujemata.")
        db.add(User(name=name, email=email, password_hash=hash_password(password), role=Role.admin))
        db.commit()
    print("Začetni administrator je ustvarjen.")


if __name__ == "__main__":
    main()

# Pijacai
:)
Pijacai je spletni sistem za vodenje proizvodnih šarž v manjši polnilnici pijač. Omogoča načrtovanje proizvodnih nalogov, evidentiranje surovin in njihove porabe, kontrolo kakovosti ter sledljivost med serijami surovin in končnimi šaržami.

## Tehnologije

- **Frontend:** React, TypeScript in Vite
- **Backend:** Python in FastAPI
- **Podatkovna baza:** PostgreSQL
- **Dostop do podatkov in migracije:** SQLAlchemy in Alembic
- **Zagon okolja:** Docker Compose


## Lokalni zagon

Potrebuješ zagnan Docker Desktop z Linux kontejnerji in Docker Compose. Ukaze izvajaj v korenski mapi projekta.

Ob prvi postavitvi ustvari lokalno konfiguracijo:

```powershell
Copy-Item .env.example .env
```

Nastavitve prilagodi v `.env`, ki ostane lokalna. Nato zaženi aplikacijo:

```powershell
docker compose up --build
```

- Aplikacija: [http://localhost:5174](http://localhost:5174)
- API dokumentacija: [http://localhost:8001/docs](http://localhost:8001/docs)
- PostgreSQL: `localhost:5433`

Backend pred zagonom samodejno izvede migracije baze. Za prvo prijavo v drugem terminalu ustvari začetnega administratorja:

```powershell
docker compose exec backend python -m app.seed
```

Sledi pozivom za ime, e-pošto in geslo, nato se prijavi v aplikaciji. Obstoječega računa ni treba ustvariti znova.

Za ustavitev uporabi:

```powershell
docker compose down
```

Podatki baze se ohranijo v Dockerjevem volumnu.

## Dokumentacija

- [Zasnova rešitve](docs/01-zasnova-resitve.md)
- [Funkcionalnosti in obseg](docs/02-funkcionalnosti-in-obseg.md)
- [Podatkovni model](docs/03-podatkovni-model.md)
- [Arhitektura in tehnološki sklad](docs/04-arhitektura-in-tehnoloski-sklad.md)
- [Uporabniške zgodbe](docs/05-uporabniske-zgodbe.md)
- [Wireframes](docs/06-wireframes.md)
- [Arhitekturne odločitve (ADR)](docs/adr/)

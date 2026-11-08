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

### Zahteve

- Docker Desktop z vključenimi Linux kontejnerji in Docker Compose.
- Node.js 22 in npm za pripravo `frontend/package-lock.json` ob začetni postavitvi.

Ukaze izvajaj v korenski mapi repozitorija. Docker Desktop mora biti zagnan.

Ob prvi postavitvi v PowerShellu ustvari lokalno konfiguracijo:

```powershell
Copy-Item .env.example .env
```

Datoteka `.env` ostane lokalna. Primer vsebuje nastavitve za razvoj na lastnem računalniku. Če v njej spremeniš geslo baze, uporabi znake, ki so veljavni tudi v povezovalnem URL, oziroma jih ustrezno URL-kodiraj.

Ob začetni pripravi projekta ustvari datoteko z zaklenjenimi različicami npm odvisnosti:

```powershell
npm install --package-lock-only --prefix frontend
```

Datoteko `frontend/package-lock.json` dodaj v isti commit kot razvojno okolje. Po kloniranju repozitorija, ki že vsebuje to datoteko, ta korak ni potreben. Docker pri gradnji namesti odvisnosti z `npm ci`.

Zaženi vse tri storitve:

```powershell
docker compose up --build
```

- Aplikacija: [http://localhost:5174](http://localhost:5174)
- API dokumentacija: [http://localhost:8001/docs](http://localhost:8001/docs)
- Preverjanje API in baze: [http://localhost:8001/api/health](http://localhost:8001/api/health)
- PostgreSQL za lokalna orodja: `localhost:5433`.

Začetna stran prikaže stanje povezave z API in PostgreSQL. Endpoint `/api/health` ob uspehu vrne `{"status":"ok","database":"ok"}`, ob nedosegljivi bazi pa HTTP 503.

PostgreSQL hrani podatke v Dockerjevem imenovanem volumnu `pijacai-db`. Vrata baze in aplikacije so objavljena samo na lokalnem računalniku (`127.0.0.1`). Backend se zažene po pripravljenosti baze, frontend pa po pripravljenosti backenda. Vrata lahko spremeniš v `.env` z nastavitvami `DB_PORT`, `BACKEND_PORT` in `FRONTEND_PORT`. Med kontejnerji backend dostopa do baze prek `db:5432`.

### Preverjanje in ustavitev

V drugem terminalu preveri stanje storitev in frontend:

```powershell
docker compose ps
Invoke-RestMethod http://localhost:8001/api/health
docker compose exec frontend npm run check
docker compose exec frontend npm run build
```

Če si spremenil `BACKEND_PORT`, prilagodi naslov v ukazu za preverjanje API.

Za pregled dnevnikov in ustavitev uporabi:

```powershell
docker compose logs backend
docker compose down
```

Ukaz `docker compose down` ohrani podatke baze. Sprememba uporabniškega imena ali gesla v `.env` ne spremeni prijavnih podatkov že inicializiranega PostgreSQL volumna.

### Podatkovni model in migracije

Backend pred zagonom API samodejno izvede `alembic upgrade head`. Če migracija ne uspe, se API ne zažene. Obstoječi podatki v volumnu ostanejo ohranjeni.

Prva migracija ustvari tabelo `app_user` s polji `id`, `name`, `email`, `password_hash`, `role`, `active` in `created_at`. E-pošta je enolična, vloga je omejena na `operator`, `quality`, `planner`, `warehouse` in `admin`. Polja so obvezna; aktivnost in čas nastanka imata privzeti vrednosti v bazi. Model vsebuje samo polje za zgoščeno geslo; zgoščevanje in preverjanje gesel sledita pri implementaciji prijave.

Po spremembi modelov in migracij ponovno zgradi in zaženi okolje:

```powershell
docker compose up --build
```

V drugem terminalu preveri uporabljeno migracijo in skladnost modelov s podatkovno bazo:

```powershell
docker compose exec backend alembic current
docker compose exec backend alembic check
docker compose exec db psql -U pijacai -d pijacai -c '\d app_user'
```

Pričakovana revizija je `0001_create_app_user (head)`, `alembic check` pa ne sme zaznati novih operacij za migracijo. Ukaz `psql` uporablja uporabnika in bazo iz `.env.example`; če si ju spremenil, prilagodi argumenta `-U` in `-d`. Tabela je za zdaj prazna; dodajanje uporabnikov in prijava sledita v naslednjih nalogah.

### Trenutni obseg

Pripravljeno je osnovno razvojno okolje s preverjanjem povezave frontend → API → PostgreSQL ter model uporabnika s prvo Alembic migracijo (F1, US-01, naloga 1). Preostale MVP funkcionalnosti F1–F7 se bodo dodajale postopoma.

## Dokumentacija

- [Zasnova rešitve](docs/01-zasnova-resitve.md)
- [Funkcionalnosti in obseg](docs/02-funkcionalnosti-in-obseg.md)
- [Podatkovni model](docs/03-podatkovni-model.md)
- [Arhitektura in tehnološki sklad](docs/04-arhitektura-in-tehnoloski-sklad.md)
- [Uporabniške zgodbe](docs/05-uporabniske-zgodbe.md)
- [Wireframes](docs/06-wireframes.md)
- [Arhitekturne odločitve (ADR)](docs/adr/)

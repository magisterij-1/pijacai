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

Prva migracija ustvari tabelo `app_user` s polji `id`, `name`, `email`, `password_hash`, `role`, `active` in `created_at`. E-pošta je enolična, vloga je omejena na `operator`, `quality`, `planner`, `warehouse` in `admin`. Polja so obvezna; aktivnost in čas nastanka imata privzeti vrednosti v bazi. Model vsebuje samo polje za zgoščeno geslo; zgoščevanje in preverjanje gesel sta del implementacije prijave.

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

Pričakovana revizija je `0001_create_app_user (head)`, `alembic check` pa ne sme zaznati novih operacij za migracijo. Ukaz `psql` uporablja uporabnika in bazo iz `.env.example`; če si ju spremenil, prilagodi argumenta `-U` in `-d`. Uporabniki se ne ustvarijo samodejno.

### API za prijavo

Odločitev o JWT je zapisana v [ADR 0007](docs/adr/0007-jwt-avtentikacija.md), ki nadomešča [ADR 0005](docs/adr/0005-avtentikacija-in-seje.md). Stari ADR je ohranjen in označen kot nadomeščen. Poti API uporabljajo predpono `/api`; pot `/auth/login` iz zasnove je v aplikaciji dosegljiva kot `/api/auth/login`.

V `.env` dodaj `JWT_SECRET` po vzoru `.env.example`. Ključ mora vsebovati najmanj 32 bajtov; za okolje izven lokalnega razvoja uporabi dolg naključen ključ namesto razvojne vrednosti iz primera. Po spremembi konfiguracije in odvisnosti zaženi `docker compose up --build`.

Pred prvim preizkusom ročno ustvari začetnega administratorja:

```powershell
docker compose exec backend python -m app.seed
```

Ukaz vpraša za ime, e-pošto in geslo. Geslo mora imeti najmanj 8 znakov in največ 72 UTF-8 bajtov, pri vnosu se ne izpisuje in se shrani samo kot bcrypt zgoščena vrednost. Ob obstoječi e-pošti ukaz ne spremeni računa. To je lokalni ukaz za začetno postavitev, ne javna registracija ali administratorski API.

V Swagger UI na `http://localhost:8001/docs` odpri `POST /api/auth/login`, izberi **Try it out** in vnesi podatke ustvarjenega uporabnika:

```json
{
  "email": "tvoja-vnesena-eposta@example.com",
  "password": "tvoje-vneseno-geslo"
}
```

Uspešna prijava vrne `access_token`, `token_type`, `expires_in` (3600 sekund) in javne podatke uporabnika. Žeton vsebuje `sub`, `role`, `iat` in `exp`. Napačna e-pošta, napačno geslo ali neaktiven uporabnik vrnejo HTTP 401 s sporočilom »Napačna e-pošta ali geslo.« Odgovor ne vsebuje gesla ali njegove zgoščene vrednosti.

Avtomatske teste prijave zaženi v razvojnem kontejnerju:

```powershell
docker compose exec backend pip install -r requirements-dev.txt
docker compose exec backend python -m pytest tests -q
```

Testi uporabljajo nadomestno podatkovno sejo in ne spreminjajo PostgreSQL podatkov. Preverjajo uspešno izdajo in podpis žetona, življenjsko dobo, enotno napako 401, odsotnost gesla v odgovoru, bcrypt in CORS. Namestitev testnih odvisnosti ponoviš, če ponovno ustvariš kontejner in želiš izvajati teste.

### Prijavni obrazec

Odpri `http://localhost:5174` in se prijavi z računom, ustvarjenim z `python -m app.seed`. Obrazec zahteva veljavno obliko e-pošte in vnos gesla. Med pošiljanjem je gumb onemogočen; napačni podatki prikažejo »Napačna e-pošta ali geslo.«, nedosegljiv API pa sporočilo o neuspešni povezavi. Geslo se po poskusu počisti.

Po uspehu se prikaže začetni pogled glede na uporabnikovo vlogo: skladišče, načrtovanje proizvodnje, proizvodnja, kontrola kakovosti ali upravljanje uporabnikov. Ti pogledi so za zdaj osnovni; poslovni obrazci sledijo v pripadajočih Issues.

Prijava se trenutno hrani samo v pomnilniku aplikacije. Po osvežitvi strani se znova prikaže prijavni obrazec. Obnova prijave, odjava in odziv na potek žetona so del naslednje naloge US-01/4. Zaščita API in dostopa do strani po vlogah je del US-02.

Preveri uspešno prijavo, napačno geslo, prazen obrazec in neveljavno obliko e-pošte. Preveri tudi uporabo tipkovnice in prikaz na ozkem zaslonu. Po spremembah ponovno zgradi frontend in preveri TypeScript:

```powershell
docker compose up --build
```

V drugem terminalu:

```powershell
docker compose exec frontend npm run check
docker compose exec frontend npm run build
```

### Trenutni obseg

Pripravljeno je osnovno razvojno okolje, model uporabnika z migracijo, API za prijavo z JWT in prijavni obrazec z začetnimi pogledi po vlogah (F1, US-01, naloge 1–3). Ravnanje odjemalca ob poteku prijave ter preverjanje uporabnika in vlog na zaščitenih končnih točkah sledijo v naslednjih nalogah. Žeton že vsebuje potek po 60 minutah; preverjanje poteka pri zaščitenih zahtevkih še ni implementirano.

## Dokumentacija

- [Zasnova rešitve](docs/01-zasnova-resitve.md)
- [Funkcionalnosti in obseg](docs/02-funkcionalnosti-in-obseg.md)
- [Podatkovni model](docs/03-podatkovni-model.md)
- [Arhitektura in tehnološki sklad](docs/04-arhitektura-in-tehnoloski-sklad.md)
- [Uporabniške zgodbe](docs/05-uporabniske-zgodbe.md)
- [Wireframes](docs/06-wireframes.md)
- [Arhitekturne odločitve (ADR)](docs/adr/)

# Ločen spletni uporabniški vmesnik in zaledni API

**Status:** Proposed

## Context and Problem Statement

Pijacai uporablja več uporabniških vlog, ki potrebujejo različne obrazce in preglede. Poslovna pravila, kot sta preverjanje zalog ob zagonu šarže in preverjanje meritev pred sprostitvijo, morajo veljati za vse uporabnike. Arhitektura mora jasno razmejiti prikaz, poslovna pravila in dostop do podatkov, hkrati pa ostati dovolj preprosta za MVP.

## Considered Options

* Strežniško upodobljena aplikacija, na primer Django.
* React SPA in REST API z Django REST Framework.
* React SPA in REST API s FastAPI.
* React SPA in REST API z Node.js/Express.
* Mikrostoritve za posamezna poslovna področja.

## Decision Outcome

Chosen option: "React SPA in REST API s FastAPI, organiziran kot modularni monolit", because ta pristop loči uporabniški vmesnik od pravil, ki morajo biti avtoritativno uveljavljena na strežniku, obenem pa se izogne operativni kompleksnosti mikrostoritev. FastAPI izberemo zaradi validacije vhodnih podatkov in samodejnega OpenAPI opisa, kar olajša razvoj ter pregled API-ja. React in TypeScript zagotovita ločen komponentni uporabniški vmesnik. Backend bo odgovoren za poslovna pravila in dostop do podatkov.

### Consequences

* Good, because poslovna pravila in preverjanje uporabniških vlog se izvajajo na enem mestu ne glede na odjemalca.
* Good, because API je mogoče dokumentirati in pozneje uporabiti z drugim odjemalcem, če se pojavi zahteva.
* Bad, because ločen SPA in API zahtevata dodatno konfiguracijo komunikacije, CORS-a in prijave.
* Bad, because React in API zahtevata usklajeno obravnavo napak, validacije in stanja v uporabniškem vmesniku.
* Bad, because modularni monolit ne omogoča neodvisnega skaliranja posameznih modulov; za predvideni obseg MVP to ni zahteva.

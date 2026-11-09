<!-- — veljavna odločitev o prijavi z JWT. -->
# Prijava z JWT in preverjanje uporabnika na backendu

**Status:** Accepted

## Context and Problem Statement

Pogoji sprejemljivosti US-01 in US-02 ter arhitektura predvidevajo prijavo z JWT. Enak pristop uporablja izvorna aplikacija. Potrebujemo enoten način prijave, ki ga lahko preverimo prek API in pozneje uporabimo v React vmesniku.

Ta odločitev nadomesti [ADR 0005 o strežniških sejah](0005-avtentikacija-in-seje.md). Stari dokument ostane ohranjen in je označen kot nadomeščen.

## Considered Options

* Strežniška seja z identifikatorjem v piškotku.
* Podpisan JWT dostopni žeton, poslan v glavi Authorization.

## Decision Outcome

Uporabimo JWT, podpisan z algoritmom HS256. Žeton vsebuje identifikator uporabnika (`sub`), vlogo (`role`), čas izdaje (`iat`) in čas poteka (`exp`). Veljaven je 60 minut. Podpisni ključ je nastavitev okolja in se ne vključi v izvorno kodo.

Gesla hranimo kot bcrypt zgoščene vrednosti. Napačna e-pošta, napačno geslo in neaktiven uporabnik pri prijavi vrnejo enoten odgovor 401. API v odgovorih ne vrača gesla ali njegove zgoščene vrednosti.

Zaščitene končne točke bodo ob vsakem zahtevku preverile podpis in potek žetona ter trenutnega uporabnika, aktivnost in vlogo v bazi (US-02). Podatek o vlogi v žetonu ne nadomesti preverjanja trenutnih pravic. Prijavni obrazec in ravnanje odjemalca ob poteku prijave sledita v ločenih nalogah US-01.

### Consequences

* Prijava sledi pogojem sprejemljivosti in izvorni implementaciji.
* Strežniku ni treba hraniti prijavnih sej, mora pa varovati podpisni ključ.
* JWT je poverilnica: kdor ga pridobi, ga lahko uporablja do poteka, zato je pri gostovanju potreben HTTPS.
* Odjava z odstranitvijo žetona na odjemalcu ne prekliče njegove morebitne kopije. Takojšnji preklic posameznega žetona bi zahteval dodatni mehanizem.
* Preverjanje trenutnega uporabnika pri zaščitenih zahtevkih omogoča zavrnitev dostopa po deaktivaciji računa ali spremembi vloge.

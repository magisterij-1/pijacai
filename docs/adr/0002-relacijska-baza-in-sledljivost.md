# Relacijska podatkovna baza za sledljivost šarž

**Status:** Proposed

## Context and Problem Statement

Sistem mora za vsako šaržo pokazati porabljene serije surovin, za vsako serijo surovine pa vse šarže, v katerih je bila uporabljena. Zagon šarže posodobi zalogo in zabeleži porabo; te spremembe morajo biti dosledne tudi ob napaki. Potrebujemo model, ki podpira povezane zapise, referenčno celovitost in transakcije.

## Considered Options

* Relacijska baza PostgreSQL z ločenimi tabelami in tujimi ključi.
* Dokumentna baza z vgnezdenim seznamom porabe znotraj šarže.
* Relacijska baza, vendar brez ločenega zapisa porabe po serijah.

## Decision Outcome

Chosen option: "PostgreSQL z relacijskim modelom in povezovalno tabelo `batch_consumption`", because povezava med šaržo in serijo surovine je več-na-več, vsak zapis porabe pa mora hraniti tudi količino. Ločena povezovalna tabela omogoča poizvedbe sledljivosti v obe smeri, transakcije in omejitve tujih ključev pa pomagajo ohraniti skladnost podatkov.

### Consequences

* Good, because porabo je mogoče poizvedovati od šarže do serije in od serije do šarž.
* Good, because zagon šarže lahko v eni transakciji posodobi zalogo in zabeleži porabo.
* Good, because relacijske omejitve pomagajo preprečiti neveljavne povezave med zapisi.
* Bad, because podatkovni model in spremembe sheme zahtevajo migracije ter usklajeno načrtovanje.
* Bad, because PostgreSQL sam ne uveljavi vseh poslovnih pravil; zanje mora poskrbeti backend.

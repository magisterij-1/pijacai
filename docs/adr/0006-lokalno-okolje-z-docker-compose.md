# Docker Compose za lokalno razvojno okolje

**Status:** Proposed

## Context and Problem Statement

Frontend, backend in PostgreSQL imajo različna okolja izvajanja in nastavitve. Razvijalci morajo lokalno zagnati združljive različice teh komponent, ne da bi vsak ročno nameščal in povezoval vse odvisnosti. Rešitev je namenjena lokalnemu razvoju; produkcijsko gostovanje še ni določeno.

## Considered Options

* Vsako komponento namestiti in zagnati neposredno na računalniku razvijalca.
* Docker Compose uporabiti za lokalni zagon več komponent.
* Vsako komponento zagnati v ločenem orkestracijskem okolju.

## Decision Outcome

Chosen option: "Docker Compose za lokalni zagon frontenda, backenda in PostgreSQL", because en opis storitev in njihovih povezav zmanjša razlike med razvojnimi okolji, orkestracija pa ostane sorazmerna z obsegom MVP. Skrivnosti se podajo prek lokalne konfiguracije in se ne shranjujejo v repozitorij.

### Consequences

* Good, because razvijalci lahko okolje zaženejo z usklajenimi storitvami in nastavitvami.
* Good, because podatkovno bazo je mogoče zagnati brez lokalne namestitve PostgreSQL.
* Bad, because za razvoj je potreben Docker, kar porabi dodatne sistemske vire.
* Bad, because konfiguracija Compose še ne določa načina produkcijske namestitve.

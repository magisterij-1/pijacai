# Transakcijska poraba zaloge po načelu FIFO

**Status:** Proposed

## Context and Problem Statement

Ob zagonu šarže mora sistem preveriti razpoložljive količine, odpisati porabo iz zaloge in zabeležiti, iz katerih serij surovin je bila porabljena. Delna izvedba teh korakov bi povzročila neskladje med stanjem zalog in sledljivostjo. Če je surovina na voljo v več serijah, mora sistem določiti vrstni red porabe.

## Considered Options

* FIFO po času prejema (najprej najstarejša serija).
* FEFO po roku uporabe (najprej serija z najbližjim rokom).
* Ročna izbira serij s strani operaterja.

## Decision Outcome

Chosen option: "Preverjanje in odpis v eni transakciji, z izbiro serij po FIFO", because podatkovni model že beleži čas prejema, rokov uporabe pa še ne opredeljuje. Če zahtevane količine ni na voljo, se transakcija ne potrdi in šarža se ne zažene.

### Consequences

* Good, because odpis zaloge in zapis sledljivosti uspeta ali spodletita skupaj.
* Good, because starejša prejeta zaloga se praviloma porabi pred novejšo.
* Bad, because FIFO ne upošteva roka uporabe; ob uvedbi rokov bo treba ponovno oceniti FEFO.
* Bad, because sočasni zagoni lahko tekmujejo za isto zalogo, zato mora implementacija preprečiti dvojni odpis.
* Bad, because fizično stanje skladišča lahko zahteva inventuro ali popravek zaloge.

# Pripenjanje različice recepture proizvodnemu nalogu

**Status:** Proposed

## Context and Problem Statement

Receptura določa vrste in količine sestavin za izdelek. Ko se receptura spremeni, mora biti še vedno mogoče ugotoviti, po kateri različici je bil načrtovan že ustvarjen proizvodni nalog. Če bi nalog uporabljal vedno aktualno recepturo, bi spremembe lahko spremenile razlago zgodovinskih podatkov.

## Considered Options

* Obstoječo recepturo urejati na mestu.
* Ob spremembi ustvariti novo različico in jo pripeti nalogu.
* Ob nastanku naloga kopirati vse postavke recepture v nalog.

## Decision Outcome

Chosen option: "Različice receptur; proizvodni nalog se naveže na točno določeno različico", because s tem ohranimo zgodovinsko povezavo brez kopiranja vseh postavk recepture v vsak nalog. Po aktivaciji in uporabi različice v nalogu se njena vsebina ne spreminja.

### Consequences

* Good, because zgodovinski nalog ostane vezan na recepturo, po kateri je bil načrtovan.
* Good, because spremembe recepture so sledljive kot nove različice.
* Bad, because treba je določiti pravila za ustvarjanje, aktiviranje in arhiviranje različic.
* Bad, because aplikacija mora preprečiti ali obravnavati spreminjanje različice, ki je že uporabljena v nalogu.

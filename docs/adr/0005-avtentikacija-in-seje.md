# Seja na strežniku za prijavo uporabnikov

**Status:** Proposed

## Context and Problem Statement

Pijacai je predviden kot interni sistem, do katerega uporabniki dostopajo prek brskalnika. Za vsak zaščiten zahtevek mora backend preveriti prijavljenega uporabnika in njegovo vlogo, administrator pa mora imeti možnost preklicati dostop. Za MVP ni opredeljena potreba po dostopu tretjih aplikacij ali mobilnih odjemalcev.

## Considered Options

* Seja na strežniku, identificirana z naključnim ID-jem v varnem piškotku.
* JWT dostopni žetoni, ki jih preveri backend.
* Osnovna avtentikacija pri vsakem zahtevku.

## Decision Outcome

Chosen option: "Seja na strežniku z naključnim ID-jem v piškotku z atributi `HttpOnly`, `Secure` in `SameSite`", because sistem je namenjen brskalniškemu odjemalcu, za katerega je preklic seje pomemben, stateless žetoni ali podpora zunanjim odjemalcem pa niso zahteva MVP. Seja se po odjavi ali administratorskem preklicu odstrani; preverjanje vloge se opravi na backendu. Zahtevki, ki spreminjajo podatke, morajo biti zaščiteni pred CSRF.

### Consequences

* Good, because strežnik lahko sejo prekliče takoj, ne da bi čakal na potek žetona.
* Good, because `HttpOnly` preprečuje, da bi JavaScript neposredno prebral identifikator seje.
* Bad, because backend mora hraniti in čistiti seje.
* Bad, because seja v piškotku zahteva zaščito pred CSRF in pravilno konfiguracijo piškotkov glede na gostovanje.
* Bad, because dodajanje zunanjih odjemalcev bi lahko zahtevalo dodatni način avtentikacije.

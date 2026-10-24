# 01 – Zasnova rešitve

## Ime rešitve

**Pijacai** – spletni sistem za vodenje proizvodnih šarž, kontrole kakovosti in sledljivosti v polnilnici pijač.

## Namen in problem

Manjše polnilnice pijač (sokovi, vode, gazirane pijače) proizvodnjo pogosto vodijo z Excelovimi tabelami in papirnatimi delovnimi nalogi. Pri tem se pojavljajo štiri ponavljajoče se težave:

1. **Ni povezave med surovinami in šaržami.** Ko pride reklamacija ali dobavitelj sporoči napako v seriji surovine, je treba ročno iskati, katere šarže so bile prizadete.
2. **Sprostitev šarže ni formalno vezana na kakovost.** Šarža se lahko odpremi, čeprav meritve (npr. Brix, pH, CO₂, nivo polnjenja) niso vnesene pravočasno.
3. **Zaloge se ne ujemajo s porabo.** Poraba surovin in embalaže se ne beleži v realnem času, zato so zaloge pogosto netočne.
4. **Vodja nima pregleda nad izmetom in stroški.** Podatki so razpršeni, zato so analize počasne.

**Pijacai** te težave naslavlja z enim sistemom, kjer je vsaka šarža vezana na proizvodni nalog, recepturo, uporabljene serije surovin in rezultate kontrole kakovosti. Sistem uveljavlja pravila poteka (npr. šarže ni mogoče sprostiti brez ustreznih meritev) in omogoča sledljivost v obe smeri.

## Ciljni uporabniki

| Uporabnik | Situacija | Kaj potrebuje |
|---|---|---|
| Operater linije | Med izmeno zažene šaržo in vpisuje količine | Hiter, enostaven vnos; jasno, kaj je na vrsti |
| Kontrolor kakovosti | Po polnjenju meri parametre in odloča o šarži | Vnos meritev z mejnimi vrednostmi, sprostitev ali zavrnitev |
| Planer / vodja proizvodnje | Načrtuje proizvodnjo in spremlja uspešnost | Proizvodni nalogi, pregled šarž in izmeta |
| Skladiščnik | Sprejema surovine in embalažo | Vnos prejemov z dobaviteljevo serijo, pregled zalog |
| Administrator | Vzdržuje šifrante in uporabnike | Upravljanje izdelkov, receptur, linij in uporabnikov |

Ciljno okolje je mala do srednja polnilnica z eno ali dvema linijama. 

## Kratek opis delovanja

1. **Skladiščnik** vnese prejem surovin (npr. sadni koncentrat, sladkor, plastenke, zamaški) z dobaviteljevo številko serije in količino.
2. **Planer** ustvari proizvodni nalog za izbrani izdelek in količino. Nalog se naveže na veljavno recepturo.
3. **Operater** iz naloga zažene šaržo na izbrani liniji. Sistem v eni transakciji preveri, ali je dovolj surovin in embalaže, in samodejno odpiše porabo iz najstarejših serij (FIFO). Poraba se zapiše ob šarži.
4. Ko je polnjenje končano, operater vnese proizvedeno količino. Šarža preide v stanje **»Čaka na kontrolo«**.
5. **Kontrolor kakovosti** vnese meritve. Sistem primerja vrednosti z mejami za izdelek.
6. Kontrolor šaržo **sprosti** ali **zavrne**. Sprostitev brez popolnih in ustreznih meritev sistem zavrne.
7. **Sledljivost:** za poljubno šaržo sistem izpiše uporabljene serije surovin, za poljubno serijo surovine pa vse šarže, v katerih je bila uporabljena.

# 02 – Funkcionalnosti in obseg

## 1. Uporabniške vloge

| Vloga | Kaj lahko počne | Česa ne more |
|---|---|---|
| **Operater linije** | Vidi proizvodne naloge, zažene šaržo na liniji, vnese proizvedeno količino in izmet, šaržo preda v kontrolo | Ne more ustvarjati ali spreminjati nalogov, vnašati meritev kakovosti, sproščati šarž ali urejati zalog |
| **Kontrolor kakovosti** | Vnaša meritve kakovosti, sprosti ali zavrne šaržo, vidi šarže, ki čakajo na kontrolo, uporablja sledljivost | Ne more zagnati šarže, ustvarjati nalogov ali spreminjati zalog |
| **Planer / vodja proizvodnje** | Ustvarja in odpoveduje proizvodne naloge, vidi vse šarže, zaloge in poročila, uporablja sledljivost | Ne more spreminjati meritev kakovosti, sproščati šarž ali spreminjati vnosov operaterjev |
| **Skladiščnik** | Vnaša prejem surovin in embalaže, vidi zaloge | Ne vidi rezultatov kakovosti, ne ustvarja nalogov in ne zaganja šarž |
| **Administrator** | Upravlja uporabnike in njihove vloge | Razen upravljanja uporabnikov in njihovih vloge nič drugega |

## 2. Predvidene funkcionalnosti

Funkcionalnosti označene z **MVP** sodijo v prvo delujočo različico. Stolpec »Vrsta« pove, ali je funkcionalnost domensko specifična (D) ali splošna (S).

| ID | Funkcionalnost | Opis | Vloga | Vrsta | MVP |
|---|---|---|---|---|---|
| F1 | Prijava in vloge | Prijava z e-pošto in geslom, dostop do funkcij glede na vlogo | vse | S | **MVP** |
| F2 | Sprejem surovin in embalaže | Vnos prejema z dobaviteljevo serijo, količino in nabavno ceno; ustvari serijo surovine na zalogi | skladiščnik | D | **MVP** |
| F3 | Proizvodni nalog iz receptur | Planer izbere izdelek in količino; sistem poveže veljavno recepturo in izračuna potrebne količine | planer | D | **MVP** |
| F4 | Zagon šarže s preverjanjem zalog | Pred zagonom sistem preveri, ali je dovolj vsake sestavine; v eni transakciji odpiše porabo po načelu FIFO in jo zapiše ob šarži | operater | D | **MVP** |
| F5 | Vnos meritev kakovosti | Vnos parametrov (pH, CO₂, nivo polnjenja) z avtomatskim primerjanjem z mejami za izdelek | kontrolor | D | **MVP** |
| F6 | Sprostitev ali zavrnitev šarže | Sprostitev je mogoča le, če so vneseni vsi zahtevani parametri in ustrezajo mejam; zavrnitev zahteva razlog | kontrolor | D | **MVP** |
| F7 | Sledljivost šarže in surovine | Iz šarže izpiše uporabljene serije surovin; iz serije surovine izpiše vse prizadete šarže | planer, kontrolor | D | **MVP** |
| F8 | Upravljanje receptur in šifrantov | Urejanje izdelkov, receptur (z verzijami), surovin, linij in kakovostnih parametrov | kontrolor | D | |
| F9 | Zapis faz in zastojev | Beleženje faz šarže (priprava, polnjenje, pakiranje) in zastojev z razlogom | operater | D | |
| F10 | Pregled zalog z opozorili | Trenutne zaloge po surovinah, opozorilo, ko zaloga pade pod minimalno | skladiščnik, planer | D | |
| F11 | Nadzorna plošča KPI | Proizvedena količina, izmet in izkoristek po liniji in obdobju | planer | D | |
| F12 | Odprema šarž | Zapis odpreme sproščenih šarž; zavrnjene šarže ni mogoče odpremiti | planer | D | |
| F13 | Strošek šarže in enote | Izračun stroška surovin in embalaže na šaržo in na enoto iz nabavnih cen serij | planer | D | |

Skupaj je 13 funkcionalnosti, od tega je 7 označenih z MVP (F1–F7). Med njimi je 6 domensko specifičnih (F2–F7).

## 3. Kasnejše nadgradnje

1. **Odpoklic izdelka:** iz napačne serije surovine samodejno izpiši vse odpremljene šarže in kupce, ki so jih prejeli.
2. **OEE (Overall Equipment Effectiveness) linije:** izračun celotne učinkovitosti opreme (razpoložljivost, zmogljivost, kakovost).
3. **Sprotno osveževanje** nadzorne plošče prek WebSocket-ov (komunikacijski protokol, ki omogoča dvosmerno komunikacijo med odjemalcem (npr. brskalnikom) in strežnikom v realnem času.).
4. **Izvoz poročil** o šaržah in sledljivosti v PDF ali Excel.
5. **Avtomatski predlogi naročil** surovin, ko zaloga pade pod mejo.
6. **Revizijska sled (audit log):** zapis, kdo je kdaj spremenil pomemben podatek.
7. **Mobilna oblika vmesnika** za operaterje na liniji (PWA).

## 4. Out of scope (kaj projekt ne bo)

- Povezava s fizičnimi stroji, senzorji ali PLC-ji (Programmable Logic Controller); podatke vnašajo uporabniki.
- Računovodstvo, izdajanje računov in plačilni promet.
- Kadrovska evidenca, plače in razporejanje izmen.
- Načrtovanje dobavne verige in avtomatska komunikacija z dobavitelji.
- Podpora za več tovarn ali več podjetij hkrati (multi-tenancy - ena skupna infrastruktura služi več različnim strankam (tenantom), pri čemer so njihovi podatki in nastavitve medsebojno ločeni).
- Certificiranje skladnosti z zakonodajo (npr. HACCP - Hazard Analysis and Critical Control Points, sistem za zagotavljanje varnosti živil); sistem zgolj shranjuje podatke, ki so lahko podlaga za to.

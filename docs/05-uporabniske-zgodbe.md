# 05 – Uporabniške zgodbe

Dokument povezuje vseh 13 funkcionalnosti iz `02-funkcionalnosti-in-obseg.md` (F1–F13) z uporabniškimi zgodbami. Zgodbe US-01 do US-15 pokrivajo MVP (F1–F7), zgodbe US-16 do US-23 pa funkcionalnosti po MVP (F8–F13). Uporabljene so vloge, entitete in stanja iz `03-podatkovni-model.md` (npr. `batch.status`: `in_production`, `awaiting_qc`, `released`, `rejected`) ter poti API-ja iz `04-arhitektura-in-tehnoloski-sklad.md`.

## 1. Pregled zgodb

| Oznaka | Naslov | Funkcionalnost | Vloga |
|---|---|---|---|
| US-01 | Prijava z e-pošto in geslom | F1 | vse vloge |
| US-02 | Dostop do funkcij glede na vlogo | F1 | vse vloge |
| US-03 | Upravljanje uporabnikov | F1 | administrator |
| US-04 | Vnos prejema surovine ali embalaže | F2 | skladiščnik |
| US-05 | Pregled zalog po serijah | F2 | skladiščnik |
| US-06 | Ustvarjanje proizvodnega naloga iz receptur | F3 | planer |
| US-07 | Odpoved proizvodnega naloga | F3 | planer |
| US-08 | Zagon šarže s preverjanjem zalog | F4 | operater linije |
| US-09 | FIFO odpis porabe surovin ob zagonu šarže | F4 | operater linije |
| US-10 | Zaključek polnjenja in predaja v kontrolo | F4 | operater linije |
| US-11 | Vnos meritev kakovosti | F5 | kontrolor kakovosti |
| US-12 | Sprostitev šarže | F6 | kontrolor kakovosti |
| US-13 | Zavrnitev šarže z razlogom | F6 | kontrolor kakovosti |
| US-14 | Sledljivost šarže nazaj do serij surovin | F7 | planer, kontrolor kakovosti |
| US-15 | Sledljivost serije surovine naprej do šarž | F7 | planer, kontrolor kakovosti |
| US-16 | Nova verzija receptur | F8 | kontrolor kakovosti |
| US-17 | Vzdrževanje šifrantov in kakovostnih parametrov | F8 | kontrolor kakovosti |
| US-18 | Zapis faz šarže | F9 | operater linije |
| US-19 | Zapis zastoja z razlogom | F9 | operater linije |
| US-20 | Pregled zalog z opozorili o minimalni zalogi | F10 | skladiščnik, planer |
| US-21 | Nadzorna plošča KPI | F11 | planer |
| US-22 | Zapis odpreme sproščene šarže | F12 | planer |
| US-23 | Strošek šarže in enote | F13 | planer |


| Funkcionalnost | Zgodbe | MVP |
|---|---|---|
| F1 Prijava in vloge | US-01, US-02, US-03 | da |
| F2 Sprejem surovin in embalaže | US-04, US-05 | da |
| F3 Proizvodni nalog iz receptur | US-06, US-07 | da |
| F4 Zagon šarže s preverjanjem zalog | US-08, US-09, US-10 | da |
| F5 Vnos meritev kakovosti | US-11 | da |
| F6 Sprostitev ali zavrnitev šarže | US-12, US-13 | da |
| F7 Sledljivost šarže in surovine | US-14, US-15 | da |
| F8 Upravljanje receptur in šifrantov | US-16, US-17 | ne |
| F9 Zapis faz in zastojev | US-18, US-19 | ne |
| F10 Pregled zalog z opozorili | US-20 | ne |
| F11 Nadzorna plošča KPI | US-21 | ne |
| F12 Odprema šarž | US-22 | ne |
| F13 Strošek šarže in enote | US-23 | ne |

**Opomba:** Funkcionalnosti F9 (faze in zastoji) in F12 (odprema) v `03-podatkovni-model.md` še nimata svojih tabel; za njuno izvedbo v prihodnje model razširimo (tabele za faze, zastoje in odpreme šarž).

---

## 2. Uporabniške zgodbe

### US-01 – Prijava z e-pošto in geslom

- **Povezana funkcionalnost:** F1 – Prijava in vloge
- **Uporabniška vloga:** vse vloge (operater, kontrolor, planer, skladiščnik, administrator)
- **Zgodba:** Kot uporabnik sistema želim, da se prijavim z e-pošto in geslom, da lahko dostopam do funkcij, ki jih potrebujem pri delu.

**Acceptance criteria:**

1. Ob vnosu veljavne e-pošte in pravilnega gesla `POST /auth/login` vrne JWT žeton z identifikatorjem uporabnika in vlogo, uporabnik pa je preusmerjen na začetno stran svoje vloge.
2. Ob napačni e-pošti ali napačnem geslu sistem vrne odgovor 401 in prikaže sporočilo »Napačna e-pošta ali geslo.« Sporočilo ne razkrije, katero od obeh polj je napačno.
3. Uporabnik z `active = false` se ne more prijaviti, tudi če sta e-pošta in geslo pravilna.
4. Žeton poteče po 60 minutah; po poteku je uporabnik ob naslednji akciji preusmerjen na prijavo.
5. Geslo se v bazi hrani samo kot zgoščena vrednost (bcrypt ali argon2), v odgovorih API-ja ga ni.

---

### US-02 – Dostop do funkcij glede na vlogo

- **Povezana funkcionalnost:** F1 – Prijava in vloge
- **Uporabniška vloga:** vse vloge
- **Zgodba:** Kot uporabnik želim videti in uporabljati samo funkcije svoje vloge, da ne naredim napake v procesu, ki ni moja odgovornost.

**Acceptance criteria:**

1. Meni v vmesniku prikazuje samo strani, ki jih dovoljuje vloga (npr. skladiščnik vidi »Prejem surovin« in »Zaloge«, ne vidi pa »Šarže za kontrolo«).
2. Če uporabnik z vpisom naslova ročno odpre stran, ki je njegova vloga ne dovoljuje, vidi stran »Nimate dostopa« (403).
3. Backend zavrne klic končne točke z napačno vlogo z odgovorom 403, tudi če je zahtevek poslan mimo vmesnika (npr. operater pokliče `POST /batches/{id}/release`).
4. Zahtevek brez veljavnega žetona ali s poteklim žetonom backend zavrne z odgovorom 401.
5. Za vsako končno točko iz tabele v `04-arhitektura-in-tehnoloski-sklad.md` obstaja avtomatski test, ki preveri, da jo vloga, ki ni navedena, ne more poklicati.

---

### US-03 – Upravljanje uporabnikov

- **Povezana funkcionalnost:** F1 – Prijava in vloge
- **Uporabniška vloga:** administrator
- **Zgodba:** Kot administrator želim ustvariti uporabnika z dodeljeno vlogo in ga po potrebi deaktivirati, da imajo dostop samo zaposleni, ki ga potrebujejo.

**Acceptance criteria:**

1. Administrator lahko ustvari uporabnika z imenom, e-pošto, začetnim geslom (najmanj 8 znakov) in eno od vlog: `operator`, `quality`, `planner`, `warehouse`, `admin`.
2. Če e-pošta že obstaja, sistem uporabnika ne ustvari in prikaže sporočilo »Uporabnik s to e-pošto že obstaja.«
3. Administrator lahko uporabnika deaktivira (`active = false`); deaktiviran uporabnik se ne more prijaviti, njegovi pretekli zapisi (šarže, meritve) ostanejo nespremenjeni.
4. Uporabniki z drugimi vlogami ne morejo odpreti seznama uporabnikov ali ustvarjati računov (403).
5. Samostojne registracije ni: v aplikaciji in API-ju ne obstaja stran ali končna točka za registracijo.

---

### US-04 – Vnos prejema surovine ali embalaže

- **Povezana funkcionalnost:** F2 – Sprejem surovin in embalaže
- **Uporabniška vloga:** skladiščnik
- **Zgodba:** Kot skladiščnik želim vnesti prejem surovine z dobaviteljevo serijo, količino in nabavno ceno, da je vsaka serija na zalogi evidentirana in sledljiva.

**Acceptance criteria:**

1. Obrazec zahteva surovino (izbor iz šifranta), dobavitelja, dobaviteljevo številko serije, količino in nabavno ceno na enoto; brez vseh polj prejema ni mogoče shraniti in ob vsakem manjkajočem polju je prikazano sporočilo o napaki.
2. Količina mora biti večja od 0, nabavna cena pa ne sme biti negativna; sicer sistem prejem zavrne s sporočilom ob polju.
3. Ob uspešnem shranjevanju sistem ustvari zapis `material_lot` z `remaining_qty` enako `received_qty`, `received_at` s trenutnim časom in `received_by` s prijavljenim skladiščnikom.
4. Če za isto surovino in istega dobavitelja že obstaja serija z isto dobaviteljevo številko serije, sistem prejem zavrne (409) in prikaže sporočilo »Ta serija je že vnesena.«
5. Nov prejem se takoj pojavi v seznamu serij (US-05) in poveča skupno zalogo surovine.

---

### US-05 – Pregled zalog po serijah

- **Povezana funkcionalnost:** F2 – Sprejem surovin in embalaže
- **Uporabniška vloga:** skladiščnik
- **Zgodba:** Kot skladiščnik želim videti trenutne zaloge po surovinah in serijah, da vem, kaj je v skladišču in katera serija bo na vrsti za porabo.

**Acceptance criteria:**

1. Seznam prikazuje za vsako serijo surovino, dobavitelja, dobaviteljevo številko serije, prejeto količino, preostalo količino in datum prejema.
2. Serije so privzeto razvrščene po datumu prejema od najstarejše do najnovejše (vrstni red FIFO).
3. Seznam je mogoče filtrirati po surovini; ob filtru je prikazana vsota preostalih količin vseh serij te surovine.
4. Serije s preostalo količino 0 so privzeto skrite, prikaže jih stikalo »Pokaži porabljene«.
5. Uporabnik z vlogo operater ali kontrolor seznama zalog ne more odpreti (403).

---

### US-06 – Ustvarjanje proizvodnega naloga iz receptur

- **Povezana funkcionalnost:** F3 – Proizvodni nalog iz receptur
- **Uporabniška vloga:** planer / vodja proizvodnje
- **Zgodba:** Kot planer želim ustvariti proizvodni nalog za izbrani izdelek in količino ter videti potrebne količine surovin, da vem, ali lahko proizvodnjo pravočasno začnemo.

**Acceptance criteria:**

1. Obrazec zahteva izdelek, načrtovano količino (celo število, večje od 0) in načrtovan datum, ki ni v preteklosti.
2. Ob shranitvi sistem na nalog pripne trenutno aktivno verzijo receptur izdelka (`production_order.recipe_id`); poznejša sprememba receptur obstoječega naloga ne spremeni.
3. Pred potrditvijo sistem prikaže tabelo potrebnih količin surovin, izračunanih po formuli `qty × planned_qty / output_qty` za vsako postavko receptur.
4. Izdelka brez aktivne receptur ni mogoče izbrati za nalog; sistem prikaže sporočilo »Za ta izdelek ni aktivne receptur.«
5. Novi nalog dobi status `planned` in se pojavi na seznamu nalogov operaterja.

---

### US-07 – Odpoved proizvodnega naloga

- **Povezana funkcionalnost:** F3 – Proizvodni nalog iz receptur
- **Uporabniška vloga:** planer / vodja proizvodnje
- **Zgodba:** Kot planer želim odpovedati nalog, ki ga ne bomo izvedli, da operaterji ne zaženejo šarže po nepotrebnem.

**Acceptance criteria:**

1. Planer lahko odpove samo nalog v stanju `planned`; sistem pred odpovedjo zahteva potrditev v pogovornem oknu.
2. Nalog, za katerega je že bila zagnana vsaj ena šarža (stanje `in_progress`), sistem ne odpove in prikaže sporočilo »Naloga ni mogoče odpovedati, ker je šarža že zagnana.«
3. Po uspešni odpovedi ima nalog status `cancelled` in ni več na seznamu nalogov operaterja.
4. Operater za odpovedan nalog ne more zagnati šarže (`POST /orders/{id}/batches` vrne 409).
5. Odpovedan nalog ostane viden v pregledu nalogov planerja s statusom `cancelled`.

---

### US-08 – Zagon šarže s preverjanjem zalog

- **Povezana funkcionalnost:** F4 – Zagon šarže s preverjanjem zalog
- **Uporabniška vloga:** operater linije
- **Zgodba:** Kot operater želim, da sistem pred zagonom šarže preveri, ali je dovolj vseh surovin in embalaže, da proizvodnje ne prekinemo sredi polnjenja.

**Acceptance criteria:**

1. Operater izbere nalog v stanju `planned` ali `in_progress`, aktivno linijo in količino za šaržo; sistem pred zagonom prikaže za vsako sestavino potrebno količino, razpoložljivo zalogo in stanje (OK ali PREMALO).
2. Če katere koli sestavine ni dovolj, sistem šarže ne zažene (409), izpiše manjkajočo surovino in količino, ki manjka, ter ne ustvari nobenega zapisa in ne spremeni nobene zaloge.
3. Če je vseh sestavin dovolj, sistem ustvari šaržo s statusom `in_production`, enolično kodo v obliki `LLLL-MM-DD-L<linija>-<zap. št.>` (npr. `2026-10-20-L1-01`), `started_at` in `operator_id`; status naloga se spremeni v `in_progress`.
4. Vsi koraki zagona (ustvarjanje šarže, odpis porabe, zmanjšanje zaloge) potekajo v eni transakciji; če katera koli operacija odpove, ni shranjena nobena sprememba.
5. Šarže ni mogoče zagnati na odpovedanem nalogu ali na deaktivirani liniji (`active = false`).

---

### US-09 – FIFO odpis porabe surovin ob zagonu šarže

- **Povezana funkcionalnost:** F4 – Zagon šarže s preverjanjem zalog
- **Uporabniška vloga:** operater linije
- **Zgodba:** Kot operater želim, da se poraba samodejno odpiše iz najstarejših serij, da so zaloge točne, surovine pa sveže.

**Acceptance criteria:**

1. Za vsako sestavino sistem porablja serije po naraščajočem `received_at`, pri čemer upošteva samo serije z `remaining_qty > 0`.
2. Če ena serija ne zadošča, sistem porabo razdeli na več serij in za vsako uporabljeno serijo ustvari svoj zapis `batch_consumption`.
3. Vsota `batch_consumption.qty` po surovini je enaka potrebni količini za šaržo, `remaining_qty` pa se za vsako serijo zmanjša natanko za odpisano količino in nikoli ne postane negativen.
4. Če dva operaterja istočasno zaženeta šaržo, ki bi porabila isto zalogo, se obe ne moreta uspešno izvesti: druga dobi odgovor 409, če zaloge ne zadoščata (preverjeno z avtomatskim testom s sočasnima zahtevkoma).
5. Odpisane količine in serije so vidne na podrobnostih šarže.

---

### US-10 – Zaključek polnjenja in predaja v kontrolo

- **Povezana funkcionalnost:** F4 – Zagon šarže s preverjanjem zalog
- **Uporabniška vloga:** operater linije
- **Zgodba:** Kot operater želim ob koncu polnjenja vnesti proizvedeno količino in izmet ter šaržo predati v kontrolo, da kontrolor lahko začne meritve.

**Acceptance criteria:**

1. Operater lahko zaključi samo šaržo v stanju `in_production`; obvezna sta `produced_qty` in `rejected_qty` (celi števili, ≥ 0).
2. Izmet ne sme presegati proizvedene količine; sicer sistem zavrne vnos s sporočilom ob polju.
3. Ob uspešnem zaključku se šarža premakne v stanje `awaiting_qc`, nastavi se `finished_at`, šarža pa se pokaže na seznamu »Šarže za kontrolo«.
4. Po predaji v kontrolo operater količin ne more več spreminjati (`POST /batches/{id}/finish` na šarži v drugem stanju vrne 409).
5. Operater ne more zaključiti šarže, ki jo je zagnal drug operater; API vrne 403.

---

### US-11 – Vnos meritev kakovosti

- **Povezana funkcionalnost:** F5 – Vnos meritev kakovosti
- **Uporabniška vloga:** kontrolor kakovosti
- **Zgodba:** Kot kontrolor želim vnesti izmerjene vrednosti parametrov za šaržo in takoj videti, ali ustrezajo mejam, da hitro ocenim kakovost.

**Acceptance criteria:**

1. Kontrolor vidi seznam šarž v stanju `awaiting_qc`; ob izbiri šarže obrazec prikaže vse parametre (`quality_parameter`) njenega izdelka z enoto ter mejama `min_value` in `max_value`.
2. Po vnosu številske vrednosti sistem izračuna `passed` (vrednost je znotraj mej, vključno z mejama) in ob parametru prikaže »ustreza« ali »ne ustreza«.
3. Prazna ali nenumerična vrednost se ne shrani; sistem prikaže sporočilo ob polju.
4. Vsaka shranjena meritev vsebuje `batch_id`, `parameter_id`, `value`, `passed`, `checked_by` in `checked_at`; pri ponovnem vnosu istega parametra se ustvari nov zapis, za presojo velja zadnji.
5. Meritev je mogoče vnesti samo za šarže v stanju `awaiting_qc`; za druge šarže sistem vrne 409.

---

### US-12 – Sprostitev šarže

- **Povezana funkcionalnost:** F6 – Sprostitev ali zavrnitev šarže
- **Uporabniška vloga:** kontrolor kakovosti
- **Zgodba:** Kot kontrolor želim sprostiti šaržo, ki je prestala kontrolo, da je formalno potrjeno, da je primerna za odpremo.

**Acceptance criteria:**

1. Gumb »Sprosti šaržo« je aktiven samo, če so za vse zahtevane parametre izdelka vnesene meritve in so zadnje meritve vseh parametrov `passed = true`.
2. Če kateri parameter nima meritve ali je izven mej, `POST /batches/{id}/release` vrne 422 s seznamom manjkajočih in neustreznih parametrov, šarža pa ostane v stanju `awaiting_qc`.
3. Ob uspešni sprostitvi se stanje šarže spremeni v `released`, zapišeta se `decided_by` in `decided_at`.
4. Sprostitev je mogoča samo iz stanja `awaiting_qc`; sproščene ali zavrnjene šarže ni mogoče ponovno sprostiti (409).
5. Sprostitev lahko izvede samo vloga `quality`; planer ali operater dobita 403.

---

### US-13 – Zavrnitev šarže z razlogom

- **Povezana funkcionalnost:** F6 – Sprostitev ali zavrnitev šarže
- **Uporabniška vloga:** kontrolor kakovosti
- **Zgodba:** Kot kontrolor želim zavrniti neustrezno šaržo in zapisati razlog, da je odločitev razumljiva in sledljiva.

**Acceptance criteria:**

1. Zavrnitev je mogoča za šaržo v stanju `awaiting_qc`, ne glede na to, ali so vse meritve že vnesene.
2. Razlog je obvezen in mora imeti najmanj 10 znakov; sicer `POST /batches/{id}/reject` vrne 422 in šarža ostane nespremenjena.
3. Ob uspešni zavrnitvi se stanje spremeni v `rejected`, zapišejo se `decision_note`, `decided_by` in `decided_at`.
4. Zavrnjene šarže ni več mogoče sprostiti; poskus vrne 409.
5. Razlog zavrnitve je viden na podrobnostih šarže vsem vlogam z dostopom do šarž.

---

### US-14 – Sledljivost šarže nazaj do serij surovin

- **Povezana funkcionalnost:** F7 – Sledljivost šarže in surovine
- **Uporabniška vloga:** planer, kontrolor kakovosti
- **Zgodba:** Kot kontrolor ali planer želim za izbrano šaržo videti, katere serije surovin so bile uporabljene, da lahko ob reklamaciji hitro ugotovim izvor.

**Acceptance criteria:**

1. Ob vnosu kode šarže `GET /traceability/batch/{id}` vrne vse zapise `batch_consumption` te šarže; tabela prikazuje surovino, dobavitelja, dobaviteljevo številko serije in porabljeno količino.
2. Če je bila ista surovina porabljena iz več serij, je vsaka serija v svoji vrstici, vsota po surovini pa je enaka porabi, odpisani ob zagonu.
3. Za šaržo, ki ne obstaja, sistem prikaže »Šarža ni najdena.«
4. Ob rezultatu je prikazan izdelek in status šarže (`in_production`, `awaiting_qc`, `released`, `rejected`).
5. Operater, skladiščnik in administrator sledljivosti ne morejo odpreti (403).

---

### US-15 – Sledljivost serije surovine naprej do šarž

- **Povezana funkcionalnost:** F7 – Sledljivost šarže in surovine
- **Uporabniška vloga:** planer, kontrolor kakovosti
- **Zgodba:** Kot planer ali kontrolor želim za izbrano serijo surovine videti vse šarže, v katerih je bila uporabljena, da ob napaki dobavitelja takoj vem, katere šarže so prizadete.

**Acceptance criteria:**

1. Uporabnik izbere surovino in vnese dobaviteljevo številko serije; `GET /traceability/lot/{id}` vrne vse šarže, v katerih je bila uporabljena.
2. Za vsako šaržo so prikazani koda šarže, izdelek, datum zagona, status in količina, porabljena iz te serije; vrstni red je od najstarejše do najnovejše šarže.
3. Če serija še ni bila porabljena, sistem prikaže »Ta serija še ni bila uporabljena v nobeni šarži.«
4. Če serija ne obstaja, sistem prikaže »Serija ni najdena.«
5. Rezultat za isto serijo vsebuje natanko iste šarže, kot jih vrne iskanje po šaržah (US-14) za vsako od teh šarž (preverjeno z avtomatskim testom).

---

## 4. Zgodbe za funkcionalnosti po MVP (F8–F13)

### US-16 – Nova verzija receptur

- **Povezana funkcionalnost:** F8 – Upravljanje receptur in šifrantov
- **Uporabniška vloga:** kontrolor kakovosti
- **Zgodba:** Kot kontrolor želim ustvariti novo verzijo receptur izdelka, da lahko izboljšam recepturo, ne da bi spremenil pomen že izdelanih šarž.

**Acceptance criteria:**

1. Nova verzija se ustvari s kopiranjem postavk trenutne verzije; kontrolor lahko postavke doda, odstrani ali jim spremeni količino (`qty` > 0) ter nastavi `output_qty` (> 0).
2. Receptura brez ene same postavke se ne shrani; sistem prikaže sporočilo »Receptura mora vsebovati vsaj eno surovino.«
3. Ob aktivaciji nove verzije se prejšnja verzija samodejno deaktivira, tako da ima izdelek vedno največ eno aktivno verzijo (`active = true`).
4. Verzijska številka se poveča za 1 (kombinacija `product_id` + `version` je enolična); obstoječe verzije ni mogoče spreminjati, če je navezana na kakšen nalog.
5. Nalogi in šarže, ustvarjeni z eno od starejših verzij, ohranijo svojo verzijo (`production_order.recipe_id` se ne spremeni).

---

### US-17 – Vzdrževanje šifrantov in kakovostnih parametrov

- **Povezana funkcionalnost:** F8 – Upravljanje receptur in šifrantov
- **Uporabniška vloga:** kontrolor kakovosti
- **Zgodba:** Kot kontrolor želim urejati izdelke, surovine, linije in kakovostne parametre z mejami, da sistem uporablja aktualne podatke.

**Acceptance criteria:**

1. Kontrolor lahko ustvari in uredi izdelek (ime, SKU, enota), surovino (ime, tip `ingredient`/`packaging`, enota, `min_stock`), linijo (ime) in kakovostni parameter izdelka (ime, enota, `min_value`, `max_value`).
2. Sistem zavrne parameter, pri katerem je `min_value` večja od `max_value`, ter izdelek z že obstoječim SKU, in ob polju prikaže sporočilo o napaki.
3. Surovine, linije ali izdelka, ki ga uporabljata receptura ali zgodovinski zapis (serija, šarža), ni mogoče izbrisati (409); lahko ga deaktiviramo, nato ni več na voljo za izbiro pri novih zapisih.
4. Sprememba mej parametra velja samo za nove meritve; `passed` obstoječih zapisov `quality_check` se ne spremeni.
5. Planer, operater in skladiščnik šifrantov ne morejo urejati (403).

---

### US-18 – Zapis faz šarže

- **Povezana funkcionalnost:** F9 – Zapis faz in zastojev
- **Uporabniška vloga:** operater linije
- **Zgodba:** Kot operater želim beležiti faze šarže (priprava, polnjenje, pakiranje), da je razvidno, koliko časa je trajala posamezna faza.

**Acceptance criteria:**

1. Operater lahko za šaržo v stanju `in_production` začne fazo z izborom ene od treh faz: priprava, polnjenje, pakiranje; sistem zapiše čas začetka.
2. Hkrati je lahko aktivna samo ena faza; začetek nove faze samodejno zaključi prejšnjo z istim časom.
3. Ob ročnem zaključku faze sistem zapiše čas konca in izračuna trajanje v minutah; čas konca ne sme biti pred časom začetka.
4. Na podrobnostih šarže so faze prikazane v časovnem zaporedju s trajanjem.
5. Faz ni mogoče dodajati ali spreminjati na šaržah v stanju `awaiting_qc`, `released` ali `rejected` (409).

---

### US-19 – Zapis zastoja z razlogom

- **Povezana funkcionalnost:** F9 – Zapis faz in zastojev
- **Uporabniška vloga:** operater linije
- **Zgodba:** Kot operater želim zabeležiti zastoj z razlogom, da vodja kasneje ve, zakaj je proizvodnja stala.

**Acceptance criteria:**

1. Zastoj se zapiše za šaržo v stanju `in_production` z začetkom, koncem (ali je odprt, dokler ga operater ne zaključi) in razlogom iz seznama: okvara stroja, čakanje na material, čiščenje, drugo.
2. Pri razlogu »drugo« je obvezen opis z vsaj 5 znaki; za ostale razloge opis ni obvezen.
3. Trajanje zastoja se izračuna samodejno v minutah; čas konca ne sme biti pred časom začetka.
4. Na šarži je naenkrat lahko odprt največ en zastoj; poskus odprtja drugega vrne sporočilo »Zastoj je že odprt.«
5. Skupno trajanje zastojev je prikazano na podrobnostih šarže, zastoji pa so našteti s časom in razlogom.

---

### US-20 – Pregled zalog z opozorili o minimalni zalogi

- **Povezana funkcionalnost:** F10 – Pregled zalog z opozorili
- **Uporabniška vloga:** skladiščnik, planer
- **Zgodba:** Kot skladiščnik ali planer želim videti, katere surovine so pod minimalno zalogo, da pravočasno naročimo novo.

**Acceptance criteria:**

1. Pregled prikazuje za vsako surovino skupno zalogo (vsota `remaining_qty` vseh serij), enoto in mejo `min_stock`.
2. Surovine, pri katerih je skupna zaloga manjša od `min_stock`, so vizualno označene, na vrhu strani pa je prikazano število takih surovin.
3. Seznam je mogoče razvrstiti in filtrirati po tipu (`ingredient` / `packaging`) ter filtrirati samo surovine pod mejo.
4. Surovina brez serij je prikazana z zalogo 0 in opozorilom, če je `min_stock` večji od 0.
5. Po vnosu prejema (US-04) ali zagonu šarže (US-08) pregled ob naslednjem nalaganju prikazuje posodobljene vrednosti.

---

### US-21 – Nadzorna plošča KPI

- **Povezana funkcionalnost:** F11 – Nadzorna plošča KPI
- **Uporabniška vloga:** planer
- **Zgodba:** Kot planer želim videti proizvedeno količino, izmet in izkoristek po liniji in obdobju, da hitro ocenim uspešnost proizvodnje.

**Acceptance criteria:**

1. Planer izbere obdobje (od–do) in linijo (ena ali vse); plošča prikaže vsoto proizvedene količine, vsoto izmeta in odstotek izmeta (`rejected_qty / produced_qty`).
2. Izkoristek je prikazan kot `(produced_qty − rejected_qty) / planned_qty` v odstotkih; v izračun so vključene samo šarže, ki so že zaključile polnjenje (`awaiting_qc`, `released`, `rejected`).
3. Prikazan je graf (Recharts) proizvedene količine in izmeta po dnevih izbranega obdobja.
4. Če v izbranem obdobju ni šarž, sistem prikaže »Za izbrano obdobje ni podatkov.«
5. Vsote na plošči se ujemajo z vsotami v seznamu šarž za isto obdobje in linijo (preverjeno z avtomatskim testom).

---

### US-22 – Zapis odpreme sproščene šarže

- **Povezana funkcionalnost:** F12 – Odprema šarž
- **Uporabniška vloga:** planer
- **Zgodba:** Kot planer želim zapisati odpremo sproščene šarže, da imam evidenco, kam in kdaj je šarža odšla.

**Acceptance criteria:**

1. Odpremo je mogoče zapisati samo za šaržo v stanju `released`; šarže v stanjih `in_production`, `awaiting_qc` ali `rejected` sistem zavrne (409) s sporočilom »Šarža ni sproščena.«
2. Obrazec zahteva prejemnika (kupca), količino (celo število, večje od 0) in datum odpreme, ki ni v prihodnosti.
3. Skupna odpremljena količina šarže ne sme presegati `produced_qty − rejected_qty`; sicer sistem zavrne vnos in prikaže, koliko je še na voljo.
4. Za isto šaržo je mogoče zapisati več odprem; na podrobnostih šarže so prikazane vse odpreme in preostala neodpremljena količina.
5. Odpremo lahko zapiše samo planer (403 za druge vloge).

---

### US-23 – Strošek šarže in enote

- **Povezana funkcionalnost:** F13 – Strošek šarže in enote
- **Uporabniška vloga:** planer
- **Zgodba:** Kot planer želim videti strošek surovin in embalaže za šaržo in na enoto, da ocenim stroškovno učinkovitost proizvodnje.

**Acceptance criteria:**

1. Strošek šarže je vsota `batch_consumption.qty × material_lot.unit_cost` po vseh zapisih porabe šarže in je prikazan v evrih na dve decimalki.
2. Strošek na enoto je strošek šarže, deljen z `produced_qty − rejected_qty`; če je ta količina 0, sistem prikaže »Strošek na enoto ni izračunljiv.«
3. Prikazana je razčlenitev stroška po surovinah (surovina, serija, količina, nabavna cena, strošek).
4. Strošek se računa iz cen serij, uporabljenih ob zagonu šarže (FIFO), zato poznejši prejemi z drugačno ceno stroška obstoječe šarže ne spremenijo.
5. Strošek je prikazan tudi na seznamu šarž, planer pa ga lahko razvrsti po stroških na enoto.

# 07 – Pregled projekta

## 1. Implementirane funkcionalnosti (MVP)

| ID | Funkcionalnost | Stanje | Opomba |
|---|---|---|---|
| F1 | Prijava in vloge | Implementirano | JWT, dostop glede na vlogo |
| F2 | Sprejem surovin in embalaže | Implementirano | Ustvari serijo na zalogi |
| F3 | Proizvodni nalog iz receptur | Implementirano | Povezava z aktivno recepturo, izračun količin |
| F4 | Zagon šarže s preverjanjem zalog | Implementirano | Transakcijska FIFO poraba |
| F5 | Vnos meritev kakovosti | Implementirano | Primerjava z mejami izdelka |
| F6 | Sprostitev ali zavrnitev šarže | Implementirano | Zavrnitev zahteva razlog |
| F7 | Sledljivost | Implementirano | Naprej in nazaj |

Aplikacijo sem lokalno zagnal z `docker compose up --build` in preizkusil
osnovni potek: prejem surovin → proizvodni nalog → zagon šarže →
zaključek polnjenja → meritve → sprostitev/zavrnitev → sledljivost.

## 2. Ujemanje z uporabniškimi zgodbami

| Zgodba | Funkcionalnost | Zadošča? | Komentar |
|---|---|---|---|
| US-01 Prijava z e-pošto in geslom | F1 | Da | ... |
| US-02 Dostop glede na vlogo | F1 | Da | ... |
| US-03 Upravljanje uporabnikov | F1 | Da | Stran Uporabniki (administrator) |
| US-04 Vnos prejema surovine/embalaže | F2 | Da | ... |
| US-05 Pregled zalog po serijah | F2 | Da | ... |


# Ziemski kalendarz — czego ten świat nie ma

Czas liczy się dniami. Doby i lata istnieją; tygodnie, miesiące oraz nazwy dni
i miesięcy nie. Ebner odwołuje się do czasu przez zdarzenia: „wczoraj", „kiedy
przyleciałem", „trzy dni temu".

Reguła stoi już w dwóch miejscach — `diary_pl.md` punkt 14 i lista kontrolna w
`check_pl.md`. Oba prompty przepuściły ją czterokrotnie: zdanie „Odpisałem, że
zapłacę w przyszłym tygodniu." zamyka wpisy 3, 4, 5 i 16, słowo w słowo. Dlatego
krok redakcji dostaje tę poprawkę także z automatu, a nie tylko wtedy, gdy
kontrola ją zauważy.

Plik jest tutaj, a nie w kodzie, bo to słownictwo świata: zmiana reguły ma być
edycją tekstu, nie Pythona. Wykrywanie jest mechaniczne, ale naprawa nie —
podmiany dokonuje krok redakcji, który widzi zdanie i wie, co w nie wstawić.
Strażnik celowo tego nie blokuje: odrzucony wpis kosztuje całą, już opłaconą
prozę, a tu chodzi o jedno słowo.

## Zakazane słowa

Wyrażenia regularne, dopasowywane w granicach słowa (`\b`), bez względu na
wielkość liter. Jedna linia to jeden wzorzec; puste linie i `#` są pomijane.

```regex
tydzie[nń]
tygodni\w*
miesi[aąeę]c\w*
weekend\w*
poniedzia[lł]\w*
wtorek|wtorku
[sś]rod[aęy]
czwart(?:ek|ku|kiem|ki)
pi[aą]t(?:ek|ku|kiem)
sobot[aęy]
niedziel\w*
stycz(?:e[nń]|nia)
lut(?:y|ego)
marzec|marca
kwiet(?:nia|niu)
czerw(?:iec|ca)
lip(?:iec|ca)
sierp(?:ie[nń]|nia)
wrze(?:sie[nń]|śnia)
pa[zź]dzierni(?:k|ka)
listopad(?:a)?
grud(?:zie[nń]|nia)
```

Nie ma tu `maja` ani `lut` bez końcówki: pierwsze myli się z „mają", drugie z
lutowaniem, którym Ebner zarabia. Rok, doba, dzień i pora dnia są dozwolone.

## Poprawka

Jedna linia, doklejana do listy poprawek dla kroku redakcji. `{slowo}` zostaje
zastąpione znalezionym słowem.

```text
zamień „{slowo}" na określenie w dniach albo przez zdarzenie („za kilka dni", „kiedy wrócę") — ten świat nie ma tygodni, miesięcy ani nazw dni
```

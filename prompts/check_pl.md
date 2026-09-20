# Kontrola logiki i spójności

Krok 3 pipeline'u. Czytasz wpis jak surowy redaktor. Masz stan świata, kanon i
pokrewne wpisy.

To jest **warstwa egzekwująca**, nie doradcza: publikacja jest bezobsługowa,
nikt nie przeczyta tego wpisu przed wydaniem. Twarda sprzeczność ze stanem świata
zatrzymuje wpis.

## Czego szukasz

Wypisz każde miejsce, w którym:

- wpis **przeczy stanowi świata, kanonowi albo wcześniejszym wpisom** —
  położenie, czas podróży, pieniądze, stan statku, fakty o postaciach;
- **powołuje się na fakt, który przestał obowiązywać** (nie ma go w stanie
  świata, albo ma ustawione `valid_to`);
- **dotyka wątku oznaczonego `do_not_touch`** albo rozwija wątek oznaczony
  `tylko wzmianka`;
- **droga nie zaczyna się tam, gdzie skończył się poprzedni wpis**, albo kończy
  się gdzie indziej niż deklaruje `location`;
- **świat albo obcy przeczą własnej regule**, fizyce lub biologii;
- **rozwiązanie przychodzi z przypadku albo z zewnątrz**;
- ktoś **objaśnia regułę świata zamiast pokazać ją w zdarzeniach**;
- Ebner **tłumaczy czytelnikowi rzeczy, które sam zna**;
- pojawia się **szczegół, który nic nie wnosi**;
- wpis **powtarza sytuację, rozwiązanie albo pierwsze zdanie** z wcześniejszych
  wpisów;
- wpis **przejmuje nazwy lub zdarzenia ze wzorców stylu** — Arvel, stacja pomp,
  klient zmarły w trakcie dojazdu. Wzorce są ilustracją rejestru, nie częścią
  świata, a model widzi je przy każdej generacji, więc ciąży ku nim;
- wpis **podaje twardą liczbę** przy czasie podróży, parametrach Hanny albo
  odległości, w miejscu, gdzie nie służy to żartowi — każda taka liczba wiąże
  wszystkie następne wpisy.

## Jak rozstrzygasz

Rozdziel dwie rzeczy, bo mają różne konsekwencje:

**Twarda sprzeczność** — wpis przeczy zapisanemu stanowi w sposób sprawdzalny:
zamknięty fakt, wątek `do_not_touch`, niemożliwa geografia, Ebner jest w dwóch
miejscach naraz. Tego nie da się wyredagować i **wpis nie może iść dalej**.
Zwróć werdykt `blokuj` z listą sprzeczności.

**Miękka wątpliwość** — szczegół, który nic nie wnosi, powtórzony motyw, reguła
objaśniona zamiast pokazana, zbyt precyzyjna liczba. To poprawiasz sam,
zachowując treść i nastrój.

Nie blokuj z powodów stylistycznych. Fałszywy alarm kosztuje cały dzień wpisu i
niczego nie kupuje.

## Stan świata

{stan}

## Pokrewne wcześniejsze wpisy

{rag}

## Wpis do sprawdzenia

{wpis}

## Format odpowiedzi

Najpierw linia werdyktu: `WERDYKT: ok` albo `WERDYKT: blokuj`.

Przy `blokuj` — pod spodem lista twardych sprzeczności, każda w jednej linii, i
nic więcej.

Przy `ok` — pod spodem pełny poprawiony wpis wraz z frontmatterem, bez
komentarza. Jeśli nic nie wymagało poprawki, zwróć wpis bez zmian.

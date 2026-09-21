# Ekstrakcja stanu świata

Krok 5 pipeline'u. Czytasz opublikowany wpis i zwracasz **wyłącznie obiekt
JSON** opisujący, co ten wpis zmienił w świecie. Bez komentarza, bez bloku
Markdown, bez wyjaśnień.

Klucze są po angielsku — czyta je kod. Wartości tekstowe po polsku.

## Zasada naczelna: zapisujesz deltę, nie streszczenie

Nie opisujesz, o czym był wpis. Opisujesz, **co się zmieniło**. Wiersz wpisu —
dzień, tytuł, miejsce, rodzaj, treść — kod bierze z pliku Markdown i nie wolno go
tu powtarzać.

Jeśli wpis niczego nie zmienił, zwróć obiekt z samym `day`. To jest poprawna
odpowiedź, zwłaszcza dla wpisów rodzaju `quiet`.

## Jak mapować to, co widzisz

**Nowe miejsce, osoba, organizacja albo statek** → `entities`. Identyfikator
małymi literami z myślnikami. Miejsca zagnieżdżaj przez `parent`: księżyc w
planecie, planeta w układzie. Nie dodawaj bytu, który już istnieje w stanie
świata.

**Przemieszczenie** → `travel`, po jednym wpisie na przeskok, w kolejności
`seq`. Pierwszy przeskok wychodzi z miejsca, w którym skończył się poprzedni
wpis; ostatni kończy tam, gdzie `location` tego wpisu.

**Sprawa, która się zaczyna, toczy albo kończy** → `threads`. Dług, spór,
niedokończone zlecenie, powracający żart — wszystko to są wątki.

Sprawdź to osobno, bo najłatwiej tu przeoczyć: **jeśli wpis zajmuje się czymś,
co ciągnie się dłużej niż jeden dzień, to jest wątek i trzeba go otworzyć.**
Zlecenie rozpoznane wczoraj i wykonane dziś, spór, który będzie miał ciąg
dalszy, usterka, do której Ebner wróci — wszystko to. Nie wystarczy, że wpis
wspomni istniejący wątek; sprawa, o której wpis naprawdę jest, ma mieć własny.

**Cokolwiek, co od teraz obowiązuje w świecie** → `facts_opened`. To jest
najszerszy worek i celowo:

- stan Hanny („uszczelka w obiegu drugim wymieniona", „ładownia bez oświetlenia")
- pieniądze („dostał zapłatę za bramę na Hoonu", „nie ma na paliwo")
- zadłużenie i wierzytelności („winien jest kancelarii z Varnu, kwota rośnie")
- jaki jest świat i ludzie w nim

Każdy fakt w `facts_opened` **musi mieć treść i podmiot**. Fakt bez treści to
pusta skorupa: nic nie wnosi do świata, a wygląda, jakby wnosił.

**Zmierzona wielkość, tempo albo okres są faktem — i to najważniejszym.**
Jeśli wpis ustala, ile czegoś jest, jak często coś przychodzi albo ile trwa
cykl, to jest dokładnie ta rzecz, którą następne wpisy muszą znać, bo inaczej
jej zaprzeczą. Dni 28, 29 i 30 nie zapisały **ani jednego faktu**, a ustaliły:
że doba Ebnera na Oskrze ma osiem przejść bąbla, że jego wieczór to siódme
przejście, i — w Dniu 30, który jest w całości o tym pomiarze — że sygnał
przychodzi raz na jeden bąbel. Żadna z tych rzeczy nie weszła do kanonu, więc
Dzień 33 napisał „czekaliśmy sześć bąbli" w świecie, w którym sześć bąbli to
sześć wezwań, i nikt nie miał tego z czym porównać.

Wpis, który czegoś dowiódł, zmierzył albo policzył, **nie może wyjść bez
faktu**. Brak faktów jest sygnałem, że coś przeoczyłeś, a nie że dzień był
spokojny — spokojny dzień też zmienia stan Hanny, zapasy albo nastrój
rachunków.

Fakt, który **przestał obowiązywać**, wymieniasz w `facts_closed` — tam wystarczy
sam identyfikator. Faktów się nie edytuje: naprawa, spłata czy zmiana
okoliczności **zamyka stary fakt i otwiera nowy**.

Identyfikator do zamknięcia **musi pochodzić z listy w stanie świata powyżej** —
jest tam podany przy każdym fakcie. Nie wymyślaj własnego: zamknięcie
nieistniejącego faktu niczego nie zamyka i nikt tego nie zauważy.

**Reguła, na której stoi obca cywilizacja** → fakt z `kind: "world_rule"`,
którego podmiotem jest to miejsce. Jedno zdanie. Tylko wtedy, gdy wpis taką
regułę faktycznie odsłonił.

**Fragmenty do wyszukiwania** → `fragments`, najwyżej pięć, a zwykle dwa albo
trzy. Wybieraj to, do czego warto będzie wrócić za sto wpisów: scena, dokument,
puenta, opis świata. Treść fragmentu ma być **cytatem albo zwięzłym oddaniem**
tego miejsca wpisu, nie etykietą. Fragment nie mający związku z żadnym wątkiem ma
puste `threads`.

**Szkic** → `sketch`, jedno zdanie po polsku opisujące, co miałby przedstawiać,
albo `null`. Nie każdy wpis go potrzebuje.

## Czego nie robisz

- Nie wymyślasz faktów, których we wpisie nie ma.
- Nie otwierasz wątku dla każdej wzmianki — wątek to sprawa, która ma ciąg dalszy.
- Nie zapisujesz twardych liczb przy czasach podróży i parametrach statku, nawet
  jeśli padły we wpisie: przy pieniądzach, fakturach i terminach liczby są
  wskazane, przy technice nie.
- Nie zamykasz wątku, który we wpisie tylko przycichł.

## Gdzie skończył się poprzedni wpis

{skad}

Pierwszy przeskok w `travel` musi wychodzić **stąd**, a ostatni kończyć się tam,
gdzie wskazuje `location` we frontmatterze tego wpisu. Jeśli Ebner się nie
ruszył, nie zapisuj żadnego przeskoku.

**Miejsce w obrębie miejsca to nadal miejsce.** Dni 20 i 21 dostały rodzaj
`travel`, Ebner pojechał w nich na grzbiet czwartej nitki i zapisane zostało
zero przeskoków, bo grzbiet nie miał identyfikatora — a w Dniu 27 wrócił tam
i dalej nie miał. Reguła jest taka: jeśli Ebner **pracuje** gdzieś, **nocuje**
albo **tam wróci**, to jest byt, nawet jeśli leży wewnątrz miejsca, które już
istnieje. Wprowadź je w `entities` z `parent` wskazującym na to większe
miejsce, i zapisz przeskok.

Mijana po drodze sceneria identyfikatora nie potrzebuje. Kryterium nie brzmi
„czy zostało nazwane", tylko „czy ktoś tam jeszcze wróci".

## Byty, które już istnieją

Nie wprowadzaj ich ponownie w `entities`. Odwołuj się do nich tym
identyfikatorem — także w `parent`, `subject`, `travel` i `threads` fragmentów.

{byty}

## Stan świata przed tym wpisem

{stan}

## Wpis

{wpis}

## Schemat odpowiedzi

Twoja odpowiedź musi być poprawna wobec poniższego schematu JSON. Pola nieużyte
pomiń — nie wypełniaj ich pustymi tablicami.

{schema}

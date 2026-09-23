# Rejestr: warsztat kontra kancelaria

Ten dziennik pisze fachowiec, nie urzędnik. Kancelaria jest w nim po to, żeby
się o nią rozbijał konkret — faktura ma sens wtedy, gdy obok leży rozebrana
wciągarka. Kiedy znika warsztat, a zostaje sam przepis, wpis przestaje być
dziennikiem roboczym i staje się protokołem.

To się stało. Dzień 30 ma dwadzieścia trzy słowa urzędowe na jedno
warsztatowe: same dostawy, odbiorcy, rubryki i rozliczenia, i ani jednej
rzeczy, której da się dotknąć. Czytelnik przestał czytać w tym miejscu, a
pomiar wskazał to samo miejsce niezależnie od niego.

Dlatego proporcja jest liczona mechanicznie i trafia do kroku redakcji jako
poprawka — tak samo jak ziemski kalendarz. **Nie jest to zakaz pisania o
przepisach.** Absurd urzędowy jest osią tego świata. Chodzi o to, żeby obok
przepisu stało narzędzie.

Próg: wpis liczy się jako przeważony, gdy ma **co najmniej dziesięć** słów z
listy kancelaryjnej i **co najmniej dwa razy** więcej ich niż ze wszystkich list
konkretnych razem. Dwa warunki, bo sama proporcja w krótkiej notatce nic nie
znaczy.

Listy konkretu są dwie i to jest poprawka po realnym błędzie miernika. Pierwsza
wersja miała tylko nazwy rzeczy z warsztatu Hanny — kołnierz, uszczelka, gwint,
smar, pilnik, wciągarka — czyli słownik jednego statku. Na Netli konkret nazywa
się inaczej: zarost, śluz, kanaliki, lustro, miska, kreda. Dzień 68 wyciął
próbkę narośli, wystawił trzy kawałki w trzech środowiskach i zmierzył, na jakiej
wysokości jest najgrubsza — a miernik zaliczył mu **dwa** słowa warsztatowe i
tylko dlatego nie krzyknął, że nie został przekroczony próg bezwzględny. Rzeczy
na obcym świecie mają obce nazwy; **czasowniki roboty nie mają**. Fachowiec
wszędzie wierci, mierzy, podważa, szoruje i rozbiera, więc druga lista łapie
czynność i materiał zamiast inwentarza.

## Kancelaria

Wyrażenia regularne, dopasowywane w granicach słowa, bez względu na wielkość
liter. Jedna linia to jeden wzorzec.

```regex
przepis\w*
rubryk\w*
linijk\w*
ksi[ęe]g\w*
zapis\w*
zdarzeni\w*
rozlicz\w*
taryf\w*
dostaw\w*
odbiorc\w*
w[łl]a[śs]cicie\w*
w[łl]asno[śs]\w*
aneks\w*
deklar\w*
termin\w*
urz[ęe]d\w*
formal\w*
procedur\w*
rejestr\w*
wniosk\w*
wniose\w*
g[łl]osowani\w*
```

## Warsztat: rzeczy

```regex
ko[łl]nierz\w*
uszczelk\w*
zaw[óo]r|zaworu|zawory
gwint\w*
smar\w*
pilnik\w*
spr[ęe][żz]yn\w*
[śs]rub\w*
klucz\w*
lutow\w*
rur\w*
blach\w*
kab(?:el|l\w+)
reaktor\w*
obieg\w*
pomp\w*
[łl]o[żz]ysk\w*
wci[ąa]gark\w*
zapadk\w*
z[łl][ąa]cz\w*
ogniw\w*
k[ąa]townik\w*
p[łl]oz\w*
podpor\w*
kadłub\w*
[śs]lusar\w*
```

## Warsztat: czynności i materiał

Te same zasady. Ta lista jest niezależna od świata: zmieniają się nazwy rzeczy,
nie nazwy roboty.

```regex
odkr[ęe]c\w*
przykr[ęe]c\w*
dokr[ęe]c\w*
wkr[ęe]c\w*
rozkr[ęe]c\w*
poluzow\w*
zaci[śs]\w*
zacisk\w*
podwa[żz]\w*
wiert\w*
wierc\w*
przewierc\w*
wywierc\w*
wyci[ąę]\w*
naci[ąa]g\w*
pilow\w*
spilow\w*
szlifow\w*
szor\w*
wyszor\w*
rozebra\w*
rozbier\w*
zmierz\w*
mierz\w*
uszczeln\w*
klep\w*
zatk\w*
przetk\w*
narz[ęe]dzi\w*
wi[óo]r\w*
opi[łl]\w*
osad\w*
szczelin\w*
p[ęe]kni[ęe]\w*
kraw[ęe]d[źz]\w*
warstw\w*
rozpuszczaln\w*
skafand\w*
he[łl]m\w*
```

## Poprawka

Jedna linia, doklejana do listy poprawek dla kroku redakcji. `{ile}` i `{iles}`
zostają zastąpione liczbami.

```text
wpis jest przeważony kancelarią: {ile} słów urzędowych na {iles} konkretnych — zostaw sens przepisów, ale pokaż przy nich robotę: narzędzie, materiał, czynność, coś, co Ebner trzyma w rękach
```

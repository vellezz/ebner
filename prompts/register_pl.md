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
pierwszej listy i **co najmniej dwa razy** więcej ich niż z drugiej. Dwa
warunki, bo sama proporcja w krótkiej notatce nic nie znaczy.

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

## Warsztat

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

## Poprawka

Jedna linia, doklejana do listy poprawek dla kroku redakcji. `{ile}` i `{iles}`
zostają zastąpione liczbami.

```text
wpis jest przeważony kancelarią: {ile} słów urzędowych na {iles} warsztatowych — zostaw sens przepisów, ale pokaż przy nich robotę: narzędzie, materiał, czynność, coś, co Ebner trzyma w rękach
```

# TalkHa Operator Server

Minimalny serwer operatorski dla `TalkHa Client`.

Zadania:
- rejestracja agentow klienta
- przyjmowanie stalego ruchu wychodzacego od klienta
- kolejkowanie zadan `TalkHa` i `TalkHaLokal`
- odbior wynikow
- audit log
- zapis ostatniego IP klienta i czasu polaczenia
- prosty operator CLI `cli.py`

Model aktualny:
- klient wpisuje tylko `client_id` i `ha_token`
- `operator_url` jest stale wpisany w add-on
- `registration_token` jest wspolny i stale wpisany po obu stronach

Ten katalog jest oddzielny od repo strony `ha-uslugi`.
Nie nalezy wdrazac go do repo GitHub Pages ani mieszac z publika strony.

Docelowo trzymaj to w osobnym repo, np.:
- `talkha-client-addon`
- `talkha-operator-server`

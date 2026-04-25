# TalkHa Operator Server

Minimalny serwer operatorski dla `TalkHa Client`.

Zadania:
- rejestracja agentow klienta
- przyjmowanie stalego ruchu wychodzacego od klienta
- kolejkowanie zadan `TalkHa` i `TalkHaLokal`
- odbior wynikow
- jawny status zadania `queued` / `running` / `completed`
- audit log
- zapis ostatniego IP klienta i czasu polaczenia
- prosty operator CLI `cli.py`

Model aktualny:
- klient wpisuje `client_id`, `ha_token` i `operator_url`
- `operator_url` moze wskazywac tunel, domene, DDNS albo inny osiagalny endpoint operatora
- `registration_token` jest wspolny i stale wpisany po obu stronach
- kazdy klient ma osobny profil komunikacji w `clients.json`
- operator wybiera klienta indywidualnie przez `client_id`
- domyslny tryb komunikacji: `operator_reverse_http`
- operator CLI ma juz `clients`, `add-client`, `remove-client`, `job`, `run-job`, `result`, `wait`
- wrapper `hx` jest preferowany do codziennej pracy operatora, w tym `hx doctor`, `hx auto-summary`, `hx script-summary`, `hx thresholds` i `hx threshold-check`

Ten katalog jest oddzielny od repo strony `ha-uslugi`.
Nie nalezy wdrazac go do repo GitHub Pages ani mieszac z publika strony.

Docelowo trzymaj to w osobnym repo, np.:
- `talkha-client-addon`
- `talkha-operator-server`

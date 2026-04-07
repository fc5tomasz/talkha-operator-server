# Deploy na Twoj serwer

To jest osobna usluga. Nie wrzucaj jej do repo ani katalogu strony `ha-uslugi`.

Proponowane katalogi:
- `/opt/talkha-operator-server`
- `/etc/nginx/sites-available/operator.ha-expert.com.conf`

Minimalny deploy:
1. Skopiuj katalog `operator_server/` do `/opt/talkha-operator-server`.
2. Utworz `.venv` i zainstaluj `requirements.txt`.
3. Skopiuj `.env.example` do `.env` i uzupelnij token admina.
4. Skopiuj `clients.example.json` do `data/clients.json` i wpisz klientow.
5. Dodaj unit `systemd/talkha-operator.service`.
6. Dodaj reverse proxy `nginx/operator.ha-expert.com.conf`.
7. Wlacz HTTPS i start uslugi.

# Uzycie testowe

1. Przygotuj pliki:
```bash
cp .env.example .env
mkdir -p data
cp clients.example.json data/clients.json
```

2. Ustaw token admina w `.env`.

3. Uruchom serwer:
```bash
set -a
. ./.env
set +a
python3 server.py
```

4. W add-onie klienta wpisz:
```yaml
operator_url: "https://twoj-serwer-operatora"
client_id: "demo-client"
registration_token: "replace-with-long-random-registration-token"
```

5. Kolejkuj zadanie:
```bash
curl -X POST http://127.0.0.1:8787/api/v1/jobs \
  -H 'Authorization: Bearer replace-with-long-random-admin-token' \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"demo-client","type":"talkha","args":["podsumowanie-logow-systemowych","--limit","5"]}'
```

6. Odbierz wynik:
```bash
curl \
  -H 'Authorization: Bearer replace-with-long-random-admin-token' \
  http://127.0.0.1:8787/api/v1/jobs/<job_id>
```

7. Podejrzyj klientow i ostatnie IP:
```bash
curl \
  -H 'Authorization: Bearer replace-with-long-random-admin-token' \
  http://127.0.0.1:8787/api/v1/clients
```

8. Zamiast `curl` mozesz uzyc CLI:
```bash
python3 cli.py --admin-token replace-with-long-random-admin-token clients
python3 cli.py --admin-token replace-with-long-random-admin-token job --client-id demo-client --type talkha -- --help
python3 cli.py --admin-token replace-with-long-random-admin-token result --job-id <job_id>
```

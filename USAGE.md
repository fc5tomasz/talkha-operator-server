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
ha_token: "TOKEN_HA_KLIENTA"
client_id: "demo-client"
operator_url: "https://twoj-serwer-operatora"
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

Odpowiedz zawiera teraz jawne pola:
- `status`: `queued`, `running`, `completed`
- `result_available`
- `queue_position`

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
python3 cli.py --admin-token replace-with-long-random-admin-token run-job --client-id demo-client --type talkhalokal -- automation-summary --target "Grzejnik off bufor on tryb lato" --match-by alias
python3 cli.py --admin-token replace-with-long-random-admin-token result --job-id <job_id>
python3 cli.py --admin-token replace-with-long-random-admin-token wait --job-id <job_id>
```

9. Na co dzien wygodniej uzywac wrappera `hx` z tego repo:
```bash
install -m 0755 ./hx ~/.local/bin/hx
```

10. Potem uzywaj `hx` normalnie:
```bash
hx doctor
hx auto-summary "Grzejnik off bufor on tryb lato"
hx thresholds sensor.czujnik_salon_temperature
hx threshold-check sensor.czujnik_salon_temperature 24
hx upsert-automation ./moja_automatyzacja.yaml
hx delete-automation "Alias automatyzacji"
hx upsert-script ./moj_skrypt.yaml
hx delete-script "Alias skryptu"
hx helper-upsert input_boolean moj_helper ./helper.json
hx helper-delete input_boolean moj_helper
hx tx-summary TX_ID
hx rollback-tx TX_ID
```

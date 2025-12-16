## Vet-bot MVP

Telegram-бот “ВетСоветник AI” на `aiogram` с мульти‑питомцем, лимитами по тарифам и подключением моделей через `vsegpt.ru` (OpenAI-compatible `chat/completions`).

### Настройка (локально)

- **Установить зависимости**:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

- **Создать `.env`** по примеру `env.example` и заполнить:
  - `TELEGRAM_BOT_TOKEN`
  - `VSEGPT_API_KEY`

- **Запуск**:

```bash
python bot.py
```

### Тарифы (MVP)

- **FREE**: лимит `FREE_DAILY_LIMIT` запросов в день, дешёвая модель `MODEL_FREE_CHAT`
- **STANDARD**: лимит `STANDARD_DAILY_LIMIT` запросов в день, модель `MODEL_STANDARD_CHAT`
- **PRO**: лимит `PRO_DAILY_LIMIT` (пусто = безлимит), модель `MODEL_PRO_CHAT`, а фото/PDF анализируются через `MODEL_PRO_VISION`

Команда **`/me`** показывает текущий тариф и остаток на сегодня.

### Деплой на VPS (systemd)

Пример для Ubuntu/Debian. Пути можно менять, главное сохранить `WorkingDirectory`.

```bash
sudo adduser --system --group vetbot
sudo mkdir -p /opt/vet-bot
sudo chown -R vetbot:vetbot /opt/vet-bot
```

Скопируйте проект в `/opt/vet-bot`, затем:

```bash
cd /opt/vet-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env  # и заполнить
```

Установите сервис:

```bash
sudo cp deploy/vetbot.service /etc/systemd/system/vetbot.service
sudo systemctl daemon-reload
sudo systemctl enable --now vetbot
sudo systemctl status vetbot
```

Логи:

```bash
journalctl -u vetbot -f
```

### Деплой на VPS (Ubuntu 24.04, systemd + лог в файл как у мед-бота)

Если ты деплоишь как `ai-doctor-bot` (логи в файл через `StandardOutput=append`), используй шаблон `deploy/vetbot-ubuntu24.service`.

```bash
sudo mkdir -p /opt/vet-bot
sudo chown -R root:root /opt/vet-bot
```

Скопируй проект в `/opt/vet-bot` (например через `scp`/`rsync`), затем:

```bash
cd /opt/vet-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env  # заполнить токены/ключи
```

Установи systemd сервис:

```bash
sudo cp deploy/vetbot-ubuntu24.service /etc/systemd/system/vetbot.service
sudo systemctl daemon-reload
sudo systemctl enable --now vetbot
sudo systemctl status vetbot
```

Логи в файле:

```bash
tail -f /opt/vet-bot/bot.log
```



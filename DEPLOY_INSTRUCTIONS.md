# Инструкции по деплою

## Изменения для деплоя

Добавлены следующие функции:
1. **Система промокодов** - модели PromoCode и PromoUsage
2. **Реферальная программа** - поле referrer_id в User
3. **Новые хендлеры** - handlers/promo.py
4. **Обновлена логика лимитов** - check_text_limits для текстовых сообщений

## Файлы для коммита

```
bot.py
handlers/core.py
handlers/medcard.py
handlers/promo.py (новый)
models.py
storage.py
.env.example (обновлен)
```

## Команды для деплоя

### 1. Локально (перед пушем в GitHub):

```bash
# Добавить файлы
git add bot.py handlers/core.py handlers/medcard.py models.py storage.py handlers/promo.py .env.example

# Коммит
git commit -m "Add promo codes and referral system"

# Пуш в main
git push origin main
```

### 2. Автоматический деплой через GitHub Actions

После пуша в main, GitHub Actions автоматически:
- Подключится к VPS
- Обновит код через `git pull`
- Установит зависимости
- Перезапустит сервис vetbot

### 3. Ручной деплой на VPS (если нужно):

```bash
ssh user@your-vps
cd /opt/vet-bot
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart vetbot
sudo systemctl status vetbot
```

## Важно после деплоя

1. **Миграция БД** - новые таблицы (promo_codes, promo_usage) и поле referrer_id создадутся автоматически при первом запуске
2. **Проверка логов** - `sudo journalctl -u vetbot -f` для мониторинга
3. **Тестирование** - проверить команды `/promo` и `/create_promo`

## Создание первого промокода

После деплоя, как админ, можно создать промокод:

```
/create_promo TEST_CODE subscription_days 7 100
```

Или для баланса:

```
/create_promo BONUS_10 balance_add 10 0
```

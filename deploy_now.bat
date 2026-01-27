@echo off
echo ========================================
echo Деплой Vet-bot: Промокоды и Рефералы
echo ========================================
echo.

echo [1/4] Добавляю файлы в git...
git add bot.py handlers/core.py handlers/medcard.py models.py storage.py handlers/promo.py .env.example
if %errorlevel% neq 0 (
    echo ОШИБКА: Не удалось добавить файлы
    pause
    exit /b 1
)

echo.
echo [2/4] Создаю коммит...
git commit -m "Add promo codes and referral system"
if %errorlevel% neq 0 (
    echo ОШИБКА: Не удалось создать коммит
    pause
    exit /b 1
)

echo.
echo [3/4] Отправляю изменения в GitHub...
git push origin main
if %errorlevel% neq 0 (
    echo ОШИБКА: Не удалось отправить в GitHub
    pause
    exit /b 1
)

echo.
echo [4/4] Деплой завершен!
echo.
echo GitHub Actions автоматически развернет изменения на VPS.
echo Проверь статус деплоя: https://github.com/YOUR_REPO/actions
echo.
pause

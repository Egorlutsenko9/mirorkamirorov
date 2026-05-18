# Telegram Router (aiogram + telethon)

Бот для управления маршрутами пересылки через inline-кнопки + Telethon-слушатель для почти мгновенной пересылки сообщений из каналов/супергрупп в вашу супергруппу (в том числе в ветки/темы).

## Что умеет

- Доступ к управлению только для `ADMIN_USER_ID`.
- UX в одном главном сообщении (`/start`):
  - интерфейс обновляется только через редактирование;
  - временные сообщения для ввода удаляются;
  - сообщения пользователя с вводом удаляются.
- Добавление маршрута через inline-кнопку:
  - ID источника;
  - ID ветки источника (опционально);
  - ID ветки назначения (опционально).
- Чат назначения фиксированный: `DEST_CHAT_ID=-1003714740567`.
- Telethon читает источники, а отправка в целевую группу идет от имени бота (Bot API).
- Для нескольких фото/видео в одном посте используется отправка альбомом.
- Логи с таймстампами, уровнями и понятными русскими сообщениями.
- Хранилище маршрутов: `sqlite`.

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Настройка

1. Скопируйте `.env.example` в `.env`.
2. Заполните обязательные параметры:
   - `BOT_TOKEN`
   - `ADMIN_USER_ID`
   - `TG_API_ID`
   - `TG_API_HASH`
   - `DEST_CHAT_ID`
3. `TG_PHONE` можно оставить пустым: если сессии Telethon нет, номер запросится в консоли.

## Запуск

```bat
run.bat
```

Или с уровнем логов:

```bat
run.bat DEBUG
```

При первом запуске Telethon попросит:
1. Код из Telegram.
2. Пароль 2FA (если включен).

## VPS (Ubuntu)

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
git clone https://github.com/Egorlutsenko9/mirorkamirorov.git
cd mirorkamirorov
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

Для фонового запуска через `systemd` (рекомендуется):

1. Создайте файл `/etc/systemd/system/mirorka.service`:
```ini
[Unit]
Description=Telegram Mirorka Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/mirorkamirorov
ExecStart=/opt/mirorkamirorov/.venv/bin/python -m app.main
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
```
2. Запуск:
```bash
sudo systemctl daemon-reload
sudo systemctl enable mirorka
sudo systemctl start mirorka
sudo systemctl status mirorka
```

## Важно

- Аккаунт Telethon должен иметь доступ к источникам и к чату назначения.
- Бот должен быть добавлен в чат назначения и иметь право отправки сообщений/медиа.
- Для отправки в ветку назначения указывайте `ID ветки` (topic id / top message id).
- Если хотите слушать весь источник без фильтра ветки, в шаге ветки источника отправляйте `0`.

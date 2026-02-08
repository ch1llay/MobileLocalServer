# Mobile Local File Server

Локальный HTTP-сервер для приёма файлов по Wi-Fi. Предназначен для запуска в Termux на телефоне: включаете точку доступа, запускаете сервер — с ноутбука или другого устройства в той же сети можно открыть страницу в браузере, ввести PIN и загружать файлы на телефон.

## Требования

- Python 3.10+
- Termux (на Android) или любой другой хост в локальной сети

## Установка в Termux

```bash
pkg update && pkg install python
git clone https://github.com/YOUR_USER/MobileLocalServer.git
cd MobileLocalServer
pip install -r requirements.txt
```

## Настройка

1. Скопируйте пример конфигурации и отредактируйте:

   ```bash
   cp env.example .env
   ```

2. Сгенерируйте хэш PIN (подставьте свой PIN):

   ```bash
   python scripts/generate_pin_hash.py 1234
   ```

3. Добавьте выведенные `PIN_HASH` и `PIN_SALT` в `.env`. Пример `.env`:

   ```
   UPLOAD_DIR=./uploads
   PORT=8080
   SECRET_KEY=замените-на-длинную-случайную-строку
   TOKEN_MAX_AGE=86400
   MAX_UPLOAD_MB=500
   PIN_HASH=<результат generate_pin_hash>
   PIN_SALT=<результат generate_pin_hash>
   ```

4. В Termux для сохранения файлов в папку «Загрузки» можно указать:

   ```
   UPLOAD_DIR=/data/data/com.termux/files/home/storage/downloads/Received
   ```

   Предварительно выполните `termux-setup-storage`, чтобы разрешить доступ к хранилищу.

## Запуск

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Или используйте скрипт (порт берётся из переменной окружения `PORT` или 8080):

```bash
chmod +x run.sh
./run.sh
```

Сервер будет доступен по адресу `http://<IP_телефона>:8080`.

## Как узнать IP телефона

- В Termux: `ip addr` (интерфейс `wlan0` при раздаче Wi-Fi).
- В настройках точки доступа на Android часто показывается IP раздающего устройства.

Подключите ноутбук/ПК к этой точке доступа и в браузере откройте `http://<IP>:8080`. Введите PIN, после чего можно загружать файлы и просматривать список уже загруженных.

## Безопасность

- Доступ только по локальной сети (сервер слушает `0.0.0.0`, но без проброса портов из интернета доступа извне нет).
- PIN хранится в виде хэша (PBKDF2-HMAC-SHA256); после ввода PIN выдаётся подписанный токен с ограниченным сроком жизни (по умолчанию 24 часа).
- Токен передаётся в заголовке `Authorization: Bearer` или в query-параметре `?token=...` для ссылок на скачивание.
- Загрузки ограничены по размеру (`MAX_UPLOAD_MB`), пути к файлам проверяются (запрет path traversal).

## API

- `POST /api/login` — тело `{"pin": "1234"}`; ответ `{"token": "..."}`.
- `GET /api/files` — список файлов (заголовок `Authorization: Bearer <token>`).
- `POST /api/upload` — multipart, поле `file`; заголовок `Authorization: Bearer <token>`.
- `GET /api/files/{path}` — скачивание файла; токен в заголовке или `?token=...`.

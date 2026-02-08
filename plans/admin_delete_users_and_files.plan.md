# План: удаление пользователей и файлов админом

## Цели
- Админ может **удалять пользователей**; при удалении пользователя удаляется **вся его папка** с файлами (`uploads/<имя_папки>/`).
- Админ может **удалять отдельные файлы** из списка загруженных файлов.

---

## 1. Бэкенд

### UploadCodesService — [app/services/upload_codes.py](app/services/upload_codes.py)
- Добавить метод **`delete_user_by_index(index: int) -> str | None`**:
  - загрузить записи из JSON;
  - если `index` вне диапазона — вернуть `None`;
  - удалить запись по индексу (`pop`), сохранить обновлённый список;
  - вернуть **label** удалённого пользователя (для удаления папки).

### UploadService — [app/services/upload.py](app/services/upload.py)
- **`delete_folder(sender_name: str) -> None`**: по переданному имени (label) вычислить имя папки через `_sanitize_sender_name(sender_name)`, путь `_upload_dir / safe_sender`; если это каталог — удалить рекурсивно (`shutil.rmtree`). При невалидном `sender_name` (ValueError) — ничего не делать.
- **`delete_file(relative_path: str) -> None`**: через `_safe_join(relative_path)` получить путь; если это файл — удалить (`path.unlink()`); иначе — выбросить `FileNotFoundError`, чтобы API отдал 404.

### API — [app/routers/api_upload.py](app/routers/api_upload.py)
- **GET /api/admin/users**: в ответе для каждого пользователя добавлять поле **`index`** (порядковый номер в списке). Формат: `{"users": [{"label": "...", "created_at": "...", "index": 0}, ...]}`.
- **DELETE /api/admin/users/{index}** (admin, по токену):
  - `index: int` из path;
  - вызвать `codes_service.delete_user_by_index(index)`; если вернулось `None` — ответ **404**;
  - иначе взять возвращённый `label`, вызвать `upload_service.delete_folder(label)`;
  - ответ **204 No Content**.
- **DELETE /api/files/{path:path}** (admin, по токену):
  - `path` — например `Alice/file.pdf`;
  - вызвать `upload_service.delete_file(path)`; при `FileNotFoundError` / ValueError — **404**;
  - иначе ответ **204 No Content**.

---

## 2. Админ-панель — [app/web/templates/admin.html](app/web/templates/admin.html)

### Список пользователей
- В `loadUsers()` для каждого элемента списка добавлять кнопку **«Удалить»**.
- У каждой записи использовать `u.index` из ответа API; при клике по «Удалить» показывать подтверждение: *«Удалить пользователя <имя> и всю папку с файлами?»*; при подтверждении — **DELETE /api/admin/users/** + `u.index`, затем вызвать `loadUsers()` и `loadFileList()`.

### Список файлов
- В `loadFileList()` для каждого файла добавлять кнопку **«Удалить»**.
- При клике — подтверждение: *«Удалить файл <имя>?»*; при подтверждении — **DELETE /api/files/** + `encodeURIComponent(f.path)` (использовать `f.path`, например `Alice/file.pdf`), затем `loadFileList()`.

---

## 3. Безопасность и краевые случаи
- Оба DELETE доступны только с токеном админа (та же зависимость, что и для GET /api/files).
- Path traversal блокируется в `_safe_join`; `delete_file` использует тот же механизм.
- При удалении пользователя папка может отсутствовать — в `delete_folder` проверять `is_dir()` перед `rmtree`.

---

## Порядок внедрения
1. UploadCodesService: `delete_user_by_index`.
2. UploadService: `delete_folder`, `delete_file`.
3. API: добавить `index` в GET /api/admin/users; эндпоинты DELETE /api/admin/users/{index} и DELETE /api/files/{path:path}.
4. Admin HTML: кнопки «Удалить» у пользователей и файлов, подтверждение, вызовы API и обновление списков.

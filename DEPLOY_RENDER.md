# Форум NAGIN GTA в інтернеті (Render)

1. Створіть акаунт на https://github.com і новий **приватний** репозиторій. Завантажте туди вміст папки `nagin_forum`
   (кнопка Add file → Upload files; `server.py` має лежати в корені репозиторію).
2. На https://render.com: **New → Web Service** → підключіть GitHub-репозиторій.
   Runtime: **Python 3**, Build Command: `echo ok`, Start Command: `python server.py`.
   (Або **New → Blueprint** — Render сам прочитає `render.yaml`.)
3. Environment: додайте `NAGIN_DATA=/var/data`. Після деплою Render дасть адресу `https://назва.onrender.com`;
   `base_url` і захищені cookie підхоплюються автоматично.
4. Відкрийте адресу й зареєструйтесь першим — станете Власником.

## Важливо про дані
- **Free-план:** сайт «засинає» без відвідувачів (перший вхід ~30-60 с), а файли (база, аватари) **стираються** при кожному
  перезапуску. Підходить лише для показу.
- Щоб дані зберігалися: план **Starter** (платний) + Disk (розкоментуйте `disk` у `render.yaml`, mountPath `/var/data`).
- Пошта: без SMTP листи не надсилаються. Додайте змінні `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`
  (наприклад Gmail з паролем застосунку або Brevo/Mailgun). Інакше підтвердіть email вручну: Адмінпанель → Користувачі.
- Зв'язок із ігровим сервером: у `Config.forum.url` гри вкажіть свою адресу Render і ключ зі сторінки «Гра».

"""NAGIN GTA | керування форумом з консолі.
  python manage.py setrole <логін> <роль>   (owner, deputy_owner, admin, player ...)
  python manage.py verify <логін>          підтвердити email
  python manage.py passwd <логін>          задати новий пароль
  python manage.py roles                   список ролей
  python manage.py key                     ключ API для ігрового сервера
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import config as C, db as DB, security as S


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    DB.init_db()
    conn = DB.connect()
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "roles":
        for r in conn.execute("SELECT key, name FROM roles ORDER BY rank DESC"):
            print("%-22s %s" % (r["key"], r["name"]))
    elif cmd == "key":
        print(C.game_key())
    elif cmd in ("setrole", "verify", "passwd") and args:
        u = conn.execute("SELECT id, username FROM users WHERE username = ?", (args[0],)).fetchone()
        if not u:
            print("Користувача не знайдено."); return
        if cmd == "setrole":
            r = conn.execute("SELECT id, name FROM roles WHERE key = ?", (args[1] if len(args) > 1 else "",)).fetchone()
            if not r:
                print("Невідома роль. Дивіться: python manage.py roles"); return
            conn.execute("UPDATE users SET role_id = ?, org_id = NULL WHERE id = ?", (r["id"], u["id"]))
            print("Роль %s -> %s" % (u["username"], r["name"]))
        elif cmd == "verify":
            conn.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (u["id"],))
            print("Email підтверджено.")
        else:
            p1 = getpass.getpass("Новий пароль: ")
            problem = S.check_password_strength(p1, u["username"])
            if problem:
                print(problem); return
            conn.execute("UPDATE users SET pass_hash = ? WHERE id = ?", (S.hash_password(p1), u["id"]))
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (u["id"],))
            print("Пароль змінено, усі сеанси завершено.")
    else:
        print(__doc__); return
    conn.commit()


main()

#!/usr/bin/env python3
"""Reset a Budget Buddy password from the machine it runs on.

For when you've forgotten your password and no other admin can send you a
reset link. Needs access to this machine and its .env, which is the proof
it's you. Run from the budget-buddy folder:

    ./.venv/bin/python scripts/reset_password.py              # list accounts
    ./.venv/bin/python scripts/reset_password.py alex          # reset alex
    ./.venv/bin/python scripts/reset_password.py alex --admin  # ...and make admin

Changing the password signs that account out everywhere. The app can keep
running while you do this.
"""

import argparse
import getpass
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)  # so settings find .env and the relative database path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("username", nargs="?", help="account to reset (omit to list accounts)")
    parser.add_argument("--admin", action="store_true", help="also make the account an admin")
    parser.add_argument("--activate", action="store_true", help="also re-activate a deactivated account")
    args = parser.parse_args()

    from app.database import SessionLocal
    from app.models import User
    from app.services.users import AccountError, check_password
    from app.utils.auth import hash_password

    with SessionLocal() as db:
        if not args.username:
            users = db.query(User).order_by(User.id).all()
            if not users:
                print("No accounts yet. Open Budget Buddy in a browser to create the first one.")
                return 0
            print("Accounts:")
            for u in users:
                flags = [f for f, on in (("admin", u.is_admin), ("deactivated", not u.is_active)) if on]
                print(f"  {u.username}" + (f"  ({', '.join(flags)})" if flags else ""))
            print("\nRun again with a username to reset its password.")
            return 0

        user = db.query(User).filter(User.username == args.username).first()
        if user is None:
            print(f"No account named '{args.username}'. Run without a username to list accounts.")
            return 1
        password = getpass.getpass(f"New password for {user.username}: ")
        try:
            check_password(password)
        except AccountError as e:
            print(e)
            return 1
        if getpass.getpass("Type it again: ") != password:
            print("Passwords didn't match. Nothing changed.")
            return 1
        user.password_hash = hash_password(password)
        if args.admin:
            user.is_admin = True
        if args.activate:
            user.is_active = True
        db.commit()
        print(f"Password for {user.username} updated."
              + (" Now an admin." if args.admin else "")
              + (" Re-activated." if args.activate else "")
              + " Sign in with the new password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

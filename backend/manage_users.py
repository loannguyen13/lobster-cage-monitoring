"""Owner-only local CLI. Passwords are read using getpass, never CLI arguments."""
import argparse
from getpass import getpass
from pathlib import Path
import os

import psycopg2
from dotenv import load_dotenv

from backend.services.accounts import create_user, reset_password, username


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / '.env.local')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['create','reset-password','disable','enable'])
    parser.add_argument('username', type=username)
    parser.add_argument('--role',choices=['Viewer','Operator','Admin'],default='Viewer')
    args = parser.parse_args()
    print(f'Dashboard account: {args.username}. This is NOT the PostgreSQL login.')
    print('Use the Azure PostgreSQL server Administrator login (Portal > server > Overview).')
    print('Do not use lobster_api/lobster_ingest or your Microsoft account here.')
    admin_name = input('Existing PostgreSQL administrator login: ').strip()
    admin_password = getpass('Existing PostgreSQL administrator password: ')
    connection = psycopg2.connect(host=os.environ['PGHOST'],port=os.getenv('PGPORT','5432'),
        dbname=os.environ['PGDATABASE'],user=admin_name,password=admin_password,
        sslmode='verify-full',sslrootcert=os.environ['PGSSLROOTCERT'],connect_timeout=10)
    try:
        with connection:
            with connection.cursor() as cur:
                privilege = 'INSERT' if args.action == 'create' else 'UPDATE'
                cur.execute("SELECT has_table_privilege(current_user,'public.users',%s)", (privilege,))
                if not cur.fetchone()[0]:
                    raise ValueError('This PostgreSQL login cannot manage Dashboard users. Use the database owner/admin, not lobster_api.')
            if args.action in ('create','reset-password'):
                password = getpass(f'Choose NEW Dashboard password for {args.username} (12..128 characters): ')
                if password != getpass('Repeat application password: '):
                    raise ValueError('Passwords do not match')
                if args.action == 'create':
                    create_user(connection,args.username,password,args.role)
                else:
                    reset_password(connection,args.username,password)
            else:
                with connection.cursor() as cur:
                    cur.execute('UPDATE users SET enabled=%s,updated_at=now() WHERE username=%s RETURNING id',
                                (args.action=='enable',args.username))
                    row = cur.fetchone()
                    if row is None:
                        raise ValueError('Account not found')
                    cur.execute('UPDATE auth_sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL',(row[0],))
        print('Account operation completed.')
    finally:
        connection.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit('\nCancelled. Uncommitted account changes were rolled back.') from None
    except (ValueError,KeyError) as exc:
        raise SystemExit(str(exc)) from None
    except psycopg2.errors.UniqueViolation:
        raise SystemExit('Dashboard username already exists. Use reset-password to change its password.') from None
    except psycopg2.errors.InsufficientPrivilege:
        raise SystemExit('PostgreSQL login lacks permission. Use the database owner/admin.') from None
    except psycopg2.errors.UndefinedTable:
        raise SystemExit('Required table is missing. Run migration 005_local_auth.sql in the configured PGDATABASE.') from None
    except psycopg2.OperationalError:
        raise SystemExit('Cannot connect to PostgreSQL. Check the server Administrator login/password, PGHOST/PGDATABASE, firewall and CA path. This is not a Dashboard signin.') from None
    except psycopg2.Error:
        raise SystemExit('Database operation failed. Check migrations and database permissions.') from None

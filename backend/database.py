"""Short-lived, bounded TLS connections. API uses its own least-privilege role."""
import os
from contextlib import contextmanager

import psycopg2


def connect(*, api=False):
    prefix = 'API_' if api else ''
    return psycopg2.connect(
        host=os.environ['PGHOST'], port=int(os.getenv('PGPORT', '5432')),
        dbname=os.environ['PGDATABASE'], user=os.environ[prefix + 'PGUSER'],
        password=os.environ[prefix + 'PGPASSWORD'], sslmode='verify-full',
        sslrootcert=os.environ['PGSSLROOTCERT'], connect_timeout=10,
        options='-c statement_timeout=15000 -c lock_timeout=10000',
        application_name='lobster-api' if api else 'lobster-ingestion',
    )


@contextmanager
def session(*, api=False):
    connection = connect(api=api)
    try:
        with connection:
            yield connection
    finally:
        connection.close()

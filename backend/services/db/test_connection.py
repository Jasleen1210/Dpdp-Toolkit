#run this to connect live supabase db connection
import os

import psycopg
from dotenv import load_dotenv


load_dotenv("backend/.env")


host = os.getenv("DPDP_DB_SUPABASE_HOST")
port = os.getenv("DPDP_DB_SUPABASE_PORT", "5432")
database = os.getenv("DPDP_DB_SUPABASE_NAME")
username = os.getenv("DPDP_DB_SUPABASE_USER")
password = os.getenv("DPDP_DB_SUPABASE_PASSWORD")


print("Host:", host)
print("Port:", port)
print("Database:", database)
print("User:", username)
print("Password configured:", bool(password))


connection = None

try:
    connection = psycopg.connect(
        host=host,
        port=int(port),
        dbname=database,
        user=username,
        password=password,
        sslmode="require",
        connect_timeout=10,
    )

    print("\nSUCCESS: Connected to Supabase PostgreSQL!")

    # Test 1: basic database identity
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), current_user;")
        result = cursor.fetchone()

        print("Database:", result[0])
        print("User:", result[1])

    # Test 2: discover actual tables
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name;
        """)

        tables = cursor.fetchall()

    print("\nTABLES FOUND:")

    if not tables:
        print("  No user tables found.")

    else:
        for schema, table in tables:
            print(f"  {schema}.{table}")


except Exception as exc:
    print("\nFAILED")
    print(type(exc).__name__)
    print(str(exc))

finally:
    if connection is not None:
        connection.close()
        print("\nConnection closed.")
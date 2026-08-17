import os

from dotenv import load_dotenv

from backend.services.db.connector import (
    close_connection,
    open_read_only_connection,
)
from backend.services.db.scanner import scan_database


load_dotenv("backend/.env")


config = {
    "engine": "postgres",
    "host": os.getenv("DPDP_DB_SUPABASE_HOST"),
    "port": int(os.getenv("DPDP_DB_SUPABASE_PORT", "5432")),
    "database": os.getenv("DPDP_DB_SUPABASE_NAME"),
    "username": os.getenv("DPDP_DB_SUPABASE_USER"),
    "password_env_var": "DPDP_DB_SUPABASE_PASSWORD",
    "sslmode": "require",
}


print("========================================")
print("DPDP TOOLKIT - LIVE DATABASE SCAN")
print("========================================")

print("\nTarget:")
print("Host:", config["host"])
print("Port:", config["port"])
print("Database:", config["database"])
print("User:", config["username"])
print("Password configured:",
      bool(os.getenv("DPDP_DB_SUPABASE_PASSWORD")))


print("\nTesting read-only connection...")

connection = None

try:
    connection = open_read_only_connection(config)

    print("SUCCESS: Read-only PostgreSQL connection established.")

finally:
    close_connection(connection)


print("\nStarting PII scan...")
print("----------------------------------------")

try:
    result = scan_database(config)

    print("\nSCAN COMPLETED")

    print("\nSummary:")
    print("Engine:", result.get("engine"))
    print("Tables scanned:", result.get("scanned_tables"))
    print("Columns inspected:", result.get("inspected_columns"))
    print("Sampled values:", result.get("sampled_values"))
    print("Sample limit:", result.get("sample_limit"))
    print("Warnings:", len(result.get("warnings", [])))
    print("Findings:", len(result.get("findings", [])))

    print("\nFINDINGS")
    print("========================================")

    findings = result.get("findings", [])

    if not findings:
        print("No PII findings detected.")

    for finding in findings:
        print(
            f"\nTable:      {finding['table']}"
            f"\nColumn:     {finding['column']}"
            f"\nType:       {finding['pii_type']}"
            f"\nMethod:     {finding['method']}"
            f"\nConfidence: {finding['confidence']}"
            f"\nMatches:    {finding['match_count']}/{finding['sample_count']}"
            f"\nRisk:       {finding['risk']}"
            f"\nAction:     {finding['recommended_action']}"
        )

    warnings = result.get("warnings", [])

    if warnings:
        print("\nWARNINGS")
        print("========================================")

        for warning in warnings:
            print("-", warning)

except Exception as exc:
    print("\nSCAN FAILED")
    print(type(exc).__name__)
    print(str(exc))
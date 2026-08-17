from __future__ import annotations

import sqlite3
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = BACKEND_ROOT / "demo_data" / "dpdp_demo.db"


def create_demo_database(output_path: Path | str = DEFAULT_OUTPUT) -> Path:
    """Create a fake database containing only demonstration data, never real personal data."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                date_of_birth TEXT,
                address TEXT,
                consent_status TEXT
            );

            CREATE TABLE employees (
                id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                pan_number TEXT NOT NULL,
                aadhaar_number TEXT NOT NULL,
                department TEXT,
                salary_band TEXT
            );

            CREATE TABLE contacts (
                id INTEGER PRIMARY KEY,
                primary_contact TEXT NOT NULL,
                secondary_contact TEXT NOT NULL,
                contact_kind TEXT
            );

            CREATE TABLE customer_data (
                id INTEGER PRIMARY KEY,
                identifier TEXT NOT NULL,
                misc_info TEXT,
                purchase_count INTEGER
            );

            CREATE TABLE support_notes (
                id INTEGER PRIMARY KEY,
                note TEXT NOT NULL,
                category TEXT
            );

            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                order_total REAL NOT NULL,
                order_status TEXT NOT NULL,
                product_category TEXT NOT NULL
            );
            """
        )

        connection.executemany(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (1, "Ananya Rao", "ananya.rao@example.test", "9876543210", "2003-04-12", "12 Demo Street, Bengaluru", "granted"),
                (2, "Ravi Kumar", "ravi.kumar@example.test", "9123456789", "2002-11-05", "45 Sample Road, Pune", "granted"),
                (3, "Meera Iyer", "meera.iyer@example.test", "9988776655", "2004-01-21", "7 Test Avenue, Chennai", "revoked"),
            ],
        )
        connection.executemany(
            "INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, "Demo Person One", "DEMOP0001A", "9999 9999 9999", "Engineering", "B2"),
                (2, "Demo Person Two", "DEMOP0002B", "8888 8888 8888", "Operations", "B1"),
            ],
        )
        connection.executemany(
            "INSERT INTO contacts VALUES (?, ?, ?, ?)",
            [
                (1, "9234567890", "contact.one@example.test", "customer"),
                (2, "9345678901", "contact.two@example.test", "vendor"),
            ],
        )
        connection.executemany(
            "INSERT INTO customer_data VALUES (?, ?, ?, ?)",
            [
                (1, "DEMOP0003C", "Aadhaar reference: 7777 7777 7777", 4),
                (2, "DEMOP0004D", "Aadhaar reference: 6666 6666 6666", 8),
            ],
        )
        connection.executemany(
            "INSERT INTO support_notes VALUES (?, ?, ?)",
            [
                (1, "Please contact demo.user@example.test or 9456789012 for a callback.", "support"),
                (2, "General product question with no personal data.", "product"),
            ],
        )
        connection.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?)",
            [
                (1, 499.0, "paid", "books"),
                (2, 1299.0, "shipped", "electronics"),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    return path


if __name__ == "__main__":
    created = create_demo_database()
    print(f"Created fake DPDP demo database: {created}")
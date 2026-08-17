-- Run this file while connected as a PostgreSQL administrator to the dpdp_demo database.
-- Replace INSERT_MATCH_THE_VALUE_IN_BACKEND_DOT_ENV before running it.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dpdp_scanner') THEN
        CREATE ROLE dpdp_scanner LOGIN PASSWORD 'this-is-pwd-lol';
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS public.users (
    id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    date_of_birth DATE,
    address TEXT,
    consent_status TEXT
);

CREATE TABLE IF NOT EXISTS public.employees (
    id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    pan_number TEXT NOT NULL,
    aadhaar_number TEXT NOT NULL,
    department TEXT,
    salary_band TEXT
);

CREATE TABLE IF NOT EXISTS public.contacts (
    id INTEGER PRIMARY KEY,
    primary_contact TEXT NOT NULL,
    secondary_contact TEXT NOT NULL,
    contact_kind TEXT
);

CREATE TABLE IF NOT EXISTS public.customer_data (
    id INTEGER PRIMARY KEY,
    identifier TEXT NOT NULL,
    misc_info TEXT,
    purchase_count INTEGER
);

CREATE TABLE IF NOT EXISTS public.orders (
    id INTEGER PRIMARY KEY,
    order_total NUMERIC(10, 2) NOT NULL,
    order_status TEXT NOT NULL,
    product_category TEXT NOT NULL
);

TRUNCATE TABLE public.users, public.employees, public.contacts, public.customer_data, public.orders;

INSERT INTO public.users VALUES
    (1, 'Ananya Rao', 'ananya.rao@example.test', '9876543210', '2003-04-12', '12 Demo Street, Bengaluru', 'granted'),
    (2, 'Ravi Kumar', 'ravi.kumar@example.test', '9123456789', '2002-11-05', '45 Sample Road, Pune', 'granted');

INSERT INTO public.employees VALUES
    (1, 'Demo Person One', 'DEMOP0001A', '9999 9999 9999', 'Engineering', 'B2'),
    (2, 'Demo Person Two', 'DEMOP0002B', '8888 8888 8888', 'Operations', 'B1');

INSERT INTO public.contacts VALUES
    (1, '9234567890', 'contact.one@example.test', 'customer'),
    (2, '9345678901', 'contact.two@example.test', 'vendor');

INSERT INTO public.customer_data VALUES
    (1, 'DEMOP0003C', 'Aadhaar reference: 7777 7777 7777', 4),
    (2, 'DEMOP0004D', 'Aadhaar reference: 6666 6666 6666', 8);

INSERT INTO public.orders VALUES
    (1, 499.00, 'paid', 'books'),
    (2, 1299.00, 'shipped', 'electronics');

-- Give the scanner account the minimum access necessary for this demo.
GRANT CONNECT ON DATABASE dpdp_demo TO dpdp_scanner;
GRANT USAGE ON SCHEMA public TO dpdp_scanner;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dpdp_scanner;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO dpdp_scanner;
ALTER ROLE dpdp_scanner SET default_transaction_read_only = on;
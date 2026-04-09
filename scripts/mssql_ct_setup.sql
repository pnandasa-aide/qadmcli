-- MSSQL Change Tracking Setup Script for Testing
-- Run this script on your MSSQL database to enable CT and create test tables

-- ============================================
-- 1. Enable Change Tracking on Database
-- ============================================
-- Check current CT status
SELECT 
    name AS database_name,
    is_change_tracking_on,
    retention_period,
    retention_period_units_desc
FROM sys.change_tracking_databases
WHERE database_id = DB_ID();

-- Enable CT on database (if not already enabled)
-- ALTER DATABASE [GSTargetDB] SET CHANGE_TRACKING = ON
-- (CHANGE_RETENTION = 2 DAYS, AUTO_CLEANUP = ON);

-- ============================================
-- 2. Create Test Table (Insurance Products)
-- ============================================
IF OBJECT_ID('dbo.INSURANCE_PRODUCTS', 'U') IS NOT NULL
    DROP TABLE dbo.INSURANCE_PRODUCTS;

CREATE TABLE dbo.INSURANCE_PRODUCTS (
    PRODUCT_ID INT IDENTITY(100, 1) PRIMARY KEY,
    PRODUCT_CODE NVARCHAR(20) NOT NULL,
    PRODUCT_NAME NVARCHAR(100) NOT NULL,
    PRODUCT_TYPE NVARCHAR(20) NOT NULL,
    BASE_PREMIUM DECIMAL(10, 2) NOT NULL,
    STATUS NVARCHAR(10) DEFAULT 'ACTIVE',
    CREATED_AT DATETIME2 DEFAULT GETDATE(),
    UPDATED_AT DATETIME2 DEFAULT GETDATE()
);

-- Enable Change Tracking on table
ALTER TABLE dbo.INSURANCE_PRODUCTS
ENABLE CHANGE_TRACKING
WITH (TRACK_COLUMNS_UPDATED = ON);

-- ============================================
-- 3. Create Child Table with FK (Subscriptions)
-- ============================================
IF OBJECT_ID('dbo.SUBSCRIPTIONS', 'U') IS NOT NULL
    DROP TABLE dbo.SUBSCRIPTIONS;

CREATE TABLE dbo.SUBSCRIPTIONS (
    SUBSCRIPTION_ID INT IDENTITY(1000, 1) PRIMARY KEY,
    PRODUCT_ID INT NOT NULL,
    CUST_ID INT NOT NULL,  -- Reference to external CUSTOMERS table
    START_DATE DATE NOT NULL,
    END_DATE DATE NOT NULL,
    PREMIUM_AMOUNT DECIMAL(10, 2) NOT NULL,
    STATUS NVARCHAR(20) DEFAULT 'PENDING',
    CREATED_AT DATETIME2 DEFAULT GETDATE(),
    CONSTRAINT FK_SUBSCRIPTIONS_PRODUCT FOREIGN KEY (PRODUCT_ID)
        REFERENCES dbo.INSURANCE_PRODUCTS(PRODUCT_ID)
);

-- Enable Change Tracking on table
ALTER TABLE dbo.SUBSCRIPTIONS
ENABLE CHANGE_TRACKING
WITH (TRACK_COLUMNS_UPDATED = ON);

-- ============================================
-- 4. Verify CT is Enabled
-- ============================================
SELECT 
    OBJECT_SCHEMA_NAME(object_id) AS schema_name,
    OBJECT_NAME(object_id) AS table_name,
    is_track_columns_updated_on
FROM sys.change_tracking_tables
WHERE object_id IN (
    OBJECT_ID('dbo.INSURANCE_PRODUCTS'),
    OBJECT_ID('dbo.SUBSCRIPTIONS')
);

-- ============================================
-- 5. Insert Test Data
-- ============================================
INSERT INTO dbo.INSURANCE_PRODUCTS (PRODUCT_CODE, PRODUCT_NAME, PRODUCT_TYPE, BASE_PREMIUM, STATUS)
VALUES 
    ('PROD1001', 'Life Insurance Premium', 'LIFE', 500.00, 'ACTIVE'),
    ('PROD1002', 'Health Insurance Basic', 'HEALTH', 300.00, 'ACTIVE'),
    ('PROD1003', 'Car Insurance Full', 'AUTO', 800.00, 'ACTIVE'),
    ('PROD1004', 'Home Insurance Standard', 'PROPERTY', 450.00, 'ACTIVE'),
    ('PROD1005', 'Life Insurance Basic', 'LIFE', 250.00, 'ACTIVE');

INSERT INTO dbo.SUBSCRIPTIONS (PRODUCT_ID, CUST_ID, START_DATE, END_DATE, PREMIUM_AMOUNT, STATUS)
VALUES 
    (100, 1001, '2025-04-01', '2026-04-01', 500.00, 'ACTIVE'),
    (101, 1002, '2025-04-05', '2026-04-05', 300.00, 'ACTIVE'),
    (102, 1003, '2025-04-10', '2026-04-10', 800.00, 'PENDING');

-- ============================================
-- 6. Test Change Tracking Queries
-- ============================================

-- Get current CT version
SELECT CHANGE_TRACKING_CURRENT_VERSION() AS current_version;

-- Get min valid version for tables
SELECT 
    'INSURANCE_PRODUCTS' AS table_name,
    CHANGE_TRACKING_MIN_VALID_VERSION(OBJECT_ID('dbo.INSURANCE_PRODUCTS')) AS min_version
UNION ALL
SELECT 
    'SUBSCRIPTIONS' AS table_name,
    CHANGE_TRACKING_MIN_VALID_VERSION(OBJECT_ID('dbo.SUBSCRIPTIONS')) AS min_version;

-- Query changes for INSURANCE_PRODUCTS (using version 0 to get all changes)
SELECT 
    c.SYS_CHANGE_VERSION,
    c.SYS_CHANGE_OPERATION,
    c.SYS_CHANGE_COLUMNS,
    c.SYS_CHANGE_CONTEXT,
    c.PRODUCT_ID
FROM CHANGETABLE(CHANGES dbo.INSURANCE_PRODUCTS, 0) c
ORDER BY c.SYS_CHANGE_VERSION;

-- Query changes with column tracking
SELECT 
    c.SYS_CHANGE_VERSION,
    c.SYS_CHANGE_OPERATION,
    c.SYS_CHANGE_COLUMNS,
    c.SYS_CHANGE_CONTEXT,
    c.PRODUCT_ID,
    p.PRODUCT_NAME,
    p.STATUS
FROM CHANGETABLE(CHANGES dbo.INSURANCE_PRODUCTS, 0) c
LEFT JOIN dbo.INSURANCE_PRODUCTS p ON c.PRODUCT_ID = p.PRODUCT_ID
ORDER BY c.SYS_CHANGE_VERSION;

-- ============================================
-- 7. Test Update/Delete to Generate More Changes
-- ============================================
-- Update a record
UPDATE dbo.INSURANCE_PRODUCTS 
SET STATUS = 'INACTIVE', UPDATED_AT = GETDATE()
WHERE PRODUCT_ID = 100;

-- Delete a record
DELETE FROM dbo.SUBSCRIPTIONS WHERE SUBSCRIPTION_ID = 1002;

-- Query changes again to see I/U/D operations
SELECT 
    c.SYS_CHANGE_VERSION,
    c.SYS_CHANGE_OPERATION,
    CASE c.SYS_CHANGE_OPERATION
        WHEN 'I' THEN 'INSERT'
        WHEN 'U' THEN 'UPDATE'
        WHEN 'D' THEN 'DELETE'
    END AS operation_type,
    c.SYS_CHANGE_COLUMNS,
    c.PRODUCT_ID
FROM CHANGETABLE(CHANGES dbo.INSURANCE_PRODUCTS, 0) c
ORDER BY c.SYS_CHANGE_VERSION;

PRINT 'Change Tracking setup complete!';

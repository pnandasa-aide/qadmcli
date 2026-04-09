-- MSSQL Change Tracking Setup - Simple Version for qadmcli
-- Run each section separately with: qadmcli sql execute -q "<SQL>" --target mssql

-- ============================================
-- STEP 1: Check CT status on database
-- ============================================
-- qadmcli sql execute -q "SELECT name, is_change_tracking_on FROM sys.databases WHERE name = DB_NAME()" --target mssql

-- ============================================
-- STEP 2: Create test table (INSURANCE_PRODUCTS)
-- ============================================
-- qadmcli sql execute -q "IF OBJECT_ID('dbo.INSURANCE_PRODUCTS', 'U') IS NOT NULL DROP TABLE dbo.INSURANCE_PRODUCTS; CREATE TABLE dbo.INSURANCE_PRODUCTS (PRODUCT_ID INT IDENTITY(100, 1) PRIMARY KEY, PRODUCT_CODE NVARCHAR(20) NOT NULL, PRODUCT_NAME NVARCHAR(100) NOT NULL, PRODUCT_TYPE NVARCHAR(20) NOT NULL, BASE_PREMIUM DECIMAL(10, 2) NOT NULL, STATUS NVARCHAR(10) DEFAULT 'ACTIVE', CREATED_AT DATETIME2 DEFAULT GETDATE(), UPDATED_AT DATETIME2 DEFAULT GETDATE())" --target mssql

-- ============================================
-- STEP 3: Enable CT on table
-- ============================================
-- qadmcli sql execute -q "ALTER TABLE dbo.INSURANCE_PRODUCTS ENABLE CHANGE_TRACKING WITH (TRACK_COLUMNS_UPDATED = ON)" --target mssql

-- ============================================
-- STEP 4: Insert test data
-- ============================================
-- qadmcli sql execute -q "INSERT INTO dbo.INSURANCE_PRODUCTS (PRODUCT_CODE, PRODUCT_NAME, PRODUCT_TYPE, BASE_PREMIUM, STATUS) VALUES ('PROD1001', 'Life Insurance Premium', 'LIFE', 500.00, 'ACTIVE'), ('PROD1002', 'Health Insurance Basic', 'HEALTH', 300.00, 'ACTIVE'), ('PROD1003', 'Car Insurance Full', 'AUTO', 800.00, 'ACTIVE'), ('PROD1004', 'Home Insurance Standard', 'PROPERTY', 450.00, 'ACTIVE'), ('PROD1005', 'Life Insurance Basic', 'LIFE', 250.00, 'ACTIVE')" --target mssql

-- ============================================
-- STEP 5: Verify CT is working
-- ============================================
-- qadmcli sql execute -q "SELECT CHANGE_TRACKING_CURRENT_VERSION() AS current_version" --target mssql

-- ============================================
-- STEP 6: Query changes
-- ============================================
-- qadmcli sql execute -q "SELECT c.SYS_CHANGE_VERSION, c.SYS_CHANGE_OPERATION, c.PRODUCT_ID FROM CHANGETABLE(CHANGES dbo.INSURANCE_PRODUCTS, 0) c ORDER BY c.SYS_CHANGE_VERSION" --target mssql

-- ============================================
-- STEP 7: Update a record (generates 'U' operation)
-- ============================================
-- qadmcli sql execute -q "UPDATE dbo.INSURANCE_PRODUCTS SET STATUS = 'INACTIVE', UPDATED_AT = GETDATE() WHERE PRODUCT_ID = 100" --target mssql

-- ============================================
-- STEP 8: Query changes again to see the update
-- ============================================
-- qadmcli sql execute -q "SELECT c.SYS_CHANGE_VERSION, c.SYS_CHANGE_OPERATION, CASE c.SYS_CHANGE_OPERATION WHEN 'I' THEN 'INSERT' WHEN 'U' THEN 'UPDATE' WHEN 'D' THEN 'DELETE' END AS operation_type, c.PRODUCT_ID FROM CHANGETABLE(CHANGES dbo.INSURANCE_PRODUCTS, 0) c ORDER BY c.SYS_CHANGE_VERSION" --target mssql

-- ============================================
-- All-in-one commands (for copy-paste)
-- ============================================

-- Drop and create table:
-- qadmcli sql execute -q "IF OBJECT_ID('dbo.INSURANCE_PRODUCTS', 'U') IS NOT NULL DROP TABLE dbo.INSURANCE_PRODUCTS; CREATE TABLE dbo.INSURANCE_PRODUCTS (PRODUCT_ID INT IDENTITY(100, 1) PRIMARY KEY, PRODUCT_CODE NVARCHAR(20) NOT NULL, PRODUCT_NAME NVARCHAR(100) NOT NULL, PRODUCT_TYPE NVARCHAR(20) NOT NULL, BASE_PREMIUM DECIMAL(10, 2) NOT NULL, STATUS NVARCHAR(10) DEFAULT 'ACTIVE', CREATED_AT DATETIME2 DEFAULT GETDATE(), UPDATED_AT DATETIME2 DEFAULT GETDATE())" --target mssql

-- Enable CT:
-- qadmcli sql execute -q "ALTER TABLE dbo.INSURANCE_PRODUCTS ENABLE CHANGE_TRACKING WITH (TRACK_COLUMNS_UPDATED = ON)" --target mssql

-- Insert data:
-- qadmcli sql execute -q "INSERT INTO dbo.INSURANCE_PRODUCTS (PRODUCT_CODE, PRODUCT_NAME, PRODUCT_TYPE, BASE_PREMIUM, STATUS) VALUES ('PROD1001', 'Life Insurance Premium', 'LIFE', 500.00, 'ACTIVE'), ('PROD1002', 'Health Insurance Basic', 'HEALTH', 300.00, 'ACTIVE'), ('PROD1003', 'Car Insurance Full', 'AUTO', 800.00, 'ACTIVE'), ('PROD1004', 'Home Insurance Standard', 'PROPERTY', 450.00, 'ACTIVE'), ('PROD1005', 'Life Insurance Basic', 'LIFE', 250.00, 'ACTIVE')" --target mssql

-- Check CT status using the new CLI command:
-- qadmcli mssql ct status -t INSURANCE_PRODUCTS -s dbo

-- Query changes using the new CLI command:
-- qadmcli mssql ct changes -t INSURANCE_PRODUCTS -s dbo --since-version 0

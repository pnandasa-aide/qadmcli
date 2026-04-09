# Insurance Domain Schema

This document describes a complete insurance domain schema for AS400 DB2 for i, including customers, products, subscriptions, payments, and claims.

## Schema Overview

```
┌─────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  CUSTOMERS  │◄────┤    SUBSCRIPTIONS    │────►│ INSURANCE_PRODUCTS│
│  (existing) │ 1:M │  (SUBSC00001)       │ M:1 │   (INSUR00001)   │
└─────────────┘     └──────────┬──────────┘     └──────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
              ┌─────▼─────┐         ┌────▼────┐
              │  PAYMENTS │         │  CLAIMS │
              │ (PAYMENTS)│         │ (CLAIMS)│
              └───────────┘         └────┬────┘
                                         │
                                    ┌────▼─────────┐
                                    │CLAIM_DOCUMENTS│
                                    │ (CLAIM00001) │
                                    └───────────────┘
```

## Table Definitions

### 1. CUSTOMERS (Enhanced)

Existing table with added Thai name support:

```sql
ALTER TABLE GSLIBTST.CUSTOMERS 
ADD COLUMN THAI_FIRST_NAME VARCHAR(100) CCSID 838;

ALTER TABLE GSLIBTST.CUSTOMERS 
ADD COLUMN THAI_LAST_NAME VARCHAR(100) CCSID 838;
```

**Columns:**
| Column | Type | Description |
|--------|------|-------------|
| CUST_ID | INTEGER PK | Customer ID (auto-generated) |
| FIRST_NAME | VARCHAR(50) | English first name |
| LAST_NAME | VARCHAR(50) | English last name |
| THAI_FIRST_NAME | VARCHAR(100) CCSID 838 | Thai first name |
| THAI_LAST_NAME | VARCHAR(100) CCSID 838 | Thai last name |
| EMAIL | VARCHAR(100) | Email address |
| PHONE | VARCHAR(20) | Phone number |
| CREATED_AT | TIMESTAMP | Creation timestamp |

### 2. INSURANCE_PRODUCTS (INSUR00001)

Master table for insurance products:

```bash
# Create using SQL
qadmcli sql execute -q "CREATE TABLE GSLIBTST.INSURANCE_PRODUCTS (
    PRODUCT_ID INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    PRODUCT_CODE VARCHAR(20) NOT NULL UNIQUE,
    PRODUCT_NAME VARCHAR(100) NOT NULL,
    PRODUCT_TYPE VARCHAR(30) CHECK (PRODUCT_TYPE IN ('HEALTH', 'LIFE', 'AUTO', 'HOME', 'TRAVEL')),
    PREMIUM_BASE DECIMAL(15,2) NOT NULL,
    COVERAGE_AMOUNT DECIMAL(15,2) NOT NULL,
    DURATION_MONTHS INTEGER NOT NULL,
    IS_ACTIVE CHAR(1) DEFAULT 'Y',
    CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)"
```

**Columns:**
| Column | Type | Description |
|--------|------|-------------|
| PRODUCT_ID | INTEGER PK | Product ID (auto-generated) |
| PRODUCT_CODE | VARCHAR(20) | Unique product code (e.g., "HLTH-001") |
| PRODUCT_NAME | VARCHAR(100) | Product name |
| PRODUCT_TYPE | VARCHAR(30) | HEALTH, LIFE, AUTO, HOME, TRAVEL |
| PREMIUM_BASE | DECIMAL(15,2) | Base premium amount |
| COVERAGE_AMOUNT | DECIMAL(15,2) | Maximum coverage |
| DURATION_MONTHS | INTEGER | Policy duration |
| IS_ACTIVE | CHAR(1) | Y/N flag |
| CREATED_AT | TIMESTAMP | Creation timestamp |

### 3. SUBSCRIPTIONS (SUBSC00001)

Customer subscriptions to insurance products:

```bash
qadmcli sql execute -q "CREATE TABLE GSLIBTST.SUBSCRIPTIONS (
    SUBSCRIPTION_ID INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    CUST_ID INTEGER NOT NULL,
    PRODUCT_ID INTEGER NOT NULL,
    POLICY_NUMBER VARCHAR(30) NOT NULL UNIQUE,
    START_DATE DATE NOT NULL,
    END_DATE DATE NOT NULL,
    PREMIUM_AMOUNT DECIMAL(15,2) NOT NULL,
    PAYMENT_FREQUENCY VARCHAR(10) CHECK (PAYMENT_FREQUENCY IN ('MONTHLY', 'QUARTERLY', 'YEARLY')),
    STATUS VARCHAR(20) DEFAULT 'PENDING' CHECK (STATUS IN ('ACTIVE', 'EXPIRED', 'CANCELLED', 'PENDING')),
    CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UPDATED_AT TIMESTAMP
)"
```

### 4. PAYMENTS

Payment records for subscriptions:

```bash
qadmcli sql execute -q "CREATE TABLE GSLIBTST.PAYMENTS (
    PAYMENT_ID INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    SUBSCRIPTION_ID INTEGER NOT NULL,
    PAYMENT_DATE DATE,
    DUE_DATE DATE NOT NULL,
    AMOUNT DECIMAL(15,2) NOT NULL,
    PAYMENT_METHOD VARCHAR(20) CHECK (PAYMENT_METHOD IN ('CREDIT_CARD', 'BANK_TRANSFER', 'CASH')),
    TRANSACTION_REF VARCHAR(50),
    STATUS VARCHAR(20) DEFAULT 'PENDING' CHECK (STATUS IN ('PAID', 'PENDING', 'FAILED', 'REFUNDED')),
    CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)"
```

### 5. CLAIMS

Insurance claims filed by customers:

```bash
qadmcli sql execute -q "CREATE TABLE GSLIBTST.CLAIMS (
    CLAIM_ID INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    SUBSCRIPTION_ID INTEGER NOT NULL,
    CLAIM_NUMBER VARCHAR(30) NOT NULL UNIQUE,
    CLAIM_DATE DATE NOT NULL,
    INCIDENT_DATE DATE,
    CLAIM_TYPE VARCHAR(30) CHECK (CLAIM_TYPE IN ('MEDICAL', 'ACCIDENT', 'THEFT', 'DAMAGE')),
    DESCRIPTION VARCHAR(500),
    CLAIM_AMOUNT DECIMAL(15,2) NOT NULL,
    APPROVED_AMOUNT DECIMAL(15,2),
    STATUS VARCHAR(20) DEFAULT 'PENDING' CHECK (STATUS IN ('PENDING', 'APPROVED', 'REJECTED', 'SETTLED')),
    SETTLED_DATE DATE,
    CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UPDATED_AT TIMESTAMP
)"
```

### 6. CLAIM_DOCUMENTS (CLAIM00001)

Supporting documents for claims:

```bash
qadmcli sql execute -q "CREATE TABLE GSLIBTST.CLAIM_DOCUMENTS (
    DOC_ID INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    CLAIM_ID INTEGER NOT NULL,
    DOC_TYPE VARCHAR(30) CHECK (DOC_TYPE IN ('RECEIPT', 'REPORT', 'PHOTO', 'CERTIFICATE')),
    DOC_NAME VARCHAR(100) NOT NULL,
    FILE_PATH VARCHAR(500),
    UPLOADED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)"
```

## Post-Creation Setup

### Enable Journaling

All tables are automatically journaled when created in a library with an active journal:

```bash
# Verify journaling status
qadmcli table check -n INSURANCE_PRODUCTS -l GSLIBTST
qadmcli table check -n SUBSCRIPTIONS -l GSLIBTST
qadmcli table check -n PAYMENTS -l GSLIBTST
qadmcli table check -n CLAIMS -l GSLIBTST
qadmcli table check -n CLAIM_DOCUMENTS -l GSLIBTST
```

### Grant Permissions

```bash
# Grant all privileges to USER001
qadmcli sql execute -q "GRANT ALL PRIVILEGES ON GSLIBTST.INSURANCE_PRODUCTS TO USER001"
qadmcli sql execute -q "GRANT ALL PRIVILEGES ON GSLIBTST.SUBSCRIPTIONS TO USER001"
qadmcli sql execute -q "GRANT ALL PRIVILEGES ON GSLIBTST.PAYMENTS TO USER001"
qadmcli sql execute -q "GRANT ALL PRIVILEGES ON GSLIBTST.CLAIMS TO USER001"
qadmcli sql execute -q "GRANT ALL PRIVILEGES ON GSLIBTST.CLAIM_DOCUMENTS TO USER001"
```

## SQL Names vs System Names

IBM i DB2 truncates long SQL names to 10-character system names. QADMCLI auto-resolves SQL names:

```bash
# Both commands work for the same table:
qadmcli table check -n INSURANCE_PRODUCTS -l GSLIBTST   # SQL name
qadmcli table check -n INSUR00001 -l GSLIBTST           # System name

# Output shows both names:
# Table: GSLIBTST.INSURANCE_PRODUCTS
# System Name: INSUR00001
# SQL Name: INSURANCE_PRODUCTS
```

**Mapping:**
| SQL Name | System Name |
|----------|-------------|
| INSURANCE_PRODUCTS | INSUR00001 |
| SUBSCRIPTIONS | SUBSC00001 |
| CLAIM_DOCUMENTS | CLAIM00001 |
| PAYMENTS | PAYMENTS |
| CLAIMS | CLAIMS |

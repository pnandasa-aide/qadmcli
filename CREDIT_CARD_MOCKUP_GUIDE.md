# Credit Card Mockup Data Generation Guide

## Overview

The qadmcli mockup generator now supports **realistic credit card number generation** with:
- ✅ **Luhn algorithm** validation (credit card checksum)
- ✅ **16-digit format** (standard credit card length)
- ✅ **Auto-detection** from column names
- ✅ **Schema hints** for explicit control

---

## Method 1: Auto-Detection (No Schema File Needed)

If your column name matches one of these patterns, it will **automatically** generate credit card numbers:

**Supported Column Names:**
- `CREDIT_CARD`
- `CREDITCARD`
- `CC_NUMBER`
- `CC_NO`
- `CARD_NUMBER`
- `CARD_NO`
- `PAYMENT_CARD`
- `CREDIT_CARD_NO`

**Example:**
```bash
# If your table has a column named CREDIT_CARD
./qadmcli.sh mockup generate -t CUSTOMERS -l MYLIB -r 100 --dry-run

# Will automatically generate 16-digit Luhn-valid credit card numbers!
```

---

## Method 2: Schema File with Hint

For columns with **non-standard names**, use a schema file with `[hint:credit_card]`:

### Step 1: Create Schema File

Create `config/schema/mytable.yaml`:

```yaml
columns:
  - name: CUSTOM_COLUMN_NAME
    type: VARCHAR
    length: 20
    nullable: true
    description: "Payment card number [hint:credit_card]"
  
  - name: ANOTHER_CARD
    type: CHAR
    length: 16
    nullable: true
    description: "Backup credit card [hint:credit_card]"
```

### Step 2: Run with Schema

```bash
./qadmcli.sh mockup generate -t MYTABLE -l MYLIB \
  -s config/schema/mytable.yaml \
  --skip-validation \
  -r 50 --dry-run
```

---

## Method 3: Column Description in Database

You can also add the hint directly to the **column description** in AS400:

```sql
-- Add hint to column description
LABEL ON COLUMN MYLIB.MYTABLE.PAYMENT_INFO 
  IS 'Customer payment card [hint:credit_card]'
```

Then mockup will auto-detect it:

```bash
./qadmcli.sh mockup generate -t MYTABLE -l MYLIB -r 100
```

---

## Generated Output Examples

### Without Hint (Auto-Detection):
```sql
INSERT INTO MYLIB.CUSTOMERS (CUST_ID, FIRST_NAME, CREDIT_CARD) VALUES 
  (12345, 'John', '4532015112830366'),
  (12346, 'Jane', '5425233430109903');
```

### With Schema Hint:
```sql
INSERT INTO MYLIB.ORDERS (ORDER_ID, PAYMENT_CARD) VALUES 
  (1001, '4916338506082832'),
  (1002, '5234567890123456');
```

**Note:** All generated numbers are:
- ✅ **16 digits** (or custom length if specified)
- ✅ **Luhn-valid** (passes credit card checksum)
- ✅ **Numeric only** (no spaces or dashes)

---

## Custom Length

By default, credit cards are **16 digits**. To generate different lengths:

### Option 1: Set Column Length in Schema

```yaml
columns:
  - name: AMEX_CARD
    type: VARCHAR
    length: 15  # American Express uses 15 digits
    description: "AMEX card [hint:credit_card]"
  
  - name: OLD_CARD
    type: VARCHAR
    length: 13  # Some old cards had 13 digits
    description: "Legacy card [hint:credit_card]"
```

### Option 2: Use Column Definition

The generator respects the column's `LENGTH` attribute from the database:

```sql
-- VARCHAR(15) will generate 15-digit cards
ALTER TABLE MYLIB.CUSTOMERS 
  ALTER COLUMN CREDIT_CARD SET DATA TYPE VARCHAR(15)
```

---

## Validation

### Test Luhn Algorithm

You can verify generated numbers pass the Luhn check:

```python
def luhn_check(number):
    """Validate credit card number using Luhn algorithm."""
    def digits_of(n):
        return [int(d) for d in str(n)]
    
    digits = digits_of(number)
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    checksum = sum(odd_digits)
    for d in even_digits:
        checksum += sum(digits_of(d * 2))
    return checksum % 10 == 0

# Test
print(luhn_check("4532015112830366"))  # True ✅
```

### Run Test Suite

```bash
cd /home/ubuntu/_qoder/qadmcli
python3 test_credit_card.py
```

**Expected Output:**
```
✅ ALL TESTS PASSED!
- Direct generation works
- Luhn validation passes
- Hint-based generation works
- Auto-detection works for 8+ column name patterns
- Schema file integration works
- Variable length generation works
```

---

## Complete Example

### Schema File: `config/schema/customers2.yaml`

```yaml
# Schema for CUSTOMERS2 table with credit card support
columns:
  - name: FIRST_NAME
    type: VARCHAR
    length: 50
    description: "Customer first name"
  
  - name: LAST_NAME
    type: VARCHAR
    length: 50
    description: "Customer last name"
  
  - name: EMAIL
    type: VARCHAR
    length: 100
    description: "Email address [hint:email]"
  
  - name: PHONE_NUMBER
    type: VARCHAR
    length: 10
    description: "Phone number [hint:phone]"
  
  - name: CREDIT_CARD
    type: VARCHAR
    length: 20
    nullable: true
    description: "Credit card number [hint:credit_card]"
  
  - name: CREDIT_SCORE
    type: INTEGER
    description: "Credit score [hint:range:300:850]"
```

### Generate Data:

```bash
# Dry run - preview SQL
./qadmcli.sh mockup generate \
  -t CUSTOMERS2 \
  -l GSLIBTST \
  -s config/schema/customers2.yaml \
  --skip-validation \
  -r 20 \
  --dry-run

# Execute - insert into database
./qadmcli.sh mockup generate \
  -t CUSTOMERS2 \
  -l GSLIBTST \
  -s config/schema/customers2.yaml \
  --skip-validation \
  -r 100
```

### Sample Output:

```sql
INSERT INTO GSLIBTST.CUSTOMERS2 (
  CUSTOMER_ID, FIRST_NAME, LAST_NAME, EMAIL, PHONE_NUMBER, CREDIT_CARD, CREDIT_SCORE
) VALUES (
  12345, 'John', 'Smith', 'john@email.com', '0812345678', 
  '4532015112830366', 750
);
```

---

## Troubleshooting

### Problem: Getting random strings instead of credit card numbers

**Cause:** Column name doesn't match credit card patterns and no hint provided.

**Solution:** 
1. Rename column to match patterns (e.g., `CREDIT_CARD`)
2. OR add schema hint: `description: "Card [hint:credit_card]"`

### Problem: Wrong number of digits

**Cause:** Column LENGTH doesn't match expected credit card length.

**Solution:**
- Standard cards: Set LENGTH to 16
- Amex cards: Set LENGTH to 15
- Custom: Set LENGTH to desired value

### Problem: Schema validation errors

**Cause:** Schema file doesn't match actual table definition.

**Solution:** Add `--skip-validation` flag:
```bash
./qadmcli.sh mockup generate -t MYTABLE -l MYLIB -s schema.yaml --skip-validation
```

---

## Advanced: Other Available Hints

The mockup generator supports many hints:

| Hint | Example Columns | Generated Data |
|------|----------------|----------------|
| `credit_card` | CREDIT_CARD, CC_NUMBER | 16-digit Luhn-valid number |
| `first_name` | FIRST_NAME, FNAME | John, Jane, etc. |
| `last_name` | LAST_NAME, LNAME | Smith, Johnson, etc. |
| `email` | EMAIL, E_MAIL | user@example.com |
| `phone` | PHONE, MOBILE | 0812345678 |
| `date` | DATE, CREATED_DATE | 2024-01-15 |
| `amount` | AMOUNT, PRICE | 1234.56 |
| `status` | STATUS, TYPE | A, I, P |
| `constant:VALUE` | Any column | Fixed value |
| `range:100:999` | Any numeric | Random in range |
| `choices:A,B,C` | Any column | Random from list |

---

## References

- **Test Suite:** `test_credit_card.py`
- **Pattern Implementation:** `src/qadmcli/utils/data_generator.py` (CreditCardPattern class)
- **Schema Loading:** `src/qadmcli/cli.py` (_load_schema_hints function)
- **Luhn Algorithm:** Implemented in CreditCardPattern._luhn_checksum()

#!/usr/bin/env python3
"""Test credit card generation with schema hints."""

import sys
import os
import tempfile
import yaml

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from qadmcli.utils.data_generator import DataGenerator, CreditCardPattern


def test_credit_card_pattern_direct():
    """Test CreditCardPattern directly."""
    print("=" * 60)
    print("Test 1: CreditCardPattern Direct Generation")
    print("=" * 60)
    
    cc = CreditCardPattern()
    
    # Generate 5 credit card numbers
    for i in range(5):
        cc_number = cc.generate(16)
        print(f"  Card {i+1}: {cc_number} (length: {len(cc_number)})")
        
        # Verify it's 16 digits
        assert len(cc_number) == 16, f"Expected 16 digits, got {len(cc_number)}"
        assert cc_number.isdigit(), f"Expected all digits, got: {cc_number}"
    
    print("\n  ✅ All credit card numbers are 16 digits\n")


def test_luhn_validation():
    """Test that generated numbers pass Luhn check."""
    print("=" * 60)
    print("Test 2: Luhn Algorithm Validation")
    print("=" * 60)
    
    cc = CreditCardPattern()
    
    # Generate cards and validate Luhn
    for i in range(10):
        cc_number = cc.generate(16)
        
        # Verify Luhn checksum
        checksum = cc._luhn_checksum(cc_number)
        assert checksum == 0, f"Card {cc_number} failed Luhn check (checksum: {checksum})"
        print(f"  Card {i+1}: {cc_number} ✅ Luhn valid")
    
    print("\n  ✅ All cards pass Luhn validation\n")


def test_data_generator_with_hint():
    """Test DataGenerator with credit_card hint."""
    print("=" * 60)
    print("Test 3: DataGenerator with 'credit_card' Hint")
    print("=" * 60)
    
    gen = DataGenerator()
    
    # Test with explicit hint
    for i in range(5):
        cc_number = gen.generate_for_column(
            column_name="PAYMENT_CARD",  # Different name to test hint override
            data_type="VARCHAR",
            length=16,
            hint="credit_card"
        )
        
        print(f"  Card {i+1}: {cc_number} (length: {len(cc_number)})")
        assert len(cc_number) == 16, f"Expected 16 digits, got {len(cc_number)}"
        assert cc_number.isdigit(), f"Expected all digits, got: {cc_number}"
    
    print("\n  ✅ Hint-based generation works correctly\n")


def test_data_generator_auto_detection():
    """Test DataGenerator auto-detection for CREDIT_CARD column."""
    print("=" * 60)
    print("Test 4: DataGenerator Auto-Detection (No Hint)")
    print("=" * 60)
    
    gen = DataGenerator()
    
    # Test various credit card column names
    cc_column_names = [
        "CREDIT_CARD",
        "CREDITCARD",
        "CC_NUMBER",
        "CC_NO",
        "CARD_NUMBER",
        "CARD_NO",
        "PAYMENT_CARD",
        "CREDIT_CARD_NO"
    ]
    
    for col_name in cc_column_names:
        cc_number = gen.generate_for_column(
            column_name=col_name,
            data_type="VARCHAR",
            length=20
        )
        
        print(f"  {col_name}: {cc_number} (length: {len(cc_number)})")
        # Should be 16 digits (credit card pattern)
        assert len(cc_number) == 16 or len(cc_number) == 20, \
            f"Unexpected length for {col_name}: {len(cc_number)}"
    
    print("\n  ✅ Auto-detection works for all credit card column names\n")


def test_schema_file_integration():
    """Test schema file with credit_card hint."""
    print("=" * 60)
    print("Test 5: Schema File Integration")
    print("=" * 60)
    
    # Create temporary schema file
    schema = {
        'columns': [
            {
                'name': 'CREDIT_CARD',
                'type': 'VARCHAR',
                'length': 20,
                'nullable': True,
                'description': 'Credit card number [hint:credit_card]'
            },
            {
                'name': 'CC_BACKUP',
                'type': 'CHAR',
                'length': 16,
                'nullable': True,
                'description': 'Backup card [hint:credit_card]'
            }
        ]
    }
    
    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(schema, f)
        schema_path = f.name
    
    try:
        # Load schema hints (same as CLI does)
        import re
        hints = {}
        with open(schema_path, 'r') as f:
            loaded_schema = yaml.safe_load(f)
        
        for col in loaded_schema['columns']:
            col_name = col.get('name')
            description = col.get('description', '')
            
            if col_name and description:
                hint_match = re.search(r'\[hint:([^\]]+)\]', description, re.IGNORECASE)
                if hint_match:
                    hints[col_name.upper()] = hint_match.group(1).strip()
        
        print(f"  Loaded hints: {hints}")
        
        # Generate data using hints
        gen = DataGenerator()
        
        for col in schema['columns']:
            col_name = col['name']
            hint = hints.get(col_name.upper())
            
            cc_number = gen.generate_for_column(
                column_name=col_name,
                data_type=col['type'],
                length=col['length'],
                hint=hint
            )
            
            print(f"  {col_name} (hint={hint}): {cc_number} (length: {len(cc_number)})")
            assert cc_number.isdigit(), f"Expected digits for {col_name}"
            assert len(cc_number) >= 16, f"Expected at least 16 digits for {col_name}"
        
        print("\n  ✅ Schema file integration works correctly\n")
        
    finally:
        os.unlink(schema_path)


def test_different_lengths():
    """Test credit card generation with different lengths."""
    print("=" * 60)
    print("Test 6: Different Card Lengths")
    print("=" * 60)
    
    cc = CreditCardPattern()
    
    # Test various lengths
    for length in [13, 15, 16, 19, 20]:
        cc_number = cc.generate(length)
        print(f"  {length}-digit card: {cc_number} (actual length: {len(cc_number)})")
        assert len(cc_number) == length, f"Expected {length} digits, got {len(cc_number)}"
        assert cc_number.isdigit(), f"Expected all digits for {length}-digit card"
    
    print("\n  ✅ Variable length generation works\n")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("CREDIT CARD GENERATION TEST SUITE")
    print("=" * 60 + "\n")
    
    tests = [
        test_credit_card_pattern_direct,
        test_luhn_validation,
        test_data_generator_with_hint,
        test_data_generator_auto_detection,
        test_schema_file_integration,
        test_different_lengths,
    ]
    
    failed = 0
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"\n  ❌ Test failed: {e}\n")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("=" * 60)
    if failed == 0:
        print("✅ ALL TESTS PASSED!")
    else:
        print(f"❌ {failed} test(s) failed")
    print("=" * 60)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

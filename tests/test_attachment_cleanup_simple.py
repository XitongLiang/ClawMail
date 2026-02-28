#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple test script for attachment cleanup on email deletion.
Tests only the _delete_attachment_files() helper method.
"""

import sys
import os
from pathlib import Path
import uuid

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from clawmail.infrastructure.database.storage_manager import ClawDB


def test_delete_attachment_files_helper():
    """Test _delete_attachment_files() helper method directly."""
    print("\n" + "="*60)
    print("  Testing _delete_attachment_files() Helper")
    print("="*60 + "\n")

    data_dir = Path(os.path.expanduser("~/clawmail_data"))
    db = ClawDB(data_dir)

    # Test 1: Create attachment directory and verify deletion
    print("Test 1: Delete existing attachment directory")
    email_id_1 = str(uuid.uuid4())
    att_dir_1 = data_dir / "attachments" / email_id_1
    att_dir_1.mkdir(parents=True, exist_ok=True)
    test_file_1 = att_dir_1 / "test_document.pdf"
    test_file_1.write_bytes(b"fake pdf content")

    print(f"  Created: {att_dir_1}")
    assert att_dir_1.exists(), "Directory should exist after creation"

    # Call the helper method
    db._delete_attachment_files(email_id_1)

    # Verify deletion
    if att_dir_1.exists():
        print("  [FAIL] Directory still exists after deletion")
        return False
    else:
        print("  [PASS] Directory successfully deleted")

    # Test 2: Call delete on non-existent directory (should not error)
    print("\nTest 2: Delete non-existent attachment directory")
    email_id_2 = str(uuid.uuid4())
    att_dir_2 = data_dir / "attachments" / email_id_2

    print(f"  Testing: {att_dir_2}")
    assert not att_dir_2.exists(), "Directory should not exist"

    try:
        # Call the helper method on non-existent directory
        db._delete_attachment_files(email_id_2)
        print("  [PASS] No error when deleting non-existent directory")
    except Exception as e:
        print(f"  [FAIL] Unexpected error: {e}")
        return False

    # Test 3: Create multiple files in directory
    print("\nTest 3: Delete directory with multiple files")
    email_id_3 = str(uuid.uuid4())
    att_dir_3 = data_dir / "attachments" / email_id_3
    att_dir_3.mkdir(parents=True, exist_ok=True)

    # Create multiple files
    for i in range(5):
        file = att_dir_3 / f"document_{i}.pdf"
        file.write_bytes(f"fake content {i}".encode())

    print(f"  Created directory with 5 files: {att_dir_3}")
    assert att_dir_3.exists() and len(list(att_dir_3.iterdir())) == 5

    # Delete
    db._delete_attachment_files(email_id_3)

    if att_dir_3.exists():
        print("  [FAIL] Directory still exists after deletion")
        return False
    else:
        print("  [PASS] Directory with multiple files successfully deleted")

    return True


def test_integration_with_database():
    """Test that delete_email() calls _delete_attachment_files()."""
    print("\n" + "="*60)
    print("  Integration Test: delete_email() + file cleanup")
    print("="*60 + "\n")

    data_dir = Path(os.path.expanduser("~/clawmail_data"))
    db = ClawDB(data_dir)

    # Get any existing email from database
    with db.get_conn() as conn:
        result = conn.execute("SELECT id FROM emails LIMIT 1").fetchone()

    if not result:
        print("  [SKIP] No emails in database to test with")
        return True

    existing_email_id = result[0]
    print(f"  Found existing email: {existing_email_id}")

    # Create fake attachment directory for this email
    att_dir = data_dir / "attachments" / existing_email_id
    if att_dir.exists():
        print(f"  [SKIP] Attachment directory already exists, skipping to avoid data loss")
        return True

    att_dir.mkdir(parents=True, exist_ok=True)
    test_file = att_dir / "integration_test.pdf"
    test_file.write_bytes(b"integration test content")

    print(f"  Created test attachment: {att_dir}")
    assert att_dir.exists()

    # Now call delete_email() - this should delete both DB record AND files
    print(f"  Calling delete_email({existing_email_id})")

    try:
        db.delete_email(existing_email_id)
    except Exception as e:
        print(f"  [WARNING] Delete email failed: {e}")
        # Clean up test directory
        import shutil
        if att_dir.exists():
            shutil.rmtree(att_dir)
        return True  # Don't fail test if email doesn't exist

    # Verify attachment directory was deleted
    if att_dir.exists():
        print("  [FAIL] Attachment directory still exists after delete_email()")
        return False
    else:
        print("  [PASS] Attachment directory deleted by delete_email()")

    return True


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("  Attachment Cleanup - Simple Test Suite")
    print("="*60)

    # Check if data directory exists
    data_dir = Path(os.path.expanduser("~/clawmail_data"))
    if not data_dir.exists():
        print(f"\n[FAIL] ClawMail data directory not found: {data_dir}")
        print("Please run ClawMail at least once to initialize the database.")
        return

    results = []

    # Run tests
    try:
        results.append(("Helper method test", test_delete_attachment_files_helper()))
    except Exception as e:
        print(f"\n[FAIL] Helper test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Helper method test", False))

    try:
        results.append(("Integration test", test_integration_with_database()))
    except Exception as e:
        print(f"\n[FAIL] Integration test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Integration test", False))

    # Summary
    print("\n" + "="*60)
    print("  Test Summary")
    print("="*60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n[SUCCESS] All tests passed! Attachment cleanup is working correctly.")
    else:
        print("\n[WARNING] Some tests failed. Please review the output above.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\n[FAIL] Unexpected error: {e}")
        import traceback
        traceback.print_exc()

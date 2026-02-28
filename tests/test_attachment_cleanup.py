#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for attachment cleanup on email deletion.
Verifies that attachment files are deleted from disk when emails are permanently deleted.
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from clawmail.infrastructure.database.storage_manager import ClawDB
from clawmail.domain.models.email import Email
import uuid


def test_single_email_with_attachment_deletion():
    """Test 1: Single email deletion removes attachment directory."""
    print("\n" + "="*60)
    print("TEST 1: Single Email with Attachment Deletion")
    print("="*60)

    data_dir = Path(os.path.expanduser("~/clawmail_data"))
    db = ClawDB(data_dir)

    # Get any account for testing
    accounts = db.get_all_accounts()
    if not accounts:
        print("[FAIL] No accounts found in database. Please add an account first.")
        return False

    test_account = accounts[0]
    print(f"[OK] Using account: {test_account.email_address}")

    # Create test email
    email_id = str(uuid.uuid4())
    email = Email(
        id=email_id,
        account_id=test_account.id,
        message_id=f"<{uuid.uuid4()}@test.com>",
        thread_id=f"thread_{uuid.uuid4()}",
        from_address={"name": "Test Sender", "email": "test@example.com"},
        to_addresses=[{"name": "", "email": test_account.email_address}],
        subject="Test Email with Attachment",
        body_text="This email has attachments for testing.",
        received_at=datetime.utcnow(),
        folder="INBOX"
    )

    db.save_email(email)
    print(f"[OK] Created test email: {email_id}")

    # Create fake attachment directory and file
    att_dir = Path(data_dir) / "attachments" / email_id
    att_dir.mkdir(parents=True, exist_ok=True)
    test_file = att_dir / "test_document.pdf"
    test_file.write_bytes(b"fake pdf content for testing")

    print(f"[OK] Created attachment directory: {att_dir}")
    print(f"[OK] Created test file: test_document.pdf")

    # Verify file exists
    if not att_dir.exists():
        print("[FAIL] FAIL: Attachment directory was not created")
        return False

    # Delete email
    print(f"\n[DELETE]  Deleting email: {email_id}")
    db.delete_email(email_id)

    # Verify attachment directory is deleted
    if att_dir.exists():
        print(f"[FAIL] FAIL: Attachment directory still exists: {att_dir}")
        return False

    print(f"[OK] PASS: Attachment directory successfully deleted")
    print(f"[OK] PASS: Email and attachments cleaned up properly")
    return True


def test_email_without_attachments():
    """Test 2: Email without attachments doesn't cause errors."""
    print("\n" + "="*60)
    print("TEST 2: Email Without Attachments")
    print("="*60)

    data_dir = Path(os.path.expanduser("~/clawmail_data"))
    db = ClawDB(data_dir)

    # Get any account for testing
    accounts = db.get_all_accounts()
    if not accounts:
        print("[FAIL] No accounts found in database. Please add an account first.")
        return False

    test_account = accounts[0]
    print(f"[OK] Using account: {test_account.email_address}")

    # Create test email WITHOUT attachments
    email_id = str(uuid.uuid4())
    email = Email(
        id=email_id,
        account_id=test_account.id,
        message_id=f"<{uuid.uuid4()}@test.com>",
        thread_id=f"thread_{uuid.uuid4()}",
        from_address={"name": "Test Sender", "email": "test@example.com"},
        to_addresses=[{"name": "", "email": test_account.email_address}],
        subject="Test Email WITHOUT Attachment",
        body_text="This email has no attachments.",
        received_at=datetime.utcnow(),
        folder="INBOX"
    )

    db.save_email(email)
    print(f"[OK] Created test email (no attachments): {email_id}")

    # Delete email (should not cause errors even though no attachment dir exists)
    try:
        print(f"\n[DELETE]  Deleting email: {email_id}")
        db.delete_email(email_id)
        print(f"[OK] PASS: Email deleted without errors")
        return True
    except Exception as e:
        print(f"[FAIL] FAIL: Deletion caused error: {e}")
        return False


def test_bulk_deletion_with_attachments():
    """Test 3: Bulk deletion removes all attachment directories."""
    print("\n" + "="*60)
    print("TEST 3: Bulk Deletion with Multiple Attachments")
    print("="*60)

    data_dir = Path(os.path.expanduser("~/clawmail_data"))
    db = ClawDB(data_dir)

    # Get any account for testing
    accounts = db.get_all_accounts()
    if not accounts:
        print("[FAIL] No accounts found in database. Please add an account first.")
        return False

    test_account = accounts[0]
    print(f"[OK] Using account: {test_account.email_address}")

    # Create 3 test emails with attachments
    email_ids = []
    att_dirs = []

    for i in range(3):
        email_id = str(uuid.uuid4())
        email_ids.append(email_id)

        email = Email(
            id=email_id,
            account_id=test_account.id,
            message_id=f"<{uuid.uuid4()}@test.com>",
            thread_id=f"thread_{uuid.uuid4()}",
            from_address={"name": "Test Sender", "email": "test@example.com"},
            to_addresses=[{"name": "", "email": test_account.email_address}],
            subject=f"Bulk Test Email {i+1}",
            body_text=f"This is test email {i+1}.",
            received_at=datetime.utcnow(),
            folder="INBOX"
        )

        db.save_email(email)

        # Create attachment directory
        att_dir = Path(data_dir) / "attachments" / email_id
        att_dir.mkdir(parents=True, exist_ok=True)
        test_file = att_dir / f"document_{i+1}.pdf"
        test_file.write_bytes(b"fake pdf content")
        att_dirs.append(att_dir)

        print(f"[OK] Created email {i+1} with attachment: {email_id[:8]}...")

    # Verify all directories exist
    for att_dir in att_dirs:
        if not att_dir.exists():
            print(f"[FAIL] FAIL: Directory not created: {att_dir}")
            return False

    print(f"\n[OK] All {len(att_dirs)} attachment directories created")

    # Delete all emails for test account
    print(f"\n[DELETE]  Deleting all emails for test account...")
    deleted_count = db.delete_all_emails(account_id=test_account.id)
    print(f"[OK] Deleted {deleted_count} emails")

    # Verify all attachment directories are deleted
    failed = False
    for att_dir in att_dirs:
        if att_dir.exists():
            print(f"[FAIL] FAIL: Directory still exists: {att_dir}")
            failed = True

    if failed:
        return False

    print(f"[OK] PASS: All {len(att_dirs)} attachment directories successfully deleted")
    return True


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("  Attachment Cleanup Test Suite")
    print("="*60)
    print("\nTesting attachment file deletion on email deletion...")

    # Check if data directory exists
    data_dir = os.path.expanduser("~/clawmail_data")
    if not Path(data_dir).exists():
        print(f"\n[FAIL] ClawMail data directory not found: {data_dir}")
        print("Please run ClawMail at least once to initialize the database.")
        return

    results = []

    # Run tests
    results.append(("Single email deletion", test_single_email_with_attachment_deletion()))
    results.append(("Email without attachments", test_email_without_attachments()))
    results.append(("Bulk deletion", test_bulk_deletion_with_attachments()))

    # Summary
    print("\n" + "="*60)
    print("  Test Summary")
    print("="*60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "[OK] PASS" if result else "[FAIL] FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n[SUCCESS] All tests passed! Attachment cleanup is working correctly.")
    else:
        print("\n[WARNING]  Some tests failed. Please review the output above.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\n[FAIL] Unexpected error: {e}")
        import traceback
        traceback.print_exc()

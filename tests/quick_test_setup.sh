#!/bin/bash
# Quick Test Setup for ClawMail
# Creates synthetic test account and injects sample emails

set -e

echo "========================================"
echo "  ClawMail - Quick Test Setup"
echo "========================================"
echo ""

cd "$(dirname "$0")"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3."
    exit 1
fi

echo "✅ Python 3 found"
echo ""

# Check if ClawMail data directory exists
DATA_DIR="$HOME/clawmail_data"
if [ ! -d "$DATA_DIR" ]; then
    echo "⚠️  ClawMail data directory not found: $DATA_DIR"
    echo "   Please run ClawMail at least once to initialize the database."
    exit 1
fi

echo "✅ ClawMail data directory found: $DATA_DIR"
echo ""

# Ask user how many emails to inject
echo "How many test emails do you want to create?"
echo "  1. Quick test (5 emails)"
echo "  2. Standard test (10 emails)"
echo "  3. Full test (20 emails)"
echo "  4. Custom amount"
echo ""

read -p "Choice (1-4): " choice

case $choice in
    1)
        COUNT=5
        ;;
    2)
        COUNT=10
        ;;
    3)
        COUNT=20
        ;;
    4)
        read -p "Enter number of emails: " COUNT
        ;;
    *)
        echo "Invalid choice. Using default (10 emails)"
        COUNT=10
        ;;
esac

echo ""
echo "Creating synthetic test account and injecting $COUNT emails..."
echo ""

# Run the injector
python3 synthetic_email_injector.py --batch $COUNT

echo ""
echo "========================================"
echo "  ✅ Setup Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Open ClawMail:"
echo "     cd ~/Desktop/projectA"
echo "     python -m clawmail.ui.app"
echo ""
echo "  2. Look for 'Synthetic Test Account' in account list"
echo "  3. Test AI features on the injected emails"
echo ""
echo "To create more emails:"
echo "  python create_test_email.py"
echo ""
echo "Happy testing! 🎉"

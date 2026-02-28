@echo off
REM Quick Test Setup for ClawMail (Windows)
REM Creates synthetic test account and injects sample emails

echo ========================================
echo   ClawMail - Quick Test Setup
echo ========================================
echo.

cd /d %~dp0

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo X Python not found. Please install Python 3.
    pause
    exit /b 1
)

echo [OK] Python found
echo.

REM Check if ClawMail data directory exists
set DATA_DIR=%USERPROFILE%\clawmail_data
if not exist "%DATA_DIR%" (
    echo [!] ClawMail data directory not found: %DATA_DIR%
    echo     Please run ClawMail at least once to initialize the database.
    pause
    exit /b 1
)

echo [OK] ClawMail data directory found: %DATA_DIR%
echo.

REM Ask user how many emails to inject
echo How many test emails do you want to create?
echo   1. Quick test (5 emails)
echo   2. Standard test (10 emails)
echo   3. Full test (20 emails)
echo   4. Custom amount
echo.

set /p CHOICE="Choice (1-4): "

if "%CHOICE%"=="1" set COUNT=5
if "%CHOICE%"=="2" set COUNT=10
if "%CHOICE%"=="3" set COUNT=20
if "%CHOICE%"=="4" (
    set /p COUNT="Enter number of emails: "
)

if not defined COUNT set COUNT=10

echo.
echo Creating synthetic test account and injecting %COUNT% emails...
echo.

REM Run the injector
python synthetic_email_injector.py --batch %COUNT%

echo.
echo ========================================
echo   [OK] Setup Complete!
echo ========================================
echo.
echo Next steps:
echo   1. Open ClawMail:
echo      cd %USERPROFILE%\Desktop\projectA
echo      python -m clawmail.ui.app
echo.
echo   2. Look for 'Synthetic Test Account' in account list
echo   3. Test AI features on the injected emails
echo.
echo To create more emails:
echo   python create_test_email.py
echo.
echo Happy testing! ^_^
echo.
pause

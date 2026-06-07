@echo off
REM Startup script for PSD Converter Web Application (Windows)

echo 🚀 Starting PSD Converter ^& Email Sender Web Application...
echo.

REM Check if virtual environment exists
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔧 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo 📥 Installing dependencies...
pip install -r requirements.txt

REM Create necessary directories
echo 📁 Creating directories...
if not exist "uploads" mkdir uploads
if not exist "outputs" mkdir outputs
if not exist "static\css" mkdir static\css
if not exist "static\js" mkdir static\js
if not exist "templates" mkdir templates

REM Start the application
echo.
echo ✅ Starting server...
echo 🌐 Open your browser to: http://localhost:8000
echo Press Ctrl+C to stop the server
echo.

uvicorn app:app --host 0.0.0.0 --port 8000 --reload

pause

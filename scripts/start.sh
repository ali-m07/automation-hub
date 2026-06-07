#!/bin/bash
# Startup script for PSD Converter Web Application

echo "🚀 Starting PSD Converter & Email Sender Web Application..."
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p uploads outputs static/css static/js templates

# Start the application
echo ""
echo "✅ Starting server..."
echo "🌐 Open your browser to: http://localhost:8000"
echo "Press Ctrl+C to stop the server"
echo ""

uvicorn app:app --host 0.0.0.0 --port 8000 --reload

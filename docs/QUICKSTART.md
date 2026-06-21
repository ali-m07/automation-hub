# 🚀 Quick Start Guide

## Installation & Running

### Option 1: Using Startup Scripts (Recommended)

**macOS/Linux:**
```bash
./start.sh
```

**Windows:**
```cmd
start.bat
```

### Option 2: Manual Setup

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Create directories:**
```bash
mkdir -p uploads outputs static/css static/js templates
```

3. **Run the application:**
```bash
python app.py
```

Or:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

4. **Open in browser:**
```
http://localhost:8000
```

## First Use

### PSD Converter

1. Upload a PSD template file
2. Upload an Excel/CSV file with your data
3. Map PSD layer names to your data columns
4. Select which columns to use for filenames
5. Click "Process Files"
6. Download the ZIP file with results

### Email Sender

1. Enter your email credentials
2. Upload Excel file with email addresses
3. Configure which columns contain email addresses
4. Choose image sending option
5. Upload images (single or folder)
6. Click "Send Emails"

## Troubleshooting

**Port already in use?**
```bash
# Use a different port
uvicorn app:app --port 8001
```

**Dependencies not installing?**
```bash
# Upgrade pip first
pip install --upgrade pip
pip install -r requirements.txt
```

**PSD file not loading?**
- Ensure the PSD file is not corrupted
- Try with a simpler PSD file first
- Check that `psd-tools` installed correctly: `pip show psd-tools`

## Key Differences from Desktop App

✅ **No Photoshop Required** - Works on any server  
✅ **Web-Based** - Access from anywhere  
✅ **Cross-Platform** - Windows, macOS, Linux  
✅ **Direct PSD Editing** - Open the template in the built-in Photopea workflow and save it back to Servexa  
⚠️ **Batch PSD Rendering Limits** - Automated exports still use the local rendering pipeline for deterministic jobs  

## Next Steps

- Read `README_WEB.md` for detailed documentation
- Check API endpoints for integration
- Deploy to production server for team access

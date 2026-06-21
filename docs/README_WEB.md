# 🚀 PSD Converter & Email Sender - Web Application

A modern web application for processing Photoshop PSD files and sending bulk emails - **No Photoshop installation required!**

## ✨ Features

- ✅ **Web-based Interface** - Beautiful, modern UI accessible from any browser
- ✅ **No Photoshop Required** - Uses `psd-tools` for batch rendering and Photopea for browser-based PSD editing
- ✅ **PSD to PNG/PSD Conversion** - Process PSD files and export to PNG or PSD format
- ✅ **Bulk Processing** - Process multiple rows from Excel/CSV files
- ✅ **Text Layer Replacement** - Automatically replace text in PSD layers
- ✅ **Bulk Email Sending** - Send personalized emails with images
- ✅ **Cross-Platform** - Works on Windows, macOS, and Linux

## 📦 Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Application

```bash
python app.py
```

Or using uvicorn directly:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Access the Application

Open your browser and navigate to:
```
http://localhost:8000
```

## 🎯 How to Use

### PSD Converter

1. **Upload PSD Template**: Click "Choose PSD File" and select your Photoshop template file
2. **Upload Data File**: Click "Choose Data File" and select your Excel or CSV file
3. **Map Layers to Columns**: 
   - Enter the layer name from your PSD
   - Select the corresponding column from your data file
   - Add more mappings as needed
4. **Select Filename Fields**: Choose which columns should be used to name the output files
5. **Process Files**: Click "Process Files" and wait for processing to complete
6. **Download Results**: Download the ZIP file containing all processed images

### Email Sender

1. **Configure Email**: Enter your email address and password
2. **Upload Excel File**: Upload the file containing email addresses and data
3. **Choose Image Option**:
   - Option 1: Attach one image for all emails
   - Option 2: Send different images based on data relationships
4. **Configure Columns**: Map email columns (To, CC, Image filename)
5. **Send Emails**: Click "Send Emails" to start bulk email sending

## 🔧 Technical Details

### PSD Processing

The application uses the `psd-tools` library to:
- Read PSD file structure without Photoshop
- Extract layer information (names, positions, types)
- Composite layers into final images
- Export to PNG format

**Note**: Direct text layer editing is not fully supported by psd-tools. The application uses a workaround:
- Reads the PSD structure and layer positions
- Uses PIL/Pillow to render new text at the same positions
- Composites everything into the final image

### Architecture

- **Backend**: FastAPI (Python)
- **Frontend**: Vanilla JavaScript with modern CSS
- **PSD Processing**: psd-tools + PIL/Pillow
- **File Handling**: Temporary file storage with automatic cleanup

## 📁 Project Structure

```
.
├── app.py                 # FastAPI main application
├── automation_hub/services/psd_processor.py  # PSD file processing logic
├── email_service.py        # Email sending functionality
├── templates/
│   └── index.html         # Main web interface
├── static/
│   ├── css/
│   │   └── style.css      # Styling
│   └── js/
│       └── app.js         # Frontend JavaScript
├── uploads/               # Temporary upload storage
├── outputs/              # Processed file outputs
└── requirements.txt       # Python dependencies
```

## 🌐 Deployment

### Local Development

```bash
uvicorn app:app --reload
```

Or use the Makefile:
```bash
make run
```

### Docker Deployment

**Quick Start:**
```bash
# Build image
docker build -t psd-converter:latest .

# Run container
docker run -d -p 8000:8000 \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/outputs:/app/outputs \
  psd-converter:latest
```

**Using Docker Compose:**
```bash
docker-compose up -d
```

See `DEPLOYMENT.md` for detailed Docker instructions.

### Kubernetes Deployment

**Quick Deploy:**
```bash
# Create namespace
kubectl create namespace psd-converter

# Deploy application
kubectl apply -k k8s/ -n psd-converter

# Check status
kubectl get all -n psd-converter
```

**Using Makefile:**
```bash
make k8s-deploy
make k8s-status
```

See `DEPLOYMENT.md` and `k8s/README.md` for complete Kubernetes deployment guide.

### CI/CD Pipeline

The project includes GitHub Actions workflows for:
- Automated testing
- Docker image building
- Kubernetes deployment
- Security scanning

See `.github/workflows/` for pipeline configuration.

## ⚠️ Limitations

1. **Batch Rendering Engine**: Automated export uses `psd-tools` plus Pillow, so some advanced Photoshop-only features are still flattened during batch rendering.
2. **Complex PSD Files**: Very complex PSD files with advanced effects may render differently in the batch pipeline than in Photoshop or Photopea.
3. **Direct PSD Editing**: Layer editing and PSD save-back are now handled through the embedded Photopea workflow inside Creative Studio.

## 🔍 Troubleshooting

### PSD File Not Loading
- Ensure the PSD file is not corrupted
- Try with a simpler PSD file first
- Check that `psd-tools` is properly installed

### Text Not Appearing Correctly
- Verify layer names match exactly (case-sensitive)
- Check that layers are text layers in the original PSD
- Font rendering may differ from Photoshop

### Email Sending Fails
- Verify SMTP credentials
- Check firewall settings
- Ensure email server allows SMTP connections

## 📝 API Endpoints

- `GET /` - Main web interface
- `POST /api/upload-psd` - Upload PSD template file
- `POST /api/upload-data` - Upload Excel/CSV data file
- `POST /api/process` - Process PSD files with data
- `GET /api/download/{filename}` - Download processed files
- `POST /api/send-emails` - Send bulk emails
- `POST /api/upload-image` - Upload single image
- `POST /api/upload-image-folder` - Upload multiple images

## 🆚 Comparison with Desktop App

| Feature | Desktop App | Web App |
|---------|------------|---------|
| Photoshop Required | ✅ Yes | ❌ No |
| Platform Support | Windows/macOS | All platforms |
| Installation | Complex | Simple |
| Accessibility | Local only | Anywhere |
| Scalability | Single user | Multiple users |
| PSD Editing | Full support | Limited |

## 📄 License

Same as original project.

## 🙏 Credits

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- PSD processing with [psd-tools](https://github.com/psd-tools/psd-tools)
- Image processing with [Pillow](https://pillow.readthedocs.io/)

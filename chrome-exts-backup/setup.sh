#!/bin/bash

echo "Chrome Tab Tracker - Quick Setup"
echo "================================="
echo ""

# Check Python
echo "Checking Python..."
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "ERROR: Python not found. Please install Python 3.8+"
    exit 1
fi

echo "Found Python: $($PYTHON_CMD --version)"
echo ""

# Install dependencies
echo "Installing dependencies..."
$PYTHON_CMD -m pip install -r requirements.txt

echo ""
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Start relay server: $PYTHON_CMD relay_server.py"
echo "2. Load extension in Chrome:"
echo "   - Open chrome://extensions/"
echo "   - Enable Developer mode"
echo "   - Click 'Load unpacked'"
echo "   - Select: $(pwd)/chrome-extension/"
echo "3. Click the extension icon to start collecting"
echo "4. Run agent client: $PYTHON_CMD agent_client.py"
echo ""
echo "Server will be available at:"
echo "  HTTP: http://127.0.0.1:18792"
echo "  Extension WS: ws://127.0.0.1:18792/extension"
echo "  Client WS: ws://127.0.0.1:18792/client"
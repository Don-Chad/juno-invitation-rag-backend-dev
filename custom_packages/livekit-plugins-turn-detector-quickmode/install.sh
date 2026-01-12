#!/bin/bash
# Installation script for Quick Mode Turn Detector
# NO MODEL LOADING - Punctuation-based detection only

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Quick Mode Turn Detector Installation${NC}"
echo "=========================================="
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo -e "${YELLOW}Step 1:${NC} Uninstalling existing livekit-plugins-turn-detector..."
pip uninstall -y livekit-plugins-turn-detector 2>/dev/null || true

echo ""
echo -e "${YELLOW}Step 2:${NC} Installing quick mode turn detector..."
cd "$SCRIPT_DIR"
pip install -e .

echo ""
echo -e "${GREEN}✓ Installation complete!${NC}"
echo ""
echo "Package: livekit-plugins-turn-detector v0.5.0+quickmode"
echo "Mode: QUICK MODE ONLY (no model loading)"
echo ""
echo "Features:"
echo "  • Zero model loading - instant startup"
echo "  • Punctuation-based turn detection (. ! ?)"
echo "  • Multi-language support"
echo "  • Minimal dependencies (only livekit-agents)"
echo "  • Drop-in replacement for standard turn detector"
echo ""
echo "Usage:"
echo "  from livekit.plugins import turn_detector"
echo "  model = turn_detector.EOUModel()"
echo ""


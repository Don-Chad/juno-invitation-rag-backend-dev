#!/bin/bash
# Uninstall script for Quick Mode Turn Detector

set -e

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${YELLOW}Uninstalling Quick Mode Turn Detector${NC}"
echo "=========================================="
echo ""

pip uninstall -y livekit-plugins-turn-detector

echo ""
echo -e "${GREEN}✓ Uninstallation complete!${NC}"
echo ""
echo "To reinstall the original LiveKit version:"
echo "  pip install livekit-plugins-turn-detector"
echo ""


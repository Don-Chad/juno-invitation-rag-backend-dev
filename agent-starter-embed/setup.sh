#!/bin/bash

# Agent Starter Embed - Setup Script
# This script handles initial setup, security audit, updates, and build

set -e  # Exit on any error

echo "=================================================="
echo "Agent Starter Embed - Setup & Build Script"
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Check if pnpm is installed
echo "Step 1: Checking for pnpm..."
if ! command -v pnpm &> /dev/null; then
    print_warning "pnpm not found. Installing pnpm@9.15.9..."
    npm install -g pnpm@9.15.9
    print_status "pnpm installed successfully"
else
    PNPM_VERSION=$(pnpm --version)
    print_status "pnpm is already installed (version: $PNPM_VERSION)"
fi

echo ""

# Check if .env.local exists, if not copy from .env.example
echo "Step 2: Setting up environment variables..."
if [ ! -f .env.local ]; then
    if [ -f .env.example ]; then
        cp .env.example .env.local
        print_status "Created .env.local from .env.example"
        print_warning "Please review .env.local and update with your credentials if needed"
    else
        print_error ".env.example not found. You'll need to create .env.local manually"
    fi
else
    print_status ".env.local already exists"
fi

echo ""

# Run security audit
echo "Step 3: Running security audit..."
echo "----------------------------------------"
pnpm audit || print_warning "Security vulnerabilities found (see above)"
echo "----------------------------------------"
echo ""

# Update dependencies
echo "Step 4: Updating dependencies..."
read -p "Do you want to update all dependencies? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    pnpm update
    print_status "Dependencies updated"
else
    print_status "Skipped dependency update"
fi

echo ""

# Install dependencies
echo "Step 5: Installing dependencies..."
pnpm install
print_status "Dependencies installed"

echo ""

# Build embed popup script
echo "Step 6: Building embed popup script..."
pnpm build-embed-popup-script
print_status "Embed popup script built successfully"

echo ""

# Optional: Run full build
echo "Step 7: Build for production (optional)..."
read -p "Do you want to run a full production build? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    pnpm build
    print_status "Production build completed"
else
    print_status "Skipped production build"
fi

echo ""
echo "=================================================="
echo "Setup Complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo "  1. Review and update .env.local with your credentials"
echo "  2. Start development server: pnpm dev"
echo "  3. Open http://localhost:3000 in your browser"
echo ""
echo "For production deployment:"
echo "  - Run: pnpm build"
echo "  - Then: pnpm start"
echo ""


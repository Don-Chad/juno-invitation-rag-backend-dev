#!/bin/bash

# Backup Script for Voice Assistant Frontend
# This script creates a clean backup of the frontend code for GitHub/Cloudflare Pages deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SOURCE_DIR="voice-assistant-frontend"
BACKUP_DIR="voice-assistant-frontend-cloudflare"
GITHUB_REPO=""

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
    print_error "Source directory '$SOURCE_DIR' not found!"
    exit 1
fi

print_status "Starting backup process..."

# Remove old backup if exists
if [ -d "$BACKUP_DIR" ]; then
    print_warning "Removing old backup directory..."
    rm -rf "$BACKUP_DIR"
fi

# Create fresh backup directory
print_status "Creating backup directory: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

# Copy essential files
print_status "Copying configuration files..."
cp "$SOURCE_DIR/package.json" "$BACKUP_DIR/"
cp "$SOURCE_DIR/tsconfig.json" "$BACKUP_DIR/"
cp "$SOURCE_DIR/next.config.mjs" "$BACKUP_DIR/"
cp "$SOURCE_DIR/tailwind.config.ts" "$BACKUP_DIR/"
cp "$SOURCE_DIR/postcss.config.mjs" "$BACKUP_DIR/"

# Copy app directory (main source code)
print_status "Copying app directory..."
cp -r "$SOURCE_DIR/app" "$BACKUP_DIR/"

# Copy components directory
print_status "Copying components directory..."
cp -r "$SOURCE_DIR/components" "$BACKUP_DIR/"

# Copy hooks directory
print_status "Copying hooks directory..."
cp -r "$SOURCE_DIR/hooks" "$BACKUP_DIR/"

# Copy lib directory (if exists)
if [ -d "$SOURCE_DIR/lib" ]; then
    print_status "Copying lib directory..."
    cp -r "$SOURCE_DIR/lib" "$BACKUP_DIR/"
fi

# Copy public directory
print_status "Copying public directory..."
cp -r "$SOURCE_DIR/public" "$BACKUP_DIR/"

# Copy styles/globals.css if exists
if [ -d "$SOURCE_DIR/styles" ]; then
    print_status "Copying styles directory..."
    cp -r "$SOURCE_DIR/styles" "$BACKUP_DIR/"
fi

# Copy CSS directory if exists
if [ -d "$SOURCE_DIR/css" ]; then
    print_status "Copying css directory..."
    cp -r "$SOURCE_DIR/css" "$BACKUP_DIR/"
fi

# Create .gitignore
print_status "Creating .gitignore..."
cat > "$BACKUP_DIR/.gitignore" << 'EOF'
# Dependencies
node_modules/
.pnp
.pnp.js

# Testing
coverage/

# Next.js
.next/
out/

# Production
build/
dist/

# Misc
.DS_Store
*.pem

# Debug
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Local env files
.env*.local
.env

# Vercel
.vercel

# TypeScript
*.tsbuildinfo
next-env.d.ts

# IDE
.idea/
.vscode/
*.swp
*.swo

# Backup directories
*_backup/
*_backup*/
EOF

# Create README.md for the backup
print_status "Creating README.md..."
cat > "$BACKUP_DIR/README.md" << 'EOF'
# Voice Assistant Frontend

This is the frontend application for the Voice Assistant, designed to be deployed on Cloudflare Pages.

## Architecture Overview

This frontend connects to a separate backend token server for LiveKit authentication.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Cloudflare    │────▶│  Token Server    │────▶│   LiveKit Cloud │
│     Pages       │     │  (Separate VPS)  │     │                 │
│  (This Frontend)│◄────│                  │◄────│                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

## Environment Variables

Create a `.env.local` file with:

```
NEXT_PUBLIC_CONN_DETAILS_ENDPOINT=https://your-token-server.com/createToken
NEXT_PUBLIC_LIVEKIT_URL=wss://your-livekit-server.com
```

## Deployment

### Local Development
```bash
npm install
npm run dev
```

### Build for Production
```bash
npm run build
```

### Deploy to Cloudflare Pages
1. Push this repository to GitHub
2. Connect your GitHub repository to Cloudflare Pages
3. Set build command: `npm run build`
4. Set build output directory: `out`
5. Add environment variables in Cloudflare dashboard

## Important Notes

- **Token Server**: This frontend requires a separate token server for LiveKit authentication
- **Cloudflare Limits**: This frontend is designed to work within Cloudflare Pages free tier limits
  - Unlimited static requests
  - No server-side API routes (all API calls go to external token server)

## Project Structure

```
app/                    # Next.js app directory
  api/                  # API routes (proxies to external token server)
  embed/                # Embed page for iframe integration
  page.tsx              # Main application page
components/             # React components
hooks/                  # Custom React hooks
public/                 # Static assets
```
EOF

# Create a modified next.config.mjs for static export
print_status "Configuring next.config.mjs for static export..."
cat > "$BACKUP_DIR/next.config.mjs" << 'EOF'
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  distDir: 'dist',
  eslint: {
    ignoreDuringBuilds: true,
  },
  images: {
    unoptimized: true,
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Cross-Origin-Opener-Policy",
            value: "same-origin-allow-popups",
          },
        ],
      },
      {
        source: "/embed",
        headers: [
          {
            key: "Access-Control-Allow-Origin",
            value: "*",
          },
          {
            key: "Access-Control-Allow-Methods",
            value: "GET, POST, OPTIONS",
          },
          {
            key: "Access-Control-Allow-Headers",
            value: "Content-Type, Authorization",
          },
          {
            key: "X-Frame-Options",
            value: "ALLOWALL",
          },
          {
            key: "Content-Security-Policy",
            value: "frame-ancestors *;",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
EOF

# Create env.local.example
print_status "Creating env.local.example..."
cat > "$BACKUP_DIR/env.local.example" << 'EOF'
# Token Server Configuration
# This is the URL of your separate token server (NOT on Cloudflare)
NEXT_PUBLIC_CONN_DETAILS_ENDPOINT=https://your-token-server.com/createToken

# LiveKit Configuration
NEXT_PUBLIC_LIVEKIT_URL=wss://your-livekit-server.com

# Firebase Configuration (for authentication)
NEXT_PUBLIC_FIREBASE_API_KEY=your_firebase_api_key
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your_project_id
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your_project.appspot.com
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=your_sender_id
NEXT_PUBLIC_FIREBASE_APP_ID=your_app_id
EOF

print_status "Backup completed successfully!"
print_status "Backup location: $BACKUP_DIR"
echo ""
print_status "Next steps:"
echo "  1. cd $BACKUP_DIR"
echo "  2. git init"
echo "  3. git add ."
echo "  4. git commit -m 'Initial commit for Cloudflare deployment'"
echo "  5. Create a new repository on GitHub"
echo "  6. git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git"
echo "  7. git push -u origin main"
echo ""
print_status "Then connect to Cloudflare Pages:"
echo "  1. Go to https://dash.cloudflare.com"
echo "  2. Navigate to Pages > Create a project"
echo "  3. Connect your GitHub repository"
echo "  4. Build settings:"
echo "     - Build command: npm run build"
echo "     - Build output directory: dist"
echo "  5. Add environment variables from env.local.example"

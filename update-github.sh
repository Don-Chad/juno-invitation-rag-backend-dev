#!/bin/bash

# Update Script for the Project and GitHub Deployment
# This script automates staging, committing, and pushing changes for both
# the full project and the Cloudflare-specific subset.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Configuration
MAIN_REPO_DIR="/home/mark/projects/14_livekit_server_juno_the_invitation_rag_backend_dev"
CLOUDFLARE_DIR="$MAIN_REPO_DIR/voice-assistant-frontend-cloudflare"

# Repository URLs
MAIN_REPO_URL="https://github.com/Don-Chad/livekit-invitation-frontend-dev.git"
CLOUDFLARE_REPO_URL="https://github.com/Don-Chad/livekit-invitation-frontend-dev-cloudflare.git"

# Get current branch of main repo
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")

cd "$MAIN_REPO_DIR"

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}   Project Update & GitHub Push Script            ${NC}"
echo -e "${BLUE}==================================================${NC}"

# 1. Update Main Repository
print_status "Step 1: Updating Full Project Repository..."
print_status "Target: $MAIN_REPO_URL"

# Check for commit message
COMMIT_MSG=$1
if [ -z "$COMMIT_MSG" ]; then
    read -p "Enter commit message (default: 'update $(date '+%Y-%m-%d %H:%M:%S')'): " USER_MSG
    COMMIT_MSG=${USER_MSG:-"update $(date '+%Y-%m-%d %H:%M:%S')"}
fi

# Ensure remote is correct
git remote set-url origin "$MAIN_REPO_URL" 2>/dev/null || git remote add origin "$MAIN_REPO_URL"

# Stage all changes
print_status "Staging changes in main repository..."
git add .

# Commit changes
if git commit -m "$COMMIT_MSG"; then
    print_status "Changes committed."
    print_status "Pushing main repository to GitHub (${CURRENT_BRANCH})..."
    git push origin "$CURRENT_BRANCH"
else
    print_warning "Nothing to commit in main repository."
fi

# 2. Update Cloudflare Deployment
if [ -f "backup-to-github.sh" ]; then
    echo ""
    print_status "Step 2: Preparing Cloudflare Deployment Subset..."
    print_status "Target: $CLOUDFLARE_REPO_URL"
    
    # Run the backup script to update the cloudflare folder
    bash backup-to-github.sh
    
    if [ -d "$CLOUDFLARE_DIR" ]; then
        print_status "Updating Cloudflare deployment folder..."
        cd "$CLOUDFLARE_DIR"
        
        # Initialize git if not already done
        if [ ! -d ".git" ]; then
            print_status "Initializing git in Cloudflare directory..."
            git init
            git remote add origin "$CLOUDFLARE_REPO_URL" || true
            git branch -M main
        else
            # Ensure remote is correct
            git remote set-url origin "$CLOUDFLARE_REPO_URL" 2>/dev/null || git remote add origin "$CLOUDFLARE_REPO_URL"
        fi
        
        # Stage and commit
        git add .
        if git commit -m "Cloudflare deployment update: $(date '+%Y-%m-%d %H:%M:%S')"; then
            print_status "Pushing Cloudflare deployment to GitHub..."
            # Force push because this is a generated subset with a different history
            git push -u origin main --force
            print_status "Cloudflare deployment pushed successfully."
        else
            print_warning "No changes in Cloudflare deployment."
        fi
        
        cd "$MAIN_REPO_DIR"
    fi
fi

echo -e "\n${GREEN}Success! All tasks completed.${NC}"
echo -e "Main Repo: ${MAIN_REPO_DIR} -> ${MAIN_REPO_URL}"
echo -e "Cloudflare Subset: ${CLOUDFLARE_DIR} -> ${CLOUDFLARE_REPO_URL}"

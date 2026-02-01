#!/bin/bash

# Backup Script for Juno The Invitation RAG Backend
# This script creates a full backup to the main GitHub repository, 
# including files from sub-repositories.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SOURCE_DIR="/home/mark/projects/14_livekit_server_juno_the_invitation_rag_backend_dev"
GITHUB_REPO="https://github.com/Don-Chad/juno-invitation-rag-backend-dev.git"
MAIN_BRANCH="main"

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Navigate to source directory
cd "$SOURCE_DIR"

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}   Full Project Backup to GitHub                  ${NC}"
echo -e "${BLUE}==================================================${NC}"

# Check if it's a git repo
if [ ! -d ".git" ]; then
    print_status "Initializing git repository..."
    git init
    git branch -M "$MAIN_BRANCH"
fi

# Ensure remote is correct
print_status "Setting remote origin to: $GITHUB_REPO"
git remote set-url origin "$GITHUB_REPO" 2>/dev/null || git remote add origin "$GITHUB_REPO"

# Check for commit message
COMMIT_MSG=$1
if [ -z "$COMMIT_MSG" ]; then
    COMMIT_MSG="Full backup including sub-repos: $(date '+%Y-%m-%d %H:%M:%S')"
fi

# Handle sub-repositories
print_status "Searching for nested sub-repositories..."

# Use a temporary file to store the list of .git directories to handle spaces correctly
GIT_DIRS_FILE=$(mktemp)
find . -mindepth 2 -name ".git" -type d -not -path "*/.git/*" > "$GIT_DIRS_FILE"

if [ -s "$GIT_DIRS_FILE" ]; then
    print_status "Temporarily hiding nested .git directories to include their files..."
    while IFS= read -r git_dir; do
        hidden_dir="${git_dir}_hidden"
        print_status "  Hiding: $git_dir -> $hidden_dir"
        mv "$git_dir" "$hidden_dir"
    done < "$GIT_DIRS_FILE"
fi

# Stage all changes
print_status "Staging all files (following .gitignore)..."
git add .

# Commit changes
print_status "Committing changes..."
if git commit -m "$COMMIT_MSG"; then
    print_status "Changes committed successfully."
else
    print_warning "No changes to commit."
fi

# Restore sub-repositories
if [ -s "$GIT_DIRS_FILE" ]; then
    print_status "Restoring nested .git directories..."
    while IFS= read -r git_dir; do
        hidden_dir="${git_dir}_hidden"
        if [ -d "$hidden_dir" ]; then
            print_status "  Restoring: $hidden_dir -> $git_dir"
            mv "$hidden_dir" "$git_dir"
        fi
    done < "$GIT_DIRS_FILE"
fi

rm "$GIT_DIRS_FILE"

# Push to GitHub
print_status "Pushing to GitHub (${MAIN_BRANCH})..."
if git push origin "$MAIN_BRANCH"; then
    print_status "Backup completed successfully!"
else
    print_error "Failed to push to GitHub. Check your permissions and connection."
    exit 1
fi

echo -e "${BLUE}==================================================${NC}"
print_status "Backup complete!"
echo -e "${BLUE}==================================================${NC}"

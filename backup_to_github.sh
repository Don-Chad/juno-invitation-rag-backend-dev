#!/bin/bash
# Backup script for juno_the_invitation - Backs up LOCAL changes to GitHub
#
# PURPOSE: This script backs up your LOCAL version to GitHub (remote).
#          Your LOCAL version is the source of truth.
#
# ⚠️ SAFETY: This script NEVER overwrites your local files.
#            It only PUSHES local → remote, never PULLS remote → local.

cd /home/mark/projects/14_livekit_server_juno_the_invitation_rag_backend_dev

echo "🔄 Backing up LOCAL changes to GitHub..."
echo ""

# Check if there are uncommitted changes
if [[ -n $(git status -s) ]]; then
    echo "📝 Staging all changes..."
    git add -A
    
    echo ""
    echo "Changes to be committed:"
    git status -s
    
    echo ""
    read -p "Commit message: " msg
    
    if [[ -z "$msg" ]]; then
        msg="Backup $(date +'%Y-%m-%d %H:%M')"
    fi
    
    # Commit
    git commit -m "$msg"
    echo "✅ Committed locally"
else
    echo "ℹ️  No uncommitted changes to commit"
fi

# Fetch remote info (read-only, doesn't change local)
echo ""
echo "📡 Checking remote status..."
git fetch origin main 2>/dev/null || {
    echo "⚠️  Could not fetch from remote. Continuing anyway..."
}

# Analyze the situation
LOCAL_COMMITS=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo "0")
REMOTE_COMMITS=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "0")

echo ""
echo "📊 Status:"
echo "   Local commits ahead:  $LOCAL_COMMITS"
echo "   Remote commits ahead: $REMOTE_COMMITS"

# Attempt push
echo ""
echo "🚀 Pushing to GitHub..."

if git push origin main 2>&1; then
    echo ""
    echo "✅ Successfully backed up to GitHub!"
    exit 0
else
    PUSH_ERROR=$?
    echo ""
    echo "❌ Push failed (exit code: $PUSH_ERROR)"
    echo ""
    
    # Detailed explanation of why push failed
    if [ "$REMOTE_COMMITS" -gt 0 ]; then
        echo "═══════════════════════════════════════════════════════════════"
        echo "📋 DETAILED EXPLANATION OF THE ISSUE"
        echo "═══════════════════════════════════════════════════════════════"
        echo ""
        echo "🔍 WHY THE PUSH FAILED:"
        echo "   The remote branch has $REMOTE_COMMITS commit(s) that your"
        echo "   local branch doesn't have. Git refuses to push because"
        echo "   this would overwrite those remote commits."
        echo ""
        echo "📊 CURRENT SITUATION:"
        echo "   • Your LOCAL branch:  $LOCAL_COMMITS commits ahead"
        echo "   • Remote branch:     $REMOTE_COMMITS commits ahead"
        echo "   • Branches have DIVERGED (different histories)"
        echo ""
        echo "🔍 WHAT'S ON REMOTE (that you don't have):"
        echo ""
        git log --oneline HEAD..origin/main 2>/dev/null | head -10 | sed 's/^/   /' || echo "   (Could not retrieve)"
        echo ""
        echo "🔍 WHAT'S LOCAL ONLY (that remote doesn't have):"
        echo ""
        git log --oneline origin/main..HEAD 2>/dev/null | head -10 | sed 's/^/   /' || echo "   (Could not retrieve)"
        echo ""
        echo "📁 FILES THAT DIFFER:"
        echo ""
        git diff --name-status HEAD origin/main 2>/dev/null | head -20 | sed 's/^/   /' || echo "   (Could not retrieve)"
        echo ""
        echo "═══════════════════════════════════════════════════════════════"
        echo "💡 YOUR OPTIONS (choose one):"
        echo "═══════════════════════════════════════════════════════════════"
        echo ""
        echo "Option 1: FORCE PUSH (overwrites remote with your local)"
        echo "   ⚠️  WARNING: This will DELETE the remote commit(s)!"
        echo "   Command: git push --force origin main"
        echo ""
        echo "Option 2: EXPLORE DIFFERENCES FIRST (recommended)"
        echo "   See what's different:"
        echo "   • git log HEAD..origin/main     # Remote commits"
        echo "   • git log origin/main..HEAD    # Local commits"
        echo "   • git diff HEAD origin/main    # File differences"
        echo ""
        echo "Option 3: MANUAL RESOLUTION"
        echo "   Create backup branch: git branch backup-$(date +%Y%m%d)"
        echo "   Then manually merge/pull if needed (outside this script)"
        echo ""
        echo "Option 4: DO NOTHING"
        echo "   Keep local and remote separate for now"
        echo ""
        echo "═══════════════════════════════════════════════════════════════"
        echo "🛡️  SAFETY: Your local files are SAFE and UNCHANGED"
        echo "   This script never modifies your local files."
        echo "   All your work is preserved locally."
        echo "═══════════════════════════════════════════════════════════════"
    else
        echo "⚠️  Push failed for unknown reason. Check git output above."
    fi
    
    exit $PUSH_ERROR
fi

#!/bin/zsh
# Run ZPTTLink inside its virtual environment

REPO_DIR="/Users/hxm/Dropbox/ZPTTLink/Software/ZPTTLink"

# Ensure repo exists
if [ ! -d "$REPO_DIR" ]; then
  echo "❌ Repo not found at $REPO_DIR"
  exit 1
fi

# Enter repo
cd "$REPO_DIR" || exit 1

# Activate virtualenv
if [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
else
  echo "⚠️ No venv found. Run refresh_zpttlink.sh first."
  exit 1
fi

# Launch the app
echo "🚀 Starting ZPTTLink..."
python -m zpttlink "$@"


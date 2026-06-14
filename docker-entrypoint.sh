#!/bin/bash
set -e

# 4Dpapers Docker Entrypoint
# Initializes project structure and starts the server
# Designed to work with volume-mounted projects

PROJECT_ROOT="/workspace"
PORT="${PORT:-5006}"
SKIP_INIT="${SKIP_INIT:-false}"

# Colors for output
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}4Dpapers - Docker Startup${NC}"
echo -e "${BLUE}========================================${NC}"

# 1. Ensure workspace exists
echo -e "${YELLOW}[1/4] Checking workspace...${NC}"
mkdir -p "$PROJECT_ROOT"
cd "$PROJECT_ROOT"
echo -e "${GREEN}✓ Workspace: $PROJECT_ROOT${NC}"

# 2. Check if this is a new project or existing one
if [ -f "$PROJECT_ROOT/main.qmd" ] || [ -f "$PROJECT_ROOT/analysis_report.qmd" ]; then
    echo -e "${GREEN}✓ Existing project detected${NC}"
    EXISTING_PROJECT=true
else
    echo -e "${YELLOW}⚠ New project - initializing structure...${NC}"
    EXISTING_PROJECT=false
fi

# 3. Initialize project structure if needed
if [ "$EXISTING_PROJECT" = false ] && [ "$SKIP_INIT" = false ]; then
    echo -e "${YELLOW}[2/4] Creating initial project structure...${NC}"

    # Create directories
    mkdir -p sections
    mkdir -p data
    mkdir -p state/figures
    mkdir -p media
    mkdir -p _output

    # Create minimal analysis_report.qmd
    cat > "$PROJECT_ROOT/main.qmd" << 'EOF'
---
title: "4Dpapers Scientific Analysis"
subtitle: "Powered by Quarto + vtk.js"
author:
  - name: "Your Name"
    affiliation: "Your Institution"
date: today
abstract: |
  This is a 4Dpapers project. Use the dashboard to:
  - Edit QMD files
  - Insert interactive 3D figures
  - Compile to HTML or PDF
format:
  html:
    code-fold: true
    toc: true
  pdf:
    keep-tex: false
jupyter: python3
---

# Introduction

Replace this with your content.

{{< include sections/01_introduction.qmd >}}
EOF

    # Create sections
    cat > "$PROJECT_ROOT/sections/01_introduction.qmd" << 'EOF'
## Introduction

Add your introduction here.
EOF

    # Create _quarto.yml
    cat > "$PROJECT_ROOT/_quarto.yml" << 'EOF'
project:
  title: "4Dpapers Project"
  output-dir: _output
  pre-render:
    - _extensions/4dpaper/4dpaper.py
EOF

    # Create references.bib
    cat > "$PROJECT_ROOT/references.bib" << 'EOF'
@article{example2024,
  title={Example Citation},
  author={Example, Author},
  year={2024}
}
EOF

    echo -e "${GREEN}✓ Project structure created${NC}"
else
    echo -e "${YELLOW}[2/4] Skipping initialization (existing project)${NC}"
fi

# 4. Create .gitignore if not present
if [ ! -f "$PROJECT_ROOT/.gitignore" ]; then
    echo -e "${YELLOW}[3/4] Creating .gitignore...${NC}"
    cat > "$PROJECT_ROOT/.gitignore" << 'EOF'
# Build artifacts
_output/
_freeze/
.quarto/

# State files (runtime)
state/figures/
state/*.json

# Configuration (machine-specific)
_shortcuts.yml

# Python
__pycache__/
*.py[cod]
.venv/
venv/

# IDE
.vscode/
.cursor/
*.swp
.DS_Store
EOF
    echo -e "${GREEN}✓ .gitignore created${NC}"
else
    echo -e "${YELLOW}[3/4] .gitignore already exists${NC}"
fi

# 5. Clear Quarto cache
echo -e "${YELLOW}[4/4] Clearing Quarto cache...${NC}"
rm -rf "$PROJECT_ROOT/.quarto" "$PROJECT_ROOT/_freeze"
echo -e "${GREEN}✓ Cache cleared${NC}"

# 6. Check required files
echo -e "${YELLOW}[5/5] Verifying setup...${NC}"

if [ ! -f "$PROJECT_ROOT/main.qmd" ] && [ ! -f "$PROJECT_ROOT/analysis_report.qmd" ]; then
    echo -e "${YELLOW}⚠ Warning: main.qmd not found${NC}"
fi

if [ ! -d "$PROJECT_ROOT/state/figures" ]; then
    mkdir -p "$PROJECT_ROOT/state/figures"
fi

if [ ! -d "$PROJECT_ROOT/_output" ]; then
    mkdir -p "$PROJECT_ROOT/_output"
fi

# Link app _extensions into workspace so Quarto can find them
if [ ! -e "$PROJECT_ROOT/_extensions" ]; then
    ln -s /app/_extensions "$PROJECT_ROOT/_extensions"
    echo -e "${GREEN}✓ Linked _extensions into workspace${NC}"
fi

# Link Quarto profile files into workspace
for profile_file in /app/_quarto-apphtml.yml /app/_quarto-paperview.yml; do
    dest="$PROJECT_ROOT/$(basename $profile_file)"
    ln -sf "$profile_file" "$dest"
    echo -e "${GREEN}✓ Linked $(basename $profile_file)${NC}"
done

if [ ! -e "$PROJECT_ROOT/scripts" ]; then
    ln -s /app/scripts "$PROJECT_ROOT/scripts"
    echo -e "${GREEN}✓ Linked scripts into workspace${NC}"
fi

# Ensure _quarto.yml exists with correct output-dir
if [ ! -f "$PROJECT_ROOT/_quarto.yml" ]; then
    cat > "$PROJECT_ROOT/_quarto.yml" << 'EOF'
project:
  title: "4Dpapers Project"
  output-dir: _output
  pre-render:
    - _extensions/4dpaper/4dpaper.py
EOF
    echo -e "${GREEN}✓ Created _quarto.yml${NC}"
fi

echo -e "${GREEN}✓ Setup complete${NC}"

# 6. Start the server
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Starting 4Dpapers Server${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Port: $PORT${NC}"
echo -e "${GREEN}Workspace: $PROJECT_ROOT${NC}"
echo ""
echo -e "${YELLOW}The dashboard will be available at:${NC}"
echo -e "${BLUE}http://localhost:$PORT${NC}"
echo ""

# Set environment variables for the app
export PYTHONUNBUFFERED=1
export PROJECT_ROOT="$PROJECT_ROOT"
export DISPLAY=""
export PYVISTA_OFF_SCREEN=true
export VTK_DEFAULT_RENDER_WINDOW_OFFSCREEN=1

# Change to app directory and run serve.py with the workspace path
cd /app
python serve.py --port "$PORT"

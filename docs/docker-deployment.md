# Docker Deployment Guide

**Transform 4Dpapers into a containerized editor** that works like VS Code Server or Cursor - open any folder and start editing.

---

## 🚀 Quick Start

### Option 1: Use Docker Compose (Recommended)

```bash
# Start the container with the default ./workspace folder
docker compose up -d

# Open dashboard at http://localhost:5006
# Your project files are in ./workspace

# Stop the container
docker compose down

# View logs
docker compose logs -f
```

### Option 2: Use Docker directly

```bash
# Build the image
docker build -t 4dpapers:latest .

# Run with a project folder volume
docker run -d \
  --name 4dpapers-editor \
  -p 5006:5006 \
  -v /path/to/your/project:/workspace \
  4dpapers:latest

# Open dashboard at http://localhost:5006

# Stop the container
docker stop 4dpapers-editor
docker rm 4dpapers-editor
```

---

## 📂 Volume Mounting Strategies

### Strategy 1: New Project (Recommended for quick testing)

```bash
# Uses ./workspace by default
docker compose up -d

# Dashboard initializes with template project structure
# Files are saved under ./workspace
```

**Pros:** Simple, isolated from the application source tree
**Cons:** The local `workspace/` folder is ignored by git

---

### Strategy 2: Existing Project (Recommended for real work)

Mount your actual project folder:

```bash
FOURD_WORKSPACE=/path/to/my/4dpapers/project docker compose up -d
```

**Pros:** Changes persist in your repo, can commit to git
**Cons:** Host filesystem dependency

---

### Strategy 3: Bind Mount + Compose Override

Use `docker-compose.override.yml` for local development if you prefer a persistent local override:

```yaml
# docker-compose.override.yml (git-ignored)
version: '3.8'

services:
  4dpapers:
    volumes:
      - /absolute/path/to/project:/workspace
```

Then:

```bash
docker compose up -d
```

**Pros:** Override in override.yml (doesn't commit to git)
**Cons:** Need to manage override file separately

---

## 🎯 Common Use Cases

### Use Case 1: Edit an Existing 4Dpapers Project

```bash
# Mount your project folder
docker run -d \
  --name 4dpapers \
  -p 5006:5006 \
  -v ~/research/cardiac-ep:/workspace \
  4dpapers:latest

# Open http://localhost:5006
# Edit files, compile, export
```

---

### Use Case 2: Start a Fresh Project

```bash
# Use docker compose with the default ./workspace folder
docker compose up -d

# Container initializes with template structure:
# - main.qmd
# - sections/01_introduction.qmd
# - references.bib
# - Directories: data/, state/, media/, _output/

# Dashboard opens, ready to edit

# Later, export the project:
docker cp 4dpapers-editor:/workspace /tmp/my-project
```

---

### Use Case 3: Multiple Projects (Switch Between Them)

```bash
# Project 1
docker run -d \
  --name 4dpapers-project1 \
  -p 5006:5006 \
  -v ~/projects/paper1:/workspace \
  4dpapers:latest

# In another terminal, Project 2
docker run -d \
  --name 4dpapers-project2 \
  -p 5007:5006 \
  -v ~/projects/paper2:/workspace \
  4dpapers:latest

# Access:
# http://localhost:5006 → Paper 1
# http://localhost:5007 → Paper 2
```

---

### Use Case 4: CI/CD Pipeline Integration

```bash
# Validate QMD + generate PDF in CI
docker run --rm \
  -v /path/to/project:/workspace \
  4dpapers:latest \
  --skip-init

# Quarto will compile in /workspace/_output/
# Extract PDF from output volume
```

---

## 🔧 Configuration

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORT` | 5006 | Dashboard port |
| `FOURD_WORKSPACE` | `./workspace` | Host paper folder mounted by Docker Compose |
| `PYTHONUNBUFFERED` | 1 | Real-time logging |
| `SKIP_INIT` | false | Skip template initialization (for existing projects) |

### Example: Custom Port

```bash
docker run -d \
  -p 8080:5007 \
  -e PORT=5007 \
  -v project:/workspace \
  4dpapers:latest
```

---

## 📋 Container Lifecycle

### What Happens on Startup

1. **Check workspace** — Is `/workspace` empty?
2. **Detect project type** — Is `main.qmd`, `analysis_report.qmd`, `_quarto.yml`, or any root `.qmd` present?
3. **Initialize (if new)** — Create template structure:
   - `main.qmd` (root document)
   - `sections/01_introduction.qmd`
   - `references.bib`
   - Directories: `data/`, `state/figures/`, `_output/`
   - `.gitignore` (excludes build artifacts)
4. **Verify directories** — Ensure `state/figures/` and `_output/` exist
5. **Start server** — Listen on configured port

### Logs

```bash
# View initialization + startup logs
docker compose logs

# Follow logs in real-time
docker compose logs -f

# View logs for specific time range
docker compose logs --since 1m
```

---

## 🛠️ Building Your Own Image

### Build Locally

```bash
docker build -t my-4dpapers:latest .
```

### Push to Registry (Docker Hub/GitHub Container Registry)

```bash
# Docker Hub
docker tag 4dpapers:latest myusername/4dpapers:latest
docker push myusername/4dpapers:latest

# GitHub Container Registry
docker tag 4dpapers:latest ghcr.io/myusername/4dpapers:latest
docker push ghcr.io/myusername/4dpapers:latest
```

### Use Prebuilt Image

```bash
# Replace Dockerfile build with prebuilt image
docker-compose.yml:
  services:
    4dpapers:
      image: myusername/4dpapers:latest  # Instead of 'build:'
```

---

## 🐛 Troubleshooting

### Dashboard not accessible at http://localhost:5006

```bash
# Check if container is running
docker ps | grep 4dpapers

# Check port mapping
docker port 4dpapers-editor

# Check container logs
docker logs 4dpapers-editor

# Verify health
docker inspect 4dpapers-editor | grep -i health
```

### Files not persisting

```bash
# Check volume mount
docker inspect 4dpapers-editor | grep -A 5 "Mounts"

# List volumes
docker volume ls

# Check volume contents
docker exec 4dpapers-editor ls -la /workspace
```

### Quarto not found in container

```bash
# Verify Quarto is installed
docker exec 4dpapers-editor quarto --version

# Check Quarto path
docker exec 4dpapers-editor which quarto
```

### Permission denied on volume files

```bash
# The container runs as root by default.
# If mounting from host, ensure proper permissions:
chmod 755 /path/to/project
```

---

## 📊 Dockerfile Structure

```
Dockerfile:
├── FROM python:3.11-slim       # Base image
├── Install system deps         # curl, git, ca-certificates
├── Install Quarto              # Scientific publishing system
├── Copy app code               # /app/dashboard, /app/serve.py
├── Install Python packages     # panel, tornado, pyvista
├── WORKDIR /workspace          # Mount point for projects
├── EXPOSE 5006                 # Dashboard port
└── ENTRYPOINT docker-entrypoint.sh  # Initialize + start server
```

---

## 🔐 Security Notes

### Volume Permissions

- Container runs as `root` (simplifies volume access)
- For production, consider non-root user
- Host machine must trust container (full read/write to volume)

### Network Isolation

- Only port 5006 exposed
- Dashboard/API authentication is enabled when `FOURD_API_KEY` is set
- For internet-facing deployments, set `FOURD_API_KEY`, set `FOURD_ALLOWED_ORIGIN`, and use a reverse proxy with TLS

### Data Persistence

- The default Compose workspace is the ignored host folder `./workspace`
- Use `FOURD_WORKSPACE=/path/to/project docker compose up` to edit an existing paper
- Back up important projects before container cleanup

---

## 🚀 Advanced: Production Deployment

### Kubernetes Deployment

```yaml
# 4dpapers-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: 4dpapers-editor
spec:
  replicas: 1
  selector:
    matchLabels:
      app: 4dpapers
  template:
    metadata:
      labels:
        app: 4dpapers
    spec:
      containers:
      - name: 4dpapers
        image: myregistry.azurecr.io/4dpapers:latest
        ports:
        - containerPort: 5006
        volumeMounts:
        - name: project
          mountPath: /workspace
        env:
        - name: PORT
          value: "5006"
      volumes:
      - name: project
        emptyDir: {}  # Or use PersistentVolumeClaim
---
apiVersion: v1
kind: Service
metadata:
  name: 4dpapers-service
spec:
  selector:
    app: 4dpapers
  ports:
  - protocol: TCP
    port: 80
    targetPort: 5006
  type: LoadBalancer
```

Deploy:
```bash
kubectl apply -f 4dpapers-deployment.yaml
```

---

## 📚 File Structure in Container

```
/app/                          # Application code (read-only)
├── dashboard/                 # Flask/Tornado handlers
├── _extensions/               # Quarto extensions
├── serve.py                   # Entry point
├── docker-entrypoint.sh       # Initialization script

/workspace/                    # Project folder (volume mount)
├── main.qmd                   # Main document
├── sections/                  # Document sections
├── data/                      # User inputs (simulations, etc.)
├── state/                     # Runtime-generated files
│   ├── figures/               # Generated HTML/PNG figures
│   ├── camera_*.json          # Camera states (hidden from UI)
│   └── field_*.json           # Field states (hidden from UI)
├── media/                     # Images, videos
├── _output/                   # Compiled HTML/PDF
├── references.bib             # Bibliography
└── _quarto.yml               # Quarto configuration
```

---

## ✅ Checklist: From Folder App to Container

- ✅ Dockerfile created (Python 3.11, Panel, Quarto, dependencies)
- ✅ docker-entrypoint.sh created (initializes projects, starts server)
- ✅ docker-compose.yml created (`FOURD_WORKSPACE` controls the mounted paper folder)
- ✅ Port 5006 exposed
- ✅ Health check configured
- ✅ Volume mount strategy documented
- ✅ Startup logs show project initialization

**Ready to deploy to:** Docker Hub, Kubernetes, Docker Swarm, VPS, Cloud Run, etc.

---

## 🎓 Next Steps

1. **Build:** `docker build -t 4dpapers:latest .`
2. **Test locally:** `docker compose up`
3. **Mount a project:** `FOURD_WORKSPACE=/path/to/project docker compose up`
4. **Push to registry:** `docker push myregistry/4dpapers:latest`
5. **Deploy anywhere:** Any platform that runs Docker

---

**Documentation:** See README.md for detailed usage
**Support:** Check container logs with `docker compose logs -f`

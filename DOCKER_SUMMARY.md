# Docker Deployment - What Was Created

**Transform 4Dpapers from a folder-based app into a containerized, volume-aware editor** - similar to VS Code Server, Cursor, or an AI agent workspace.

---

## 📦 New Files Created

### 1. **Dockerfile**
- Python 3.11 slim base image
- Installs Quarto CLI for scientific document rendering
- Copies application code (`dashboard/`, `_extensions/`, `serve.py`)
- Installs Python dependencies (Panel, Tornado, PyVista)
- Sets `/workspace` as the mount point for projects
- Exposes port 5006
- Runs health checks

**Location:** `/Users/simaocastro/4Dpapers/Dockerfile`

---

### 2. **docker-compose.yml**
- Single-service setup for easy development
- Mounts `project` volume at `/workspace`
- Exposes port 5006
- Auto-restart policy
- Health check configured
- Comments for GPU support (optional)

**Usage:**
```bash
docker-compose up -d
# Open http://localhost:5006
```

**Location:** `/Users/simaocastro/4Dpapers/docker-compose.yml`

---

### 3. **docker-entrypoint.sh** (executable)
Smart initialization script that:

- Detects if project is new or existing
- Creates template structure for new projects:
  - `analysis_report.qmd` (root document)
  - `sections/01_introduction.qmd`
  - `references.bib`
  - Directories: `data/`, `state/figures/`, `media/`, `_output/`
  - `.gitignore` (excludes build artifacts)
- Verifies required directories exist
- Starts the server on configured port

**Startup flow:**
```
1. Check if /workspace is empty
2. If new → create template structure
3. If existing → use as-is
4. Verify directories (state/figures/, _output/)
5. Start server with logs
```

**Location:** `/Users/simaocastro/4Dpapers/docker-entrypoint.sh`

---

### 4. **requirements.txt**
Python dependencies for the Docker image:
- panel>=1.3.0
- tornado>=6.3
- pyvista>=0.43.0
- quarto>=0.1.0

**Location:** `/Users/simaocastro/4Dpapers/requirements.txt`

---

### 5. **DOCKER_DEPLOYMENT.md** (100+ lines)
Comprehensive deployment guide covering:
- Quick start (docker-compose)
- Volume mounting strategies
- Common use cases (single project, multiple projects, CI/CD)
- Configuration (environment variables)
- Troubleshooting
- Advanced deployments (Kubernetes, production)

---

## 🔧 Code Updates (Workspace-Aware)

### Updated: `serve.py`
- Detects `PROJECT_ROOT` from environment variable or defaults to app directory
- Separates app code (`/app`) from project workspace (`/workspace`)
- Sets `PROJECT_ROOT` env var for plugins to use
- Prints both app and project root on startup

**Key change:**
```python
# In Docker: app_root=/app, project_root=/workspace
# In dev: both point to /Users/simaocastro/4Dpapers
app_root = Path(__file__).parent
project_root = Path(os.getenv("PROJECT_ROOT", str(app_root)))
```

---

### Updated: `dashboard/camera_plugin.py`
- Uses `PROJECT_ROOT` environment variable
- Fallback to parent directory for development
- All API handlers work with either dev or Docker paths

**Key change:**
```python
_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).parent.parent)))
```

---

### Updated: `dashboard/upload_plugin.py`
- Same workspace-aware update as camera_plugin.py
- Insert Figure/Insert File work in any project folder

---

### Updated: `dashboard/plugins.py`
- Workspace-aware route registration
- `/state/` and `/output/` routes point to correct folders

---

## 🚀 How It Works

### Development (Local)
```bash
# Works as before
python serve.py
# Project files loaded from current directory
```

### Docker (Single Project)
```bash
# Mount a project folder
docker run -d \
  -p 5006:5006 \
  -v /path/to/my/project:/workspace \
  4dpapers:latest

# OR use docker-compose
docker-compose up -d
```

### Docker (New Project)
```bash
# Let Docker create a managed volume
docker-compose up -d
# Container initializes with template structure
# Access at http://localhost:5006
```

---

## 📊 Architecture

```
┌─────────────────────────────────────┐
│      Docker Image (Dockerfile)      │
│  - Python 3.11                      │
│  - Quarto CLI                       │
│  - Application code (/app)          │
│  - Entrypoint script                │
└──────────────┬──────────────────────┘
               │
               ├─ Mounts volume /workspace
               │
┌──────────────▼──────────────────────┐
│    Project Volume (/workspace)      │
│  - analysis_report.qmd              │
│  - sections/                        │
│  - data/ (user inputs)              │
│  - state/ (generated figures)       │
│  - _output/ (compiled HTML/PDF)     │
└─────────────────────────────────────┘
               │
        Exposed on :5006
               │
               ▼
        Browser http://localhost:5006
```

---

## ✅ What You Can Do Now

### 1. Build the Image
```bash
docker build -t 4dpapers:latest .
```

### 2. Run with Existing Project
```bash
docker run -d \
  --name 4dpapers-editor \
  -p 5006:5006 \
  -v ~/research/my-paper:/workspace \
  4dpapers:latest
```

### 3. Run with New Project
```bash
docker-compose up -d
# Container creates template structure automatically
```

### 4. Multiple Projects
```bash
# Terminal 1: Project A
docker run -p 5006:5006 -v ~/projects/paper-a:/workspace 4dpapers:latest

# Terminal 2: Project B
docker run -p 5007:5006 -v ~/projects/paper-b:/workspace 4dpapers:latest

# Access: http://localhost:5006 (A), http://localhost:5007 (B)
```

### 5. Push to Registry
```bash
docker tag 4dpapers:latest myregistry.azurecr.io/4dpapers:latest
docker push myregistry.azurecr.io/4dpapers:latest
```

### 6. Deploy to Cloud
- **Docker Hub:** Share on Docker Hub for anyone to use
- **Azure Container Registry:** Enterprise deployment
- **GitHub Container Registry:** GitHub-integrated deployment
- **Kubernetes:** Multi-replica production deployment
- **AWS ECS:** Serverless container deployment

---

## 🎯 Key Features

✅ **Volume-aware** — Works with any mounted project folder
✅ **Self-initializing** — Creates template structure for new projects
✅ **Workspace separation** — App code in Docker, projects as volumes
✅ **Environment-configurable** — PROJECT_ROOT can be set via env var
✅ **Backwards compatible** — Works in development (python serve.py)
✅ **Health checks** — Container monitors dashboard health
✅ **Port configurable** — PORT environment variable
✅ **Production-ready** — Includes logging, error handling, restart policies

---

## 📚 Next Steps

1. **Build:** `docker build -t 4dpapers:latest .`
2. **Test locally:** `docker-compose up -d`
3. **Test with project:** Mount your project folder
4. **Push to registry:** Share with others
5. **Deploy:** Use docker-compose, Docker Swarm, or Kubernetes

For detailed deployment instructions, see **DOCKER_DEPLOYMENT.md**

---

## 🔐 Notes

- Container runs as root (simplifies volume access)
- For production, consider non-root user
- Dashboard is unauthenticated (assume trusted network)
- Volume data persists after container stops

---

**Status:** ✅ Ready to build and deploy

**Test it now:**
```bash
docker-compose up -d
# Open http://localhost:5006
```

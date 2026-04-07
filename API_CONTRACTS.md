# 4DPaper API Contracts

This document defines the contracts between the HTML frontend (`dashboard/static/index.html`) and the backend API endpoints.

## Setup

Run the server with:
```bash
python serve.py
```

This automatically loads all API routes from `dashboard/plugins.py`.

---

## API Endpoints

### 1. GET `/api/files`
**Purpose:** List user-facing project files and folders (security-filtered)

**Filtering:** Returns only user content. Hides system code (`dashboard/`, `_extensions/`, `.git/`, etc.) and internal state files (`state/*.json`). Shows `state/figures/` for access to generated figures.

**Request:**
```javascript
const response = await fetch('/api/files');
const data = await response.json();
```

**Response (200 OK):**
```json
{
  "files": [
    "analysis_report.qmd",
    "sections/01_introduction.qmd",
    "_quarto.yml",
    "config.yaml"
  ]
}
```

**Error (500):**
```json
{
  "error": "error message"
}
```

---

### 2. GET `/api/file?path=<filepath>`
**Purpose:** Read a single file's content (text files only)

**Request:**
```javascript
const response = await fetch(`/api/file?path=${encodeURIComponent(filePath)}`);
const content = await response.text();
```

**Response (200 OK):**
```
Raw file content as text/plain
```

**Errors:**
- **400:** `{"error": "path parameter required"}` — missing path parameter
- **403:** `{"error": "Access denied"}` — path traversal attempt
- **404:** `{"error": "File not found"}` — file doesn't exist
- **500:** `{"error": "..."}` — server error

---

### 3. POST `/api/compile`
**Purpose:** Compile the QMD file to HTML

**Request:**
```javascript
const response = await fetch('/api/compile', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    files: {
      "analysis_report.qmd": "file content",
      "other_file.qmd": "file content"
    }
  })
});
const result = await response.json();
```

**Request Body:**
```json
{
  "files": {
    "filepath": "content",
    "filepath2": "content2"
  }
}
```

**Response (200 OK):**
```json
{
  "status": "success",
  "html": "<html>compiled content...</html>"
}
```

**Error (500):**
```json
{
  "error": "Compilation failed",
  "log": "last 50 lines of build output"
}
```

---

### 4. POST `/api/export`
**Purpose:** Export the QMD file to PDF

**Request:**
```javascript
const response = await fetch('/api/export', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' }
});

if (response.headers.get('content-type').includes('application/pdf')) {
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'analysis_report.pdf';
  a.click();
}
```

**Request Body:** Empty or `{}`

**Response (200 OK):**
- Content-Type: `application/pdf`
- Headers: `Content-Disposition: attachment; filename="analysis_report.pdf"`
- Body: PDF binary data

**Error (500):**
```json
{
  "error": "PDF export failed",
  "log": "last 50 lines of build output"
}
```

---

## Frontend Implementation

The HTML frontend (`dashboard/static/index.html`) implements these contracts:

1. **File Tree Loading** (line 563-575)
   - Calls `GET /api/files`
   - Renders file tree with syntax highlighting

2. **File Opening** (line 602-625)
   - Calls `GET /api/file?path=...`
   - Loads content into editor

3. **Compile Button** (line 673-739)
   - Calls `POST /api/compile` with current editor content
   - Updates preview with compiled HTML
   - Shows status in status bar

4. **Export Button** (line 742-778)
   - Calls `POST /api/export`
   - Triggers PDF download
   - Shows success/error alerts

---

## Handler Implementations

All handlers are in `dashboard/camera_plugin.py`:

| Endpoint | Handler | File |
|----------|---------|------|
| GET /api/files | `FilesHandler` | camera_plugin.py:101-124 |
| GET /api/file | `FileHandler` | camera_plugin.py:127-166 |
| POST /api/compile | `CompileHandler` | camera_plugin.py:169-230 |
| POST /api/export | `ExportHandler` | camera_plugin.py:233-277 |

---

## Testing the Contracts

### Test file listing
```bash
curl http://localhost:5006/api/files
```

### Test file reading
```bash
curl 'http://localhost:5006/api/file?path=analysis_report.qmd'
```

### Test compile
```bash
curl -X POST http://localhost:5006/api/compile \
  -H 'Content-Type: application/json' \
  -d '{"files":{"analysis_report.qmd":"# Test"}}'
```

### Test export
```bash
curl -X POST http://localhost:5006/api/export \
  -o analysis_report.pdf
```

---

## Security Notes

- **Path Traversal Prevention:** FileHandler blocks `../` and absolute paths using `is_relative_to()` check
- **Backend Filtering:** FilesHandler hides system code and internal state files before returning to frontend
  - Hidden: `.git`, `.venv`, `dashboard/`, `_extensions/`, `state/*.json`
  - Visible: User documents, data folders, `state/figures/`
- **CORS Enabled:** All endpoints allow cross-origin requests (for iframe safety)
- **Content-Type Headers:** Properly set for each response type
- **File Validation:** Only user-facing files listed (QMD, BIB, YAML, text files, figures)

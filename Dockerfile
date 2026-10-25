# ==========================================
# Stage 1: Build Frontend (Vite + React)
# ==========================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ==========================================
# Stage 2: Unified Lightweight Runner (Raspberry Pi & PC compatible)
# ==========================================
FROM python:3.11-slim AS runner

# Install FFmpeg, git (for auto-updating and cloning APIs), and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install main requirements (including YoitsuWrap & yt-dlp)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Clone the API repositories directly at build/runtime (not part of Nami repo)
RUN git clone --depth 1 https://github.com/TMCooper/AnimeSamaApi.git /app/AnimeSamaApi \
    && git clone --depth 1 https://github.com/TMCooper/voiranime_API.git /app/voiranime_API

# Install dependencies for internal APIs
RUN pip install --no-cache-dir -r /app/AnimeSamaApi/requirements.txt || true
RUN pip install --no-cache-dir -r /app/voiranime_API/requirements.txt || true

# Re-ensure typing_extensions, anyio and FastAPI compatibility (prevents sub-dependency downgrades)
RUN pip install --no-cache-dir --upgrade "typing-extensions>=4.14.0" "anyio>=4.8.0" "fastapi>=0.100.0"


# Copy backend application
COPY backend /app/backend

# Create persistent storage mountpoints
RUN mkdir -p /app/data /downloads

# Copy compiled frontend from builder
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Expose port 8080 (LAN & Docker accessible)
EXPOSE 8080

ENV PYTHONUNBUFFERED=1
ENV DOWNLOADS_DIR=/downloads
ENV DATA_DIR=/app/data

# Run unified server on port 8080
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]

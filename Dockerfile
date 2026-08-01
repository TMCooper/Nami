# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Final Backend Container
FROM python:3.11-slim AS runner

# Install FFmpeg, git, and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python requirements & install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Clone submodules directly (avoids empty submodule dirs if not initialized on host)
RUN git clone --depth 1 https://github.com/TMCooper/AnimeSamaApi.git /app/AnimeSamaApi \
    && git clone --depth 1 https://github.com/TMCooper/voiranime_API.git /app/voiranime_API

# Install submodule-specific Python dependencies
RUN pip install --no-cache-dir -r /app/AnimeSamaApi/requirements.txt || true
RUN pip install --no-cache-dir -r /app/voiranime_API/requirements.txt || true

# Copy app backend code
COPY backend /app/backend
RUN mkdir -p /app/data

# Copy built frontend assets from builder stage
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Expose port 8080 (bound to 0.0.0.0 for LAN access)
EXPOSE 8080

# Environment variables
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]

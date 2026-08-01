# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Final Backend Container
FROM python:3.11-slim AS runner

# Install FFmpeg and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python requirements & install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy submodules and app code
COPY AnimeSamaApi /app/AnimeSamaApi
COPY voiranime_API /app/voiranime_API
COPY backend /app/backend
RUN mkdir -p /app/data

# Copy built frontend assets from builder stage
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Expose port 8080 (bound to 0.0.0.0 for LAN access)
EXPOSE 8080

# Environment variables
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]

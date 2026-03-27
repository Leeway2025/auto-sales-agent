# Frontend Dockerfile — multi-stage build + Nginx
# Build:  docker build -t voice-agent-frontend:latest ./frontend
# Note: Runtime API calls go through /api → backend:8000 (Nginx proxy)

# ── Stage 1: build ──────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci --prefer-offline

COPY . .
RUN npm run build

# ── Stage 2: serve with Nginx ───────────────────────────────────────────────
FROM nginx:1.27-alpine

# Replace default config with API proxy config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

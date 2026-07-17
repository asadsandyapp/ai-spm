# syntax=docker/dockerfile:1

# --- Build stage ---------------------------------------------------------
FROM node:20-alpine AS build
WORKDIR /app

# Install dependencies (leverage layer caching)
COPY package.json package-lock.json* ./
RUN npm ci || npm install

# Build the static SPA
COPY . .
# VITE_API_URL is baked at build time; override with --build-arg for prod.
ARG VITE_API_URL=http://localhost:8080
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# --- Runtime stage -------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# SPA-aware nginx config (history fallback + asset caching + security headers)
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]

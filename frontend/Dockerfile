# ── Stage 1: Build the React app ───────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (better layer caching)
COPY package*.json ./
RUN npm ci

# Copy source and build
COPY . .
RUN npm run build

# ── Stage 2: Serve with Nginx ───────────────────────────────────────────────
FROM nginx:1.25-alpine

# Install envsubst (part of gettext)
RUN apk add --no-cache gettext

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config template
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# nginx docker image automatically runs envsubst on files in /etc/nginx/templates/
# and writes them to /etc/nginx/conf.d/ — no custom entrypoint needed.

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

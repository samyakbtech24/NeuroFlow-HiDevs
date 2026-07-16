# Stage 1: Build
FROM node:20-slim AS builder
WORKDIR /app
COPY package*.json ./
# If package-lock.json doesn't exist, npm ci fails, so fallback to npm install if needed
RUN npm ci || npm install
COPY . .
RUN npm run build

# Stage 2: Runtime (Node.js)
FROM node:20-slim AS runtime
ENV NODE_ENV=production
WORKDIR /app

RUN groupadd -r neuroflow && useradd -r -g neuroflow neuroflow

# Next.js standalone output automatically copies node_modules and server.js
COPY --from=builder --chown=neuroflow:neuroflow /app/public ./public
COPY --from=builder --chown=neuroflow:neuroflow /app/.next/standalone ./
COPY --from=builder --chown=neuroflow:neuroflow /app/.next/static ./.next/static

USER neuroflow

EXPOSE 3000
CMD ["node", "server.js"]

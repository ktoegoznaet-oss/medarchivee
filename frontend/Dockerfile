# syntax=docker/dockerfile:1.7

# ============================================================
# Builder — устанавливает npm-зависимости один раз
# ============================================================
FROM node:20-alpine AS deps

WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund

# ============================================================
# Dev — горячая перезагрузка через Vite (используется в compose)
# ============================================================
FROM node:20-alpine AS dev

WORKDIR /app
ENV NODE_ENV=development
COPY --from=deps /app/node_modules ./node_modules
COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ============================================================
# Build — продакшен-сборка (используется с этапа 12)
# ============================================================
FROM node:20-alpine AS build

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ============================================================
# Prod — отдача статики через nginx
# ============================================================
FROM nginx:1.27-alpine AS prod

COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

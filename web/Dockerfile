# WHY: production image for the Next.js 16 review/results app, deployed on the
# lab PC via docker-compose (see docker-compose.yml at repo root). Standalone
# build keeps the runtime image slim; tracked data blobs (web/data, web/public)
# are baked in because the app reads them from disk at request time.
# Build from repo root:  docker build -t vmlu-web -f web/Dockerfile web/

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
COPY --from=build /app/data ./data
EXPOSE 3000
CMD ["node", "server.js"]

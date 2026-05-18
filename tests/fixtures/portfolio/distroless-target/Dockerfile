FROM node:20-slim AS build
WORKDIR /app
COPY package.json ./
RUN npm ci --omit=dev || true
COPY index.js ./

FROM gcr.io/distroless/nodejs20-debian12@sha256:d4f8be40e3a3da72bfb96ad0f4bdcd8a3a7d33b1f4e5e9a4c6d8b2a1e0f3c5d7
COPY --from=build /app /app
WORKDIR /app
CMD ["index.js"]

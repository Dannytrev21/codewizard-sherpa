FROM node:20-slim AS build
WORKDIR /app
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/ ./packages/
RUN npm install -g pnpm@8 && pnpm install --frozen-lockfile && pnpm -r build

FROM node:20-slim
WORKDIR /app
COPY --from=build /app/packages/app/dist ./packages/app/dist
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/packages/app/package.json ./packages/app/
USER node
EXPOSE 3000
CMD ["node", "packages/app/dist/index.js"]

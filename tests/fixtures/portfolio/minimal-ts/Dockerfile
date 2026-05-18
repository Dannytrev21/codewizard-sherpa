FROM node:20-slim
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
COPY src ./src
COPY tsconfig.json ./
USER node
EXPOSE 3000
CMD ["node", "dist/index.js"]

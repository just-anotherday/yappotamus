FROM node:22-alpine
WORKDIR /app
COPY backend/ai-generator-backend/package*.json ./
RUN npm ci --omit=dev
COPY backend/ai-generator-backend .
EXPOSE 3000
CMD ["node", "server.js"]

# syntax=docker/dockerfile:1
FROM node:20-slim AS build

WORKDIR /app

# 依赖层单独缓存：lockfile 不变则不重复 npm ci
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

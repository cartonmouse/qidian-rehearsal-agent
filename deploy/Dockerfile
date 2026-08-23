FROM node:22-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc python3-dev nginx \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /frontend/dist /usr/share/nginx/html
COPY deploy/public-nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/start-public.sh /usr/local/bin/qidian-start

RUN chmod +x /usr/local/bin/qidian-start

EXPOSE 10000

CMD ["qidian-start"]

# Stage 1: Build the React application
FROM node:20-alpine as build

WORKDIR /app

# Copy package configurations
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci

# Copy frontend source code
COPY . .

ARG VITE_API_BASE_URL=/api
ARG VITE_ENABLE_DEMO_MODE=0
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_ENABLE_DEMO_MODE=$VITE_ENABLE_DEMO_MODE

# Build the Vite application for production
RUN npm run build

# Stage 2: Serve the application using Nginx
FROM nginx:alpine

# Remove default nginx HTML
RUN rm -rf /usr/share/nginx/html/*

# Copy built assets from builder stage
COPY --from=build /app/dist /usr/share/nginx/html

# Add custom Nginx config for single-page app routing
RUN echo "server { \
    listen 80; \
    location / { \
        root /usr/share/nginx/html; \
        index index.html index.htm; \
        try_files \$uri \$uri/ /index.html; \
    } \
}" > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

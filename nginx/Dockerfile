# Nginx reverse proxy for Automation Hub (long timeouts, no buffering for downloads)
FROM nginx:alpine
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.docker.conf /etc/nginx/nginx.conf
EXPOSE 80

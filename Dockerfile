FROM python:3.12-slim
WORKDIR /app
COPY domradar /app/domradar
COPY config.example.json /app/config.example.json
ENV TZ=Europe/Warsaw
CMD ["python", "-m", "domradar", "watch", "--config", "/config/config.json", "--data", "/data", "--send"]

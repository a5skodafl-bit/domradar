FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY domradar /app/domradar
COPY config.example.json /app/config.example.json
ENV TZ=Europe/Warsaw
CMD ["python", "-m", "domradar", "watch", "--config", "/config/config.json", "--data", "/data", "--send"]

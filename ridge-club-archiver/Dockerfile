FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# State + credentials are mounted as volumes; downloads are ephemeral
VOLUME ["/app/state", "/app/credentials"]

CMD ["python", "run.py", "watch"]

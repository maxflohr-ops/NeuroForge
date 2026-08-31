FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg unzip \
    && rm -rf /var/lib/apt/lists/*

# Deno: JS runtime yt-dlp needs to solve YouTube's n-token challenge
ADD https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip /tmp/deno.zip
RUN unzip -o /tmp/deno.zip -d /usr/local/bin && rm /tmp/deno.zip && deno --version

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# State + credentials are mounted as volumes; downloads are ephemeral
VOLUME ["/app/state", "/app/credentials"]

CMD ["python", "run.py", "watch"]

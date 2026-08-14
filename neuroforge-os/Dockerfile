FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY prompts/ prompts/
COPY scripts/ scripts/
COPY commander/ commander/

# Output and DB are mounted at runtime (see docker-compose.yml)
# so generated content persists on the host and isn't lost on container restart

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "scripts/neuroforge_pipeline.py"]

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# agent name is passed by compose / the platform: python runner.py <agent>
ENTRYPOINT ["python", "runner.py"]
CMD ["archivist"]

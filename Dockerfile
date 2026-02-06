FROM python:3.13-slim

# Install exiftool + basic deps
RUN apt-get update \
  && apt-get install -y --no-install-recommends libimage-exiftool-perl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python deps first for better caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . /app

# Render sets PORT; default fallback is 8000
ENV PORT=8000

# Start FastAPI (keep your workers=3)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 3"]

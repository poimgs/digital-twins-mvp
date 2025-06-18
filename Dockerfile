FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY main.py .

# Create data directory for local storage
RUN mkdir -p /app/bot_data

# Set Python path
ENV PYTHONPATH=/app

# Run the bot
CMD ["python", "main.py"]
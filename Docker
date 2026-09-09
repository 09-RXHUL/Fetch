FROM python:3.9-slim

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Add a startup script that upgrades yt-dlp and then starts the server
COPY start.sh .
RUN chmod +x start.sh

COPY . .

# Use the startup script as the container command
CMD ["./start.sh"]
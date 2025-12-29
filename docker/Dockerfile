FROM python:3.9

WORKDIR /

COPY . .

# ubuntu dependencies
RUN apt-get update && apt-get install -y nano vim tmux cron python3-venv ffmpeg libsm6 libxext6  -y 

# python dependencies
RUN pip install -r requirements.txt

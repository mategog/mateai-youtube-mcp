FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY yt_studio.py mcp_server.py report_template.html ./

ENV PYTHONUNBUFFERED=1
ENV MATEAI_YT_HOME=/tmp/mateai-yt

ENTRYPOINT ["python3", "/app/mcp_server.py"]

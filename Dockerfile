FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY yt_common.py yt_auth.py yt_quota.py yt_public.py yt_snapshot.py yt_videos.py yt_manage.py yt_retention.py yt_setup.py yt_studio.py tiktok_studio.py mcp_server.py report_template.html ./

ENV PYTHONUNBUFFERED=1
ENV MATEAI_YT_HOME=/tmp/mateai-yt

ENTRYPOINT ["python3", "/app/mcp_server.py"]

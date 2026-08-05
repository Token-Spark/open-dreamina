FROM python:3.11-slim

# 系统依赖：ffmpeg 用于视频缩略图抽帧
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

COPY . .

# 数据目录（由 docker-compose 挂载 volume 覆盖）
RUN mkdir -p /app/data/db /app/data/assets /app/data/backups

EXPOSE 10130

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10130"]

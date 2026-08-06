FROM python:3.11-slim

# 系统依赖：ffmpeg 用于视频缩略图抽帧；curl 用于即梦 CLI 一键安装
# 切换到清华镜像加速 apt（默认 deb.debian.org 在国内极慢）；--mount=type=cache 缓存下载的 deb 包，加速后续构建
RUN --mount=type=cache,target=/var/cache/apt \
    sed -i 's@deb.debian.org@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

COPY . .

# 数据目录（由 docker-compose 挂载 volume 覆盖）
RUN mkdir -p /app/data/db /app/data/assets /app/data/backups

EXPOSE 10130

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10130"]

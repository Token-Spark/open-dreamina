FROM python:3.11-slim

# 系统依赖：ffmpeg 用于视频缩略图抽帧；curl 用于即梦 CLI 一键安装。
# 国内镜像加速：默认阿里云。清华源对 Debian 13 (trixie) 的 debian / debian-security
# 路径返回 403（InRelease 未签名），不能再写死为默认源。
# 换源：docker compose build --build-arg APT_MIRROR=deb.debian.org backend
#       （也可填 mirrors.tencent.com；--mount=type=cache 缓存 deb 包加速后续构建）
ARG APT_MIRROR=mirrors.aliyun.com
RUN --mount=type=cache,target=/var/cache/apt \
    sed -i -E "s@https?://deb.debian.org@https://$APT_MIRROR@g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
# pip 源同理：清华 PyPI 在部分网络下 403；默认阿里云，可传
# --build-arg PIP_INDEX_URL=https://pypi.org/simple 切回官方源。
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
RUN pip install --no-cache-dir -r requirements.txt --index-url "$PIP_INDEX_URL"

COPY . .

# 数据目录（由 docker-compose 挂载 volume 覆盖）
RUN mkdir -p /app/data/db /app/data/assets /app/data/backups

EXPOSE 10130

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10130"]

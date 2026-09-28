# 后端对接：镜头审片中心（Backend Integration）

> 对应 SKILL.md 索引中的 `references/05-backend-integration.md`。
> 后端在线、需要回写审阅中心时加载。接口以本仓库 backend 实测为准（2026-09 验证）。

## 1. 前置条件

```bash
curl -fsS http://localhost:10130/api/v1/system/health   # 后端在线（端口以后端实际监听为准，默认 10130）
```

审片根目录由环境变量配置（`SHOT_REVIEW_SOURCE_ROOTS`，逗号分隔多个）；`GET /folders` 返回当前允许扫描的根与两层子目录。

## 2. 标准流程

```text
1. health 确认后端在线
2. GET /folders                      → 可审目录（确认剧目在允许根之下）
3. GET /sessions                     → 已有会话；按 root_path 匹配复用，避免重复建会话
4. 无匹配 → POST /sessions 建会话（自动扫描）；已有 → POST /sessions/{id}/scan 增量同步
5. GET /sessions/{id}/items?episode=&verdict=pending   → 待审条目（含分镜元数据）
6. 逐镜看片（references/06 第 4 节），按 references/04 打分写意见
7. PATCH 单条 或 POST batch 批量回写（≤50 条/批）
8. GET /sessions/{id} 取最新 summary，输出汇总报告
```

会话命名建议：`初审 <YYYY-MM-DD> <范围>`（如 `初审 2026-09-28 EP05-EP08`），便于制片人在审阅中心识别初审批次。

## 3. API 速查（已验证）

基础地址：`BASE=http://localhost:10130/api/v1`，审片路由前缀 `/shot-reviews`。

```bash
# 可审目录（含两层子目录树）
curl -fsS "$BASE/shot-reviews/folders"

# 会话列表（含 summary：pending/pass/revise/redesign/total/scored/average_score/multi_take_shots/selected_shots）
curl -fsS "$BASE/shot-reviews/sessions"

# 创建会话（root_path 必须在允许根之下；创建即扫描）
curl -fsS -X POST "$BASE/shot-reviews/sessions" -H 'Content-Type: application/json' \
  -d '{"title":"初审 2026-09-28 EP05","root_path":"/app/shot_sources/短剧剧本代号奥林匹斯/分镜脚本/EP05"}'

# 增量重扫（新增/移除的视频同步进会话；不触碰已有审阅结果）
curl -fsS -X POST "$BASE/shot-reviews/sessions/{id}/scan"

# 条目列表（可按 episode=EP05、verdict=pending|pass|revise|redesign 过滤）
curl -fsS "$BASE/shot-reviews/sessions/{id}/items?episode=EP05&verdict=pending"

# 单条回写
curl -fsS -X PATCH "$BASE/shot-reviews/items/{item_id}" -H 'Content-Type: application/json' \
  -d '{"score":72,"feedback":"…","revised_prompt":"…"}'

# 批量回写（≤50 条/批；字段省略 = 不修改）
curl -fsS -X POST "$BASE/shot-reviews/sessions/{id}/items/batch" -H 'Content-Type: application/json' \
  -d '{"items":[{"id":"…","score":72,"feedback":"…","revised_prompt":"…"}]}'

# 看片素材
curl -fsS "$BASE/shot-reviews/items/{item_id}/file" -o /tmp/shot.mp4      # 视频原文件
curl -fsS "$BASE/shot-reviews/items/{item_id}/thumbnail" -o /tmp/thumb.webp  # 首帧缩略图（仅预览）

# 最新汇总
curl -fsS "$BASE/shot-reviews/sessions/{id}"
```

条目响应中的分镜元数据（「应有」）：`shot_function / script_duration / shot_size / movement / dialogue / source_prompt / render_status / model / width / height / duration`；`source_prompt` 即 shots.md 提示词底稿原文，写精修提示词时以它为底（见 04 第 4 节）。

## 4. 路径映射（宿主机直读视频）

会话与条目里的路径是**容器内路径**（默认根 `/app/shot_sources`，来自 `SHOT_REVIEW_SOURCE_ROOTS`）。宿主机对应目录由 `SHOT_REVIEW_SOURCES_HOST_PATH` 挂载（docker-compose 默认 `./data/shot_sources`）：

```text
宿主机路径 = 宿主根 + (容器路径去掉容器根前缀)
例：/app/shot_sources/短剧剧本代号奥林匹斯/分镜脚本/EP05
 → ./data/shot_sources/短剧剧本代号奥林匹斯/分镜脚本/EP05
```

宿主根不确定时：问用户要宿主机目录，或退回用 `/items/{id}/file` 逐条下载到临时目录看片（慢但稳）。**绝不对容器路径做本地 open。**

## 5. 安全边界（强制）

1. 只回写 `score / feedback / revised_prompt`；`selected` 不传、删除接口（`POST /sessions/{id}/items/delete`、`DELETE /items/{id}`）不调、会话状态（`PATCH /sessions/{id}`）不改——这些是制片人在审阅中心的决策。
2. 复用会话前先 `GET /sessions` 按 `root_path` 匹配；不要盲目建重复会话。
3. 批量回写 ≤50 条/批；响应 `{updated, failed}` 中 failed>0 时逐条重试或记录，不静默丢弃。
4. 回写前不需要清分（score 直接覆盖）；确认不要覆盖某条时该条不进批次。
5. 看片下载的临时文件放系统临时目录，用完即弃，不落素材目录。

## 6. 故障处理

| 现象 | 处理 |
|---|---|
| 404 not_found（会话/条目） | 先 `POST /sessions/{id}/scan` 重扫；仍缺则该镜按「无法审片」记录 |
| 400 invalid_folder | root_path 不在允许根之下 → 改用 `GET /folders` 返回的合法路径 |
| 400 scan_failed | 目录不可读/权限 → 报告用户，不重试暴力扫描 |
| 后端不可达 | 切离线模式（references/06），已有结论落盘为报告，不丢工作 |

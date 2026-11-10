# 生产清单（Manifest）详细 Schema

> 对应 SKILL.md 索引中的 `references/production-schema.md`。
> 编写 / 校验 Manifest 时加载。定义资产、任务、镜头、产物等生产对象的机器可读字段。

## 1. 顶层结构

```yaml
production:
  episode: <Episode 对象>
  assets: <Asset 对象列表>
  tasks: <Task 对象列表>
  shots: <Shot 对象列表>
  artifacts: <Artifact 对象列表>
  budgets: <Budget 对象列表>
  qc_results: <QCResult 对象列表>
  retries: <Retry 对象列表>
```

## 2. Episode 对象

```yaml
episode:
  id: E01                 # 稳定 ID，唯一
  title: ""               # 集标题
  status: PLANNING        # PLANNING / IN_PRODUCTION / QC / APPROVED / DELIVERED
  style_bible: ""         # 风格圣经引用（ID 或路径）
  version: "1.0.0"
```

## 3. Asset 对象

```yaml
asset:
  id: CHAR-A-V01          # 稳定 ID，格式：<TYPE>-<标识>-V<NN>
  type: CHARACTER         # CHARACTER / LOCATION / PROP / COSTUME / VEHICLE / CREATURE / VFX / VOICE / MUSIC / SFX / RELATIONSHIP_KEYFRAME / INDOOR_LAYOUT_ANCHOR / EPISODE_STATE_LOCK
  status: APPROVED        # PENDING / GENERATED / QC_PENDING / APPROVED / FAILED / HUMAN_REVIEW
  version: V01
  provenance:             # 来源链
    source: "director-shot-plan"
    episode: E01
  references: []          # 相关参考文件 ID 列表
  locked: true            # 是否已锁定（批准后视为不可变输入）
  tags: []                # 可选标签
```

### 3.1 锚点类资产（RELATIONSHIP_KEYFRAME / INDOOR_LAYOUT_ANCHOR / EPISODE_STATE_LOCK）

| 字段 | 说明 |
|---|---|
| `id` | `rel_*` / `loc_*` / `char_*_ep{xx}_{造型}_turnaround` / `scene_*_ep{xx}_{状态}`，命名见 `ai-video-director/references/19-relationship-keyframe.md`、`20-indoor-layout-anchor.md`、`21-episode-state-lock.md` |
| `platform_asset_id` | `opendreamina upload` 返回值；登记在 `tools/asset_registry.json` |
| `approved` | 批准状态；未批准不得通过生成门禁 |
| `sidecar_ref` | `{项目根}/导演设计/EPxx/shot-design.md` 中对应 `## EPxx-SNN`（集内状态写 `## EPxx 集内状态`） |
| `camera_facing` | 仅 `INDOOR_LAYOUT_ANCHOR`：该锚点对应的机位朝向（viewA / viewB / viewWide） |
| `episode_scope` | 仅 `EPISODE_STATE_LOCK`：生效集段（`EP07` 或 `EP07-08`），跨集不复用 |

`rel_*` / `loc_*` **不进 `drama spec` 的 refs**（`ASSET_ID_RE` 白名单静默过滤），生成时由编排层
按 sidecar 手工组装多参考；完整命令见 `ai-video-director/references/19-relationship-keyframe.md` §8。

`EPISODE_STATE_LOCK` 是例外：`char_*_turnaround` 与 `scene_*` 都在白名单内，**正常进 refs、
正常被 `drama assets` 审计**，不要照抄 `rel_*` 的手工组装流程。

## 4. Task 对象

```yaml
task:
  id: E01-S03-SH07-KEYFRAME   # 稳定 ID，格式：<Episode>-<Scene>-<Shot>-<TYPE>
  type: IMAGE                 # IMAGE / KEYFRAME / VIDEO / VOICE / MUSIC / SFX / LIPSYNC / UPSCALE / POST
  status: APPROVED            # PENDING / BLOCKED / READY / QUEUED / RUNNING / GENERATED / QC_PENDING / APPROVED / FAILED / RETRYING / CANCELLED / HUMAN_REVIEW
  priority: HIGH              # URGENT / HIGH / NORMAL / LOW
  dependencies:
    - CHAR-A-V01
    - LOC-HOSPITAL-V01
  model: ""                   # 路由到的模型
  compiled_prompt: ""         # 编译后的 Prompt（或引用）
  parameters:                 # 技术参数
    resolution: "1920x1080"
    duration_seconds: 4
    frame_rate: 30
    seed: null
  attempts: 0
  max_attempts: 5
  retry_sequence: []          # 重试记录 ID 列表
  result_artifact: ""         # 产物 ID
```

## 5. Shot 对象

```yaml
shot:
  id: E01-S03-SH07            # 稳定 ID
  scene: E01-S03
  beat: ""
  keyframe_task: E01-S03-SH07-KEYFRAME
  video_task: E01-S03-SH07-VIDEO
  continuity:                 # 连续性锁定引用
    character: [CHAR-A-V01]
    location: LOC-HOSPITAL-V01
    episode_state: []           # 集内状态锚点（本集妆造三视图 / 场景状态图）
    relationship_keyframe: ""   # rel_* ID（多人 / 共现组合）
    indoor_view_anchor: ""      # loc_*_viewX ID（室内多角度）
    camera_facing: ""           # 本镜朝向，须与锚点一致
  screen_direction: ""
  status: APPROVED
```

## 6. Artifact 对象

```yaml
artifact:
  id: ART-E01-S03-SH07-VIDEO-V01
  task_id: E01-S03-SH07-VIDEO
  type: VIDEO
  path: ""                    # 本地/远端路径
  checksum: ""                # 完整性校验
  provenance: []              # 来源链（生成该产物的 Prompt / 参考 / 任务）
  created_at: ""
```

## 7. Budget 对象

```yaml
budget:
  scope: SHOT                 # EPISODE / SCENE / SHOT / ASSET
  scope_id: E01-S03-SH07
  estimated_cost: 0
  actual_cost: 0
  generation_count: 0
  retry_count: 0
  currency: CNY
```

## 8. QCResult 对象

```yaml
qc_result:
  id: QC-E01-S03-SH07-VIDEO-01
  target: E01-S03-SH07-VIDEO
  gate: VIDEO                 # ASSET / KEYFRAME / VIDEO / CONTINUITY / STORY / FINAL
  decision: RETRY             # PASS / RETRY / REDESIGN / HUMAN_REVIEW
  checks:                     # 分项检查
    identity_consistency: true
    motion_quality: true
    anatomy: true
    camera_movement: true
    physics: true
    background_stability: true
    temporal_consistency: true
  notes: ""                   # 说明与依据
```

## 9. Retry 对象

```yaml
retry:
  id: RET-E01-S03-SH07-VIDEO-02
  task_id: E01-S03-SH07-VIDEO
  attempt: 2
  failure_category: PROMPT     # IDENTITY / ANATOMY / COMPOSITION / MOTION / CONTINUITY / PROMPT / MODEL / REFERENCE / TECHNICAL
  diagnosis: ""                # 失败诊断
  correction: ""               # 采取的修正（参数调整 / Prompt 简化 / 参考调整 / 换模型 / 镜头重设计）
  result: FAILED               # 结果
```

## 10. 校验约束

1. 所有 ID 全局唯一且稳定，禁止复用已删除 ID。
2. Task 只有在 dependencies 全部为 `APPROVED` 时才可进入 `READY`。
3. `HUMAN_REVIEW` 状态必须携带原因，禁止自动清除。
4. 已批准版本（`APPROVED`）的资产/产物不可覆盖；变更必须产生新版本 ID。
5. QC 决策为 `PASS` 前，相关 Task 不得进入 `APPROVED`。
6. 超过 `max_attempts` 的 Task 必须转为 `HUMAN_REVIEW`。

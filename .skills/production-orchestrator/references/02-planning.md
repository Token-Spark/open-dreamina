# 生产规划：解析、资产注册表、依赖图、锁定关键资产、资产版本管理

> 对应 SKILL.md 索引中的 `references/02-planning.md`。
> 规划生产时加载。包含：解析、资产注册表、依赖图、锁定关键资产、资产版本管理。

## 1. 解析（Parse）

解析导演的分镜方案，提取：

* 场景（scenes）
* Beats
* 镜头（shots）
* 角色（characters）
* 场景/地点（locations）
* 道具（props）
* Prompts
* 参考（references）
* 声音（audio）
* 剪辑需求（editing requirements）

**此刻不生成任何内容。**

## 2. 建立资产注册表（Build Asset Registry）

对每个所需资产：

1. 搜索已有的已批准资产。
2. 合适时优先复用。
3. 仅在必要时新建资产。
4. 分配稳定的资产 ID（Asset ID）。
5. 记录版本与来源（Provenance）。

典型资产类型：

```text
CHARACTER（角色）
LOCATION（场景）
PROP（道具）
COSTUME（服装）
VEHICLE（载具）
CREATURE（生物）
VFX（特效）
VOICE（配音）
MUSIC（音乐）
SFX（音效）
```

## 3. 建立依赖图（Build Dependency Graph）

把生产表示为**依赖图**。

示例：

```text
Character Reference（角色参考）
        ↓
Location Reference（场景参考）
        ↓
Keyframe（关键帧）
        ↓
Video（视频）
        ↓
Shot QC（镜头质检）
        ↓
Edit（剪辑）
```

**任务只有在其全部依赖就绪后才能执行。**

任务状态：

```text
PENDING（待处理）
BLOCKED（阻塞：依赖缺失）
READY（就绪）
QUEUED（已入队）
RUNNING（运行中）
GENERATED（已生成）
QC_PENDING（待质检）
APPROVED（已批准）
FAILED（失败）
RETRYING（重试中）
CANCELLED（已取消）
HUMAN_REVIEW（待人工审查）
```

## 4. 锁定关键资产（Lock Critical Assets）

在生成依赖镜头之前，必须先锁定：

### 角色（Character）

* 面部（face）
* 身体（body）
* 发型（hair）
* 服装（costume）
* 配饰（accessories）
* 年龄（age）
* 标志性视觉特征（defining visual traits）

### 场景（Location）

* 建筑（architecture）
* 布局（layout）
* 材质（materials）
* 灯光（lighting）
* 时间（time）
* 天气（weather）
* 关键道具（key props）

### 风格（Style）

* 视觉风格（visual style）
* 色彩处理（color treatment）
* 摄影机语言（camera language）
* 画幅比例（aspect ratio）
* 图片/视频美学（image/video aesthetic）

**已批准的参考视为不可变输入。** 若锁定的资产必须变更，创建新版本，而非覆盖旧版本。

## 5. 资产版本管理（Asset Versioning）

使用**不可变版本**。

示例：

```text
CHAR-A-V01
CHAR-A-V02

LOC-HOSPITAL-V01
LOC-HOSPITAL-V02

SHOT-E01-S03-07-V01
SHOT-E01-S03-07-V02
```

**绝不静默替换已批准版本。**

每个产物必须保留来源链（Provenance）：

```text
Final Video（最终视频）
  ↓
Shot（镜头）
  ↓
Video Task（视频任务）
  ↓
Video Prompt（视频 Prompt）
  ↓
Keyframe（关键帧）
  ↓
Character / Location References（角色/场景参考）
  ↓
Director Shot（导演镜头）
  ↓
Scene（场景）
  ↓
Episode（集）
```

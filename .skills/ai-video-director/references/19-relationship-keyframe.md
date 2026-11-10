# 关系关键帧：多人 / 人物-场景共现的空间锚定

> 专业知识层 `19`，服务 STEP 5（一致性资产）、STEP 9（Keyframe 门禁）与 STEP 10（交付）。
> 本文件定义的是**关系锚点**：锁「谁在谁旁边、谁离窗多远」，补齐
> `05-continuity-and-lock.md` 只锁「长什么样」的缺口。

## 1. 为什么单资产锚点不够

现有锚点各自锁一类信息：

| 锚点 | 锁住 | 锁不住 |
|---|---|---|
| 角色 `*_turnaround` / primary | 这个人长什么样 | 他站在谁的左边、离门多远 |
| 场景 `primary` | 这个地方长什么样 | 人在这个地方的哪个位置 |
| 全局风格四常量 | 全片色调质感 | 空间关系 |

AIGC 每次生成会**重新构图**。即使三个锚点都对，模型仍可自由重排空间，
于是出现：多人同镜左右互换、身份张冠李戴；人物与场景反复共现时
人在场景里漂移、道具与人的关系变、轴线翻转、正反打两侧对不上。

> 结论：**人物之间、人物与场景之间的相对位置关系，必须由一张已批准的关键帧引导**。
> 文字描述站位不等于锚定——提示词里写「A 站在 B 左边」，模型仍可能反过来。

## 2. 触发条件（命中任一即必须有关系关键帧）

| # | 条件 | 说明 |
|---:|---|---|
| 1 | 同镜 ≥2 个具名角色 | 含对视、对话、肢体接触、群像 |
| 2 | 同一「人物 + 场景」组合第 2 次及以后出现 | 跨镜、跨集都算；反复共现是漂移高发区 |
| 3 | 同一场景内 ≥2 个镜头共享同一组站位 | **正反打也算**：单镜只拍一人，剪起来仍是同一空间 |
| 4 | 人物与地标 / 关键道具有固定相对位置 | 窗、门、桌、楼梯、信物 |
| 5 | 跨镜有空间依赖 | 反应镜头、POV、越轴、运动路径接续 |
| 6 | 同一组合换机位 / 换景别重新拍 | 机位变了，关系不能跟着变 |

**关键推论**：把多人镜头拆成「单人正反打 + 台词」能降低生成难度，
但**不免除关系关键帧**——只要成片里这些镜头被剪成同一空间，
观众仍会感知左右与距离。拆镜是生成策略，不是空间关系的替代。

## 3. 关系关键帧是什么

一张**已批准的空间布局定稿图**，必须同时固定：

```text
人物集合（谁在场）+ 各自站位（左/右、前/后、坐/站）
人物 ↔ 场景地标的相对位置与大致距离
视线方向与轴线侧（与 13 号机位图一致）
基准机位（用于推导同场景其它机位）
光线 / 色调（继承 Visual Bible，不自创）
```

它不是：角色三视图、场景 primary、故事板画格、成片首帧；室内场景时它以**已批准的室内布局总览/全景锚点**为空间底图（见 `20`）。
职责分工：**关系帧管「在哪」，单资产管「长什么样」**，两者一起给，不互相替代。

## 4. 命名、登记与版本

```text
rel_{场景}_{人物组合}_{版本}
例：rel_forge_venus_hephaestus_v1
    rel_hospital_corridor_lei_nurse_v2
```

- 登记、白名单代码事实与验收依据统一见 **§8**；无平台 `asset_id` 视为未登记（沿用「无登记不引用」纪律）。
- **同一组合 + 同一空间状态必须复用同一张**，禁止每镜重新出一张。
- 关系发生变更（有人离场 / 换位 / 时间光线切换）→ 新建版本 `v2`，
  在 sidecar 注明「关系变更点」，旧版本保留不删（与 `_superseded_*` 纪律一致）。

## 5. 落地方式（按平台能力选，不写死一种）

| 方式 | 参数 | 适用 |
|---|---|---|
| **内容参考（优先）** | `reference_asset_ids` / `reference_paths` + `frame_mode: reference` | Seedance 实测首选；多参考可同时给关系帧 + 角色三视图 + 场景 primary |
| 首帧驱动 | `frame_mode: first` | 平台支持、且该镜从确定布局起幅时 |
| 首尾帧 | `frame_mode: first_last` | **慎用**：`drama-production-playbook/references/03-seedance-best-practices.md` 补充规则 5 已记录易画面不协调 |

多参考时的固定组合：

```text
关系关键帧（站位 / 距离）
+ 每个在场角色的 *_turnaround（身份）
+ 场景 primary（外观）
+ 全局风格四常量（逐字拼接）
```

提示词只写「延续参考图中的人物站位与空间关系」并描述**本镜动作**，
不要再用文字重新描述一遍站位（文字与参考图冲突时模型会自行发挥）。

生成消费**不走** `drama spec` 的 refs（白名单会过滤 `rel_*`），由编排层按 sidecar 手工组装多参考，见 §8。

## 6. 生成门禁（硬）

触发条件命中，以下任一不成立 → 任务标记 `BLOCKED`，不得生成视频：

1. 关系关键帧不存在 → 先生成并批准。
2. 存在但未批准 → 等批准。
3. 引用了错误组合 / 旧版本 → 改正后重试。
4. 关系帧通过，但视频里出现位置漂移 → **先修关系帧或改镜头**，不得靠反复抽卡解决。

顺序不可颠倒：**室内布局/全景锚点 → 关系关键帧 → 单镜关键帧 → 视频**（室内场景时，见 `20` §7）。
关系帧未定，单镜关键帧不许开工；室内布局未定，关系帧也不许开工——关系帧必须画在同一个房间的同一套结构上。

## 7. QC 验收

- **关键帧 QC** 增加「相对位置」：左右站位、前后层次、与地标的距离、视线方向、轴线侧。
- **视频 QC** 增加「关系漂移」：是否左右互换、是否越过地标、正反打两侧是否对得上、
  跨镜同一组合的相对位置是否一致。
- **审片**对照关系关键帧 + `shots.md` + 机位图；位置不一致 → 降档，
  精修提示词里明确写「回到关系关键帧 `{asset_id}` 的站位」。

## 8. 与 shots.md / lint 的兼容（继承 `17` 的管线保护）

### 代码事实（重要，别写做不到的事）

`drama/` 对资产 ID 有硬编码白名单 `ASSET_ID_RE = (char|scene|prop|crowd|icon|voice)_...`
（`drama/parser/shots_parser.py` 与 `drama/qc/audit_refs.py`）。`rel_*` / `loc_*` 不在其中：

| 环节 | 行为 |
|---|---|
| `drama lint` | 不检查资产名 / 前缀 → 通过，**但不代表已登记** |
| `drama parse` / `drama spec` | 白名单静默过滤，`refs` 里**不会**出现 `rel_*` / `loc_*` |
| `drama assets` | 同上，`referenced_assets` 里**不可见**（不报错、不告警） |
| `drama manifest` | `id` 不校验前缀，但 `category` 只接受 `01_characters` / `02_scenes` / `03_props` / `04_iconic_scenes` / `_pilot_style`；自定义 `type` 无害但无人消费 |
| 生成侧（CLI / MCP / 后端） | 只认 `asset_id` 或本地路径，**不解析前缀** → 多参考直接传即可 |

`load_episode_spec()` 在仓库内无调用方，`EPxx.json` 是纯交付档案，不驱动生成。

### 落地路径（不改 `drama/` 代码）

1. **不改** `shots.md` 的 15 行模板、15 列列序、必填行与 lint 规则；
   **不要把 `rel_*` / `loc_*` 写进「资产绑定」行**（写了也不会进 refs，只会造成「已登记」的错觉）。
2. `opendreamina upload <图片>` → 平台 `asset_id` → 写入 `tools/asset_registry.json`：
   ```json
   {"version":1,"provider":"","scope":"project",
    "assets":{"rel_forge_venus_hephaestus_v1":{"platform_asset_id":"<id>"}}}
   ```
3. 全部语义元数据放 `{项目根}/导演设计/EPxx/shot-design.md` sidecar
   （资产 ID / `asset_id` / 批准状态 / 版本 / 关系变更点 / 机位朝向）。
4. 生成消费由编排层按 sidecar **手工组装多参考**，绕开 spec 的 refs：
   ```bash
   opendreamina image2video --provider sparkhub-seedance \
     --reference-asset <rel_* 的 asset_id> \
     --reference-asset <loc_*_viewX 的 asset_id> \
     --reference <char_*_turnaround> --reference <scene_*_primary> \
     --frame-mode reference --aspect-ratio 9:16 --prompt "<编译提示词>" --auto-wait
   ```
   `--reference` / `--reference-asset` 可多次传、可混用；MCP `reference_asset_ids` /
   `reference_paths` 无 `maxItems`。provider 层软上限：Seedance 图片 30 张、
   Gemini 图生图 14 张（超出静默截断）；`first_last` 需 2 张。
5. `assets_manifest.json` 只作**人可读记录**：`id` 可用 `rel_*`，但 `category` 必须取白名单值
   （建议 `04_iconic_scenes`）、`mode: img2img` 且带 `reference_primary`、`filename` 指向真实文件。

sidecar 追加块：

```markdown
## EP05-S08
- 关系关键帧：`rel_forge_venus_hephaestus_v1` / 平台 asset_id `xxxx` / 登记：tools/asset_registry.json / 状态：已批准
- 本镜沿用站位：A 左 B 右，A 距窗约 1m，轴线同侧（C1）
- 关系变更点：无（若换 v2 在此写明）
```

## 9. 边界

- 不重复 `05-continuity-and-lock.md` 的 Lock 字段、`13-spatial-narration-and-axis.md` 的机位图绘制规范。
- 不重复 `17-storyboard-vs-shotlist-dual-output.md` 的管线保护条款；本文件是其「AI 生成指令」字段的一个具体展开。
- 不改 Seedance 参数基线（见 `drama-production-playbook/references/03-seedance-best-practices.md`）。

# 质量管控（QC）与 QC 决策

> 对应 SKILL.md 索引中的 `references/06-quality-control.md`。
> 各生产门禁质检时加载。包含：各门禁 QC、QC 决策、最终 QC。

## 1. 每个生产门禁执行 QC

### 资产 QC（Asset QC）

检查：

* 身份（identity）
* 视觉质量（visual quality）
* 解剖/肢体（anatomy）
* 风格（style）
* 参考保真（reference fidelity）
* 集内妆造细节（episode wardrobe）：款式 / 颜色 / 污渍位置 / 破损 / 配饰 / 发型 / 妆容与剧本一致；
  细节板（`*_detail`）不得被当作生成参考使用（`ai-video-director/references/21-episode-state-lock.md` §8）

### 关键帧 QC（Keyframe QC）

检查：

* 构图（composition）
* 角色（character）
* 场景（location）
* 道具（props）
* 灯光（lighting）
* 情绪（emotion）
* 相对位置关系（relative position，对照已批准的关系关键帧）
* 室内结构一致性（structural consistency，对照该朝向的全景锚点）
* 集内妆造一致性（对照本集妆造三视图：款式、污渍位置、配饰、伤痕；换装点是否切了锚点）
* 陈设在场（set dressing presence，对照集内场景状态图：该在的床 / 输液架 / 药碗在不在，有没有多出不该有的东西）

### 视频 QC（Video QC）

**先做组级验收（连拍组）**：切点数与设计一致、切点两侧 ±0.5s 三条主线不断、
后段镜（第 3/4 镜）无一致性衰减、裁切后逐镜时长偏差 ≤±15%、母版在 `_takes/` 且已裁切落库。
组级不成立 → 整组 `RETRY` / 缩组 / 二分拆组，**不要逐镜挑单镜毛病**
（判定与降级路径见 `ai-video-director/references/23-take-group-multi-shot.md` §8/§9）。

逐镜检查：

* 身份一致性（identity consistency）
* 运动质量（motion quality）
* 解剖/肢体（anatomy）
* 摄影机运动（camera movement）
* 物理（physics）
* 背景稳定性（background stability）
* 时间一致性（temporal consistency）
* 关系漂移（relationship drift：站位互换 / 越过地标 / 正反打两侧错位）
* 空间错乱（spatial mismatch：门窗家具位置跳变 / 反打两面墙对不上 / 光向反转）
* 妆造漂移（wardrobe drift：跨镜换外套 / 污渍左右跳位 / 配饰消失 / 发型妆容变化）
* 陈设缺位（set dressing lost：开头有床、后镜空房；椅子翻倍；道具状态与剧情不同步）
* 生成模式（frame_mode）：应为 `reference`（全能参考）；用了 `first` / `first_last` 须在 sidecar 有「首帧理由」
  或降级说明，否则按违规处理（判定见 `drama-production-playbook/references/03-seedance-best-practices.md` 规则 5）
* 音轨与配乐（audio / BGM）：无背景音乐、垫乐、旋律线与节奏鼓床；仅台词人声（台词镜）＋基础环境音＋动作触发音；无台词镜不得出现人声；未实际听验不得判 PASS，未验听记 `AUDIO_PENDING`（`generate_audio` 只控制整条音轨有无、不能单独去配乐，须正向前置禁乐＋负向音乐词双通道；模板见 prompt-optimizer §3.4 / §4.5）
* 台词同期（dialogue sync）：台词镜人声存在、逐字与 shots.md 一致、音色与 `anchor-voice` 相符、口型与音节对齐；
  缺人声 / 台词被改写 / 后期硬贴配音 → `RETRY`，不做后期配音补（见 `references/04-generation.md` §2.1）

### 连续性 QC（Continuity QC）

检查：

* 角色位置（character position）
* 屏幕方向（screen direction）
* 服装（costume：单集内款式、污渍位置、破损、配饰须与集内妆造锚点一致）
* 道具（props）
* 灯光（lighting）
* 时间（time）
* 环境（environment）
* 动作状态（action state：跨镜是否从同一拍点接续，有没有重演上一镜的动作）
* 表情与情绪（expression continuity：上一镜末帧的表情余势与本镜第 0 帧是否承接，有无无过渡的跳变）

**执行方法（不要只看单镜）**：配对播放「上一镜尾 1s + 本镜头 1s」循环，按
`ai-video-director/references/22-shot-continuity-in-generation.md` §2 的三条主线逐条看——
① 人物位置关系（在哪一侧、朝向、谁看谁、谁在前景）② 环境（陈设在场、光源方位、时段天气）
③ 动作与表情（动作在第几拍、姿态、表情余势），外加屏幕运动方向与声音。
单镜 QC 永远查不出这类问题——它是唯一必须成对复查的项。

发现断点时按主线定位：位置、朝向、光向类 → 改接续句与参考版本，**不要重抽卡**；
动作重演类 → 改接续句的动作拍点；表情断层类 → 改表情余势，或降为软接并补过渡动作；
妆造类 → 回 `21` 换锚点。

### 故事 QC（Story QC）

检查：

> 生成的镜头是否仍传达了导演想要的戏剧节拍（dramatic beat）？

## 2. QC 决策

使用：

```text
PASS（通过）
RETRY（重试）
REDESIGN（重设计）
HUMAN_REVIEW（人工审查）
```

**不要仅因为镜头好看就批准。**

一个视觉惊艳但未完成其叙事功能的镜头，就是失败镜头。

## 3. 最终 QC（Final QC）

只有当以下条件**全部成立**时，成品才可交付：

```text
故事正确（Story Correct）
AND
角色一致（Character Consistent）
AND
场景一致（Location Consistent）
AND
镜头意图正确（Shot Intent Correct）
AND
运动可接受（Motion Acceptable）
AND
音频同步（Audio Synchronized）
AND
连续性通过（Continuity Passed）
AND
技术要求通过（Technical Requirements Passed）
```

预算超支应被报告，但**不自动**使创意交付失效。

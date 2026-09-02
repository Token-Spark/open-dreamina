# 生产预算、粗剪、最终制作与人工升级

> 对应 SKILL.md 索引中的 `references/07-budget-and-delivery.md`。
> 追踪成本 / 进入制作交付时加载。包含：生产预算、粗剪、最终制作、人工升级。

## 1. 生产预算（Production Budget）

追踪：

* 预估成本（estimated cost）
* 实际成本（actual cost）
* 生成次数（generation count）
* 重试次数（retry count）
* 模型（model）
* 分辨率（resolution）
* 时长（duration）
* 处理时间（processing time）

按以下层级追踪成本：

```text
Episode（集）
Scene（场景）
Shot（镜头）
Asset（资产）
```

预算优先分配给：

* Hook
* 角色出场（Character introduction）
* 重大揭示（Major reveal）
* 情绪高潮（Emotional climax）
* 悬念（Cliffhanger）

**不要均匀分配生成预算。**

## 2. 粗剪（Rough Cut）

当已有足够已批准镜头时，组装粗剪。

评估：

* 故事清晰度（story clarity）
* 节奏（pacing）
* 镜头覆盖（shot coverage）
* 连续性（continuity）
* 缺失镜头（missing shots）
* 对白时机（dialogue timing）
* 情绪节奏（emotional rhythm）

**在粗剪通过之前，不执行昂贵的最终后期处理。**

## 3. 最终制作（Final Production）

粗剪批准后：

```text
Video Assembly（视频组装）
↓
Voice（配音）
↓
Lip Sync（口型同步）
↓
SFX（音效）
↓
Music（音乐）
↓
Color（调色）
↓
VFX（特效）
↓
Upscaling（超分）
↓
Subtitles（字幕）
↓
Mastering（母带制作）
↓
Final QC（最终质检）
```

## 4. 人工升级（Human Escalation）

以下情况升级到人工审查：

* 关键资产反复失败
* 核心角色变得不一致
* 无法生成重大故事镜头
* 生产意图含糊
* 模型限制阻碍忠实执行
* 超过重试上限
* 成本超过配置预算
* 连续性无法自动解决

**不要隐藏未解决的问题。**

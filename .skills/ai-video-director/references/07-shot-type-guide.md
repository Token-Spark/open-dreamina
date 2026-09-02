# 生成约束与镜头类型专项

> 对应 SKILL.md 索引中的 `references/07-shot-type-guide.md`。
> 设计具体镜头类型时加载。包含：动作复杂度控制、AI Video Shot 优先级、对白/情绪/动作/建立/主镜头/插入镜头。

## 1. 动作复杂度控制

AI 视频生成不擅长一次完成过多复杂动作。

优先：

> 一个镜头 = 一个主要动作。

例如不要：

> 人物奔跑 → 转身 → 拔枪 → 射击 → 跳跃 → 爆炸

拆成：

```text
Shot 01
奔跑

Shot 02
转身

Shot 03
拔枪

Shot 04
射击

Shot 05
爆炸
```

然后通过剪辑形成连续动作。

## 2. AI Video Shot 优先级

优先设计：

> Stable Composition

> Simple Motion

> Clear Subject

> Strong Silhouette

> Limited Character Interaction

> Controlled Camera Movement

避免单个生成镜头包含：

* 多人物复杂互动
* 多个快速动作
* 大量物体飞行
* 复杂手部操作
* 连续复杂表情变化
* 长时间镜头内状态变化

复杂戏剧通过：

> **多 Shot 剪辑**

实现，而不是强迫单个模型完成。

## 3. Dialogue Shot

人物对白优先采用：

> Shot / Reverse Shot

或者：

> OTS → CU → Reaction

例如：

```text
Shot 01
男主 MCU

Shot 02
女主 OTS

Shot 03
女主 CU

Shot 04
男主 Reaction CU
```

不要让两个角色长时间固定在一个镜头中说话。

## 4. Emotional Shot

情绪戏优先：

> 减少摄影机运动。

例如：

> CU + Static Camera

让：

> 演员表情

承担情绪。

## 5. Action Shot

动作戏优先：

> Short Shot + Clear Direction + Strong Composition

建立：

> Screen Direction

确保：

> 左 → 右

或者：

> 右 → 左

保持连续。

## 6. Establishing Shot

每个新地点第一次出现时，根据需要提供：

> Establishing Shot

作用：

> 告诉观众"我们在哪里"。

但不要滥用。

如果观众已经知道地点：

> 不需要每次重新 Establish。

## 7. Master Shot

复杂场景可以先建立：

> Master Shot

用于：

* 空间关系
* 人物位置
* 后续剪辑参考

然后再进入：

> Coverage

包括：

* CU
* MCU
* OTS
* Reaction
* Insert

## 8. Insert Shot

关键道具必须独立镜头。

例如：

> 手机

> 门锁

> 钥匙

> 血迹

> AI系统界面

> 子弹

> 手术刀

> 眼睛

Insert Shot 用于：

> 信息提示 / 节奏 / 悬念 / 转场
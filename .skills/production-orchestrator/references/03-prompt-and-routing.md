# Prompt 编译、模型路由与生成策略

> 对应 SKILL.md 索引中的 `references/03-prompt-and-routing.md`。
> 编译 Prompt / 选择模型时加载。包含：Prompt 编译、模型路由、生成策略。

## 1. Prompt 编译（Prompt Compilation）

**不新造创意 Prompt。** 把导演的意图编译成模型可执行的执行 Prompt。

保持以下层级：

```text
Story Intent（故事意图）
Visual Intent（视觉意图）
Character（角色）
Location（场景）
Composition（构图）
Camera（摄影机）
Lighting（灯光）
Motion（运动）
Style（风格）
Technical Parameters（技术参数）
```

- 前八层来自或必须忠于导演。
- 生产层可调整：
  - 模型语法（model syntax）
  - 参数语法（parameter syntax）
  - 负向 Prompt（negative prompts）
  - 参考语法（reference syntax）
  - 分辨率（resolution）
  - 时长（duration）
  - 帧率（frame rate）
  - seed
  - 控制强度（control strength）

**绝不为了迁就模型而改变戏剧含义。**

## 2. 模型路由（Model Routing）

按以下标准选择生成工具：

```text
quality（质量）
consistency（一致性）
prompt adherence（Prompt 遵循度）
speed（速度）
cost（成本）
availability（可用性）
task suitability（任务适配度）
```

**不要假设某个特定 provider / 模型总是可用。**

按任务独立选择模型：

* 角色图（character image）
* 环境图（environment image）
* 关键帧（keyframe）
* 图生视频（image-to-video）
* 文生视频（text-to-video）
* 数字人（talking head）
* 口型同步（lip sync）
* 配音（voice）
* 音乐（music）
* 音效（SFX）
* 超分（upscaling）
* 后期（post-production）

路由偏好：

- 对需要**强视觉身份与构图控制**的镜头，优先 **图生视频**。
- 对**不需要参考**或主要为**环境/抽象**的镜头，使用 **文生视频**。

## 3. 生成策略（Generation Strategy）

优先顺序：

```text
Character Assets（角色资产）
        ↓
Location Assets（场景资产）
        ↓
Hero Keyframes（主镜头关键帧）
        ↓
Normal Keyframes（常规关键帧）
        ↓
Video Shots（视频镜头）
        ↓
Voice / SFX / Music（配音/音效/音乐）
        ↓
Rough Cut（粗剪）
        ↓
Final Post（最终后期）
```

**不要盲目一次性生成整集。**

生成优先级：

1. Hook 镜头
2. 角色出场
3. 重大揭示
4. 情绪高峰
5. 悬念（Cliffhanger）
6. 常规叙事镜头
7. 插入镜头与背景镜头

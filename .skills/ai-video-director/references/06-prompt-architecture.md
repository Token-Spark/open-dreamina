# Prompt 架构与视频运动设计

> 对应 SKILL.md 索引中的 `references/06-prompt-architecture.md`。
> 为镜头编写生成 Prompt 时加载。包含：Prompt 架构、Image/Video Prompt 分离、Video Motion Design。

## 1. Prompt Architecture

不要直接生成一大段随机 Prompt。

采用：

> **[Style] + [Character] + [Location] + [Composition] + [Action] + [Camera] + [Lighting] + [Atmosphere]**

例如：

```text
STYLE:
cinematic science fiction thriller,
photorealistic,
high-end film production

CHARACTER:
CHAR-A,
young female scientist,
short black hair,
white research coat

LOCATION:
LOC-HOSPITAL-01

COMPOSITION:
medium close-up,
character positioned on right third,
large negative space

ACTION:
she slowly turns toward the emergency door,
eyes widening

CAMERA:
50mm lens,
eye-level,
slow push-in

LIGHT:
cold fluorescent light,
red emergency reflections

ATMOSPHERE:
quiet,
claustrophobic,
ominous,
subtle film grain
```

## 2. Image Prompt 与 Video Prompt 必须分离

### Image Prompt

重点：

> **画面是什么**

包括：

* 人物
* 场景
* 构图
* 光线
* 风格

### Video Prompt

重点：

> **画面如何变化**

包括：

* 人物动作
* 摄影机运动
* 环境变化
* 情绪变化
* 时间变化

禁止简单复制 Image Prompt。

## 3. Video Motion Design

每一个视频 Shot 必须明确：

```text
Initial State
Action
Camera Motion
Environmental Motion
End State
```

例如：

> Initial State:
> 女主站在手术室门前。

> Action:
> 她缓慢抬起右手。

> Camera:
> Camera slowly pushes in.

> Environment:
> 红色警报灯持续闪烁。

> End State:
> 她的手停在门锁上。

这样比：

> "cinematic dramatic movement"

更适合视频模型。

## 4. Video Prompt 生成模板

在输出逐镜头 Video Prompt 时，必须使用以下结构化模板：

```text
镜头功能：[对话/情绪/动作/建立/主镜头/插入镜头]，[固定/推/拉/摇/移/跟/升降]
人物：[引用 Character Lock ID，如 CHAR-A、CHAR-B]
场景描述：[引用 Location Lock ID，补充该镜头特定场景细节]
秒级动作拆解：
- [起止时间]：[人物/环境动作描述]；运镜：[摄影机运动描述]
台词同步：[起止时间]：
- [人物]（语速 [x] 字/秒，台词："[具体台词内容]"）
人物关系位置：[人物之间的相对位置与朝向，如：A 在画面左1/3侧身朝右，B 在画面右1/3正面对A]
空间关系位置：[人物与环境的相对位置，如：A 站在门边，B 坐在桌后]
光感：[光源方向/类型/强度，如：左侧窗光，柔光，中亮度]
色调：[整体色彩倾向，如：冷蓝调，低饱和]
构图：[景别 + 构图方法，如：中近景，三分法，A 占画面左2/3]
细节：[需要特别关注的视觉细节，如：A 右手指尖微颤，B 眼神回避]
音效设计：[有无背景音乐，如：无背景音乐]
基础环境音：[持续存在的环境声，如：空调低频嗡鸣]
动作触发音：[由动作触发的声音，如：脚步声、门把手转动声]
特效音：[非写实的强调音，如：心跳放大、耳鸣高频]
```

### 模板使用规则

1. **秒级动作拆解**必须覆盖镜头完整时长，时间段不得有间隔或重叠。
2. **台词同步**的时间段必须与秒级动作拆解对齐；无台词的时间段标注 `无台词`。
3. **人物关系位置**与**空间关系位置**必须与一致性资产（Character Lock / Location Lock）保持连续性。
4. **音效设计**三要素（基础环境音 / 动作触发音 / 特效音）缺一不可，即使为 `无` 也必须显式标注。
5. 所有字段禁止留空；确无内容的字段填写 `无` 或 `N/A` 并说明原因。
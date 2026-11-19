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
young female scientist

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

> **进入 Open Dreamina 管线时的两处收口**：
> ① CHARACTER 段只写身份项（英文名 / `@char_*` 锚点 + 本镜身体与表演状态），
> **不写发型、服饰、妆容**——它们由本集妆造三视图 `char_*_ep{xx}_{造型}_turnaround` 承载，
> 文字与参考图会各取一半（款式对、污渍换位，或整套换掉），见 `21` §5、§6。
> ② STYLE / ATMOSPHERE 属全局风格常量，从 manifest 的 `style` 字段逐字引用，不逐镜改写；
> 资产 ID 用 manifest 的 `char_*` / `scene_*` / `prop_*`，不要另造 `CHAR-A` 这类临时编号。
> 本节的 8 段顺序是**管线外**（素材级 / 独立出图）的写法；管线内镜头提示词的段序由
> `drama compile` 固定为 8 段，见 `prompt-optimizer/references/drama-prompt-pattern.md`。

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

## 4. Video Prompt 字段清单（拆镜思考用）

> **成稿不按这张表。** 交付给生成层的逐镜提示词一律按
> `prompt-optimizer/references/02-prompt-templates.md` §3.4 的九行模板（用户定稿，唯一版本）。
> 本节这张表是**拆镜时的检查清单**——比九行模板多出人物关系位置 / 空间关系位置 / 光感 / 色调 / 构图 / 细节，
> 用来确认「这一镜的空间关系、光色、构图是否想过」。这些信息在 `shots.md` 里落到总览表列与 sidecar，
> 在九行模板里不单列；不要把它们塞进九行模板，否则就是自创字段。

拆镜时逐项自问（填中文即可，不必成稿）：

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

### 检查规则

1. **秒级动作拆解**必须覆盖镜头完整时长，时间段不得有间隔或重叠。
2. **台词同步**的时间段必须与秒级动作拆解对齐；无台词的时间段标注 `无台词`。
3. **人物关系位置**与**空间关系位置**必须与一致性资产（Character Lock / Location Lock）保持连续性。
4. **音效设计**相关项（基础环境音 / 特效音）缺一不可，即使为 `无` 也必须显式标注；
   动作触发音并入基础环境音（九行模板口径）。
5. 所有字段禁止留空；确无内容的字段填写 `无` 或 `N/A` 并说明原因。
# 一致性与锁定：Continuity / Character Lock / Location Lock / Visual Bible

> 对应 SKILL.md 索引中的 `references/05-continuity-and-lock.md`。
> 建立全片一致性资产时加载。包含：连续性原则、角色锁定、场景锁定、视觉圣经。

## 1. Continuity

必须维护：

### Character Continuity

包括：

* Face
* Hair
* Age
* Body
* Clothing
* Accessories
* Makeup
* Injuries

> **单集内的一致性必须单独锁定**：衣物款式、污渍位置、破损、配饰、妆容在同一集内不得漂移；
> 场景同理（开头卧病在床，中段人物再入画时床、输液架、药碗必须仍在该位置）。
> 跨集 Lock 只锁「这个人是什么样」，锁不住「本集此刻是什么样」——见 §2.1 与 `21`。

### Environment Continuity

包括：

* 建筑
* 天气
* 时间
* 光线
* 道具
* 空间结构

### Action Continuity

包括：

* 人物站位
* 手的位置
* 身体朝向
* 道具位置
* 动作开始 / 结束状态

## 2. Character Lock

每一个主要角色必须建立：

```text
Character ID
Face Reference
Body Reference
Hair
Costume
Accessories
Color Palette
Age
Physical Traits
Expression Range
Movement Style
```

所有后续 Prompt 都必须引用：

> Character ID

而不是每次重新描述人物。

### 2.1 Episode State Lock（集内状态锁定）

Character Lock 是跨集的身份事实源，它覆盖不到「本集这一场他穿什么」。
单集内换装、染血、受伤、湿身、卸妆，以及本集独有的陈设，必须再加一层单集粒度的锁：

```text
Episode
Wardrobe（款式 / 颜色 / 面料）
Makeup
Stains & Damage（位置写死：左袖口内侧、右膝）
Accessories
Hair
Set Dressing（本集陈设与在场道具）
Change Points（本集第几镜起变化，变化前后各一套）
Version
```

落地纪律：

- 产物是**本集妆造三视图** `char_{角色}_ep{xx}_{造型}_turnaround` 与**集内场景状态图**
  `scene_{场景}_ep{xx}_{状态}`，都从 primary 派生，不重新文生图。
- 妆造 / 陈设一经图片锁定，**提示词只引用、不描述**：写「与参考图一致」+ 本镜动作，
  不再写「白色睡裙、左袖咖啡渍」。文字与参考图冲突时模型会各取一半，污渍换位、款式漂移。
- 生成参考与首帧只用 `*_turnaround`；**半身照、剧照、成片截帧不得作种子**，
  单角度素材一转视角就换脸换衣服。
- 触发条件、产物分工、生成顺序、门禁与 QC 见 `21-episode-state-lock.md` §2–§8。

## 3. Location Lock

**室内多角度场景先建布局/全景锚点**：一张 primary 只覆盖一个朝向，反打会换墙；
触发条件、全景锚点组与朝向映射见 `20-indoor-layout-anchor.md` §2/§3/§5。

每一个主要场景建立：

```text
Location ID
Architecture
Layout
Materials
Color
Lighting
Time
Weather
Key Props
Camera Restrictions
Visual Motifs
```

例如：

```text
LOC-HOSPITAL-01
地下 AI 医院
冷白色金属墙面
低照度
绿色医疗屏幕
中央手术舱
大量透明玻璃
无自然光
```

## 4. Visual Bible

每个项目必须定义：

### Color

例如：

> 冷蓝 + 黑 + 少量红色警示

### Lighting

例如：

> Low-key cinematic lighting

### Texture

例如：

> realistic skin + subtle film grain

### Camera

例如：

> anamorphic cinematic photography

### Lens

例如：

> 35mm / 50mm / 85mm

### Aspect Ratio

例如：

> 16:9

### Visual Reference

建立：

> Master Style Prompt

所有生成镜头共享。
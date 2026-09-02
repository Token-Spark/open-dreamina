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

## 3. Location Lock

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
# 12 角色设定卡与设定图四件套

> 契约 #24 的 owner（登记见 `10-contract-owners.md`）。
>
> **角色身份先有一张卡，再有一张脸。** 设定卡是角色身份的文字事实源，
> 四件视觉产物是它的图像投影；后续所有资产生成（三视图、集内妆造、关系帧、
> 视频提示词）都从卡与四件派生，不再各写各的人物描述。
>
> 与 `11-voice-anchor.md`（契约 #23）并列互补：`11` 管声音必备件与台词镜 `BLOCKED`
> 硬门禁，**本文件管视觉设定层与素材人工验收**。三件套口径不因本文件改变。

## 1 为什么需要设定卡

没有卡时的三类高频故障：

| 现象 | 根因 |
|---|---|
| 同一角色换造型后辨识特征消失（发光发饰、义眼、疤痕不见了） | 身份级特征与造型级服装混写在一段描述里，换装时被整段替换 |
| 特写、三视图、关系帧里的人「像三个人」 | 各产物独立文生图，没有共同的文字事实源与派生链 |
| 表演提示词每镜现编表情词，情绪跨度前后不一 | Expression Range 只是 Lock 里的一个字段名，没有具象产物 |

结论：**身份级（跨造型不变）与造型级（随剧情变）必须分层**——
辨识特征进身份层，着装描述进造型层，两层都写在卡里，生成时按层取用。

## 2 设定卡（character-card.md）

落盘位置：`素材库/01_characters/{角色小写}/character-card.md`（与该角色四件产物同目录）。
剧作层出初稿（见 `short-drama-creator/references/character-design.md`），资产层校准定稿。
**卡不入 assets_manifest**（它是文字事实源，不是生成资产）；四件图各登记一条（§6）。

### 2.1 模板

```markdown
# {角色名} 设定卡

## 人物属性
| 字段 | 值 |
|---|---|
| 类别 | {角色定位：主角 / 对手 / 盟友 / 功能性；可空} |
| 纪元 | {世界观时代：科幻 / 民国 / 古代 / 现代 …} |
| 性别 | |
| 年龄 | {青年 / 中年 / 少年 …，可附具体岁数} |
| 身材 | {纤细 / 魁梧 / 娇小 …} |
| 物种 | {人类 / 精灵 / 仿生人 …} |
| 发色 | |
| 发长 | {长发 / 短发 / 及腰 …} |
| 场景 | {题材标签：时空穿越 / 宫廷 / 校园 …} |

## 辨识特征（跨造型不变项）
- {特征 1：位置 + 颜色 + 材质写死，如「长发中编织细小发光二极管，如繁星点点」}
- {特征 2 …}

## 着装描述（按造型分节）
### 默认造型（PRIMARY）
{形制 + 材质 + 配色 + 配饰，一段写全}
### {EP段或 EPxx}_{造型名}
{该造型的着装描述；与默认造型的差异项}

## 表情谱（3×3 行序 → 情绪）
| 格位 | 情绪 | 格位 | 情绪 | 格位 | 情绪 |
|---|---|---|---|---|---|
| 1 | 中性 | 2 | 微笑 | 3 | 开怀 |
| 4 | 愤怒 | 5 | 悲伤 | 6 | 克制惊讶 |
| 7 | 恐惧 | 8 | 轻蔑 | 9 | 疲惫 |

## 管线绑定
- 英文名 / `char_*` 前缀：{如 venus → char_venus_*}
- 音色：voice_{角色}（anchor-voice.wav，见 `11-voice-anchor.md`）
- 弧光卡：{分集剧本或剧作文档中的弧光卡位置}
- 造型 → 三视图对照：
  | 造型 | 三视图 asset_id | 适用集段 |
  |---|---|---|
  | 默认 | char_{角色}_primary 派生首套 *_turnaround | EP01-xx |
```

### 2.2 填写口径

- **人物属性九字段照搬参考框架**，逐字段填，不留空段（无值写「—」）。
  「场景」是**题材标签**，不绑 `scene_*` 资产——实际场景绑定走 `shots.md` 资产绑定行。
- **辨识特征 = 身份级不变项**：每条写清位置 / 颜色 / 材质，可指认、可核对。
  每造型三视图与四件产物都必须保留；换造型不得丢。条数宁少勿滥（1–4 条强特征）。
- **着装描述 = 造型级**：按造型分节，默认造型必填，其余造型随剧情增补。
  只在**生成该造型锚点时**把服装写死一次（`21` §4/§5）；锁定后提示词只引用不描述。
- **表情谱**：默认九情绪（中性/微笑/开怀/愤怒/悲伤/克制惊讶/恐惧/轻蔑/疲惫），
  可按剧集情绪谱替换格位，但**惊讶格一律克制版**（`24` §1/§2，禁倒吸气三件套）。
  行序即表情九宫格的格位顺序（从左到右、从上到下），改谱必须同步重出表情格。

## 3 四件视觉产物（规格与命名）

| 产物 | 文件名 | 规格 | 是否进生成参考 |
|---|---|---|---|
| **特写**（= 基准肖像） | `{角色大写}_PRIMARY_anchor-portrait.png` | 胸部以上正面、中性表情、纯色背景、固定 seed；一切人物变体的 img2img 源 | 作 img2img 基准；**不作视频参考/首帧** |
| **立绘** | `{角色大写}_PRIMARY_fullbody.png` | 全身正面站姿定妆，头到脚完整，纯色背景；与 halfbody 同为三视图 img2img 基准（**优先 fullbody**） | 作 img2img 基准；**禁作视频种子/参考/首帧**（单角度纪律） |
| **表情九宫格** | `{角色大写}_PRIMARY_expressions.png` | 3×3 同脸九情绪，格位=卡内表情谱行序；同发型同服装（默认造型） | **否**：拼贴板禁进参考；供表演选词与人工核对 |
| **三视图** | `{角色大写}_{EP段}_{造型}_turnaround.png` | 正/侧/背全身；规格与骨架见 `21` §4 | **是**：视频与关键帧唯一人物参考入口 |

- 特写即既有基准肖像，本表只是明确其构图规格；**存量项目肖像不强制重出**。
- 立绘 / 表情格默认造型各一张即可：**表情格跨造型通用**（锁的是脸与情绪跨度，不是衣服）；
  造型版立绘可选（`{角色大写}_{EP段}_{造型}_fullbody.png`）。
- 命名与目录归 `05-asset-naming-convention.md`；本表是四件产物的规格 owner。

## 4 生成顺序

```text
设定卡（剧作层初稿 → 资产层校准定稿）
  → 特写（文生图，固定 seed）
  → 立绘（img2img ← 特写）
  → 三视图（img2img ← 特写/立绘；着装描述写死一次）
  → 表情九宫格（img2img ← 特写）
  → 音色 anchor-voice.wav（与三视图同批次，见 11）
  → 素材审阅中心人工验收（卡 + 四件 + wav 一起审）
```

- img2img strength 区间与固定 seed 纪律见 `04-consistency-strategy.md` 第 2 层（数值只改一处）。
- 三视图骨架见 `21` §4：首套跨集版同骨架，服装段取**卡内默认造型着装描述**。
- 顺序不可颠倒：卡未定稿不出特写，特写未批准不派生其余三件。

## 5 提示词骨架（卡字段驱动）

三段骨架均**尾部逐字拼接风格四常量**（`04` 第 1 层 / `drama-prompt-pattern.md`）。
`{}` 内取卡字段值；骨架标签与段序不可改，只填值。

### 5.1 特写（文生图，固定 seed）

```text
character reference portrait, chest-up, front-facing, neutral expression,
{性别} {年龄} {物种}, {身材} build, {发色} {发长} hair,
{辨识特征逐条，位置/颜色/材质},
plain solid background, soft even lighting, sharp facial details,
no text, no watermark
```

### 5.2 立绘（img2img ← 特写）

```text
full-body character concept art, front-facing standing pose, head to toe visible,
same face and hair as the reference portrait,
{默认造型着装描述：形制/材质/配色/配饰},
{辨识特征逐条},
plain solid background, even lighting, full outfit clearly visible,
no text, no watermark
```

### 5.3 表情九宫格（img2img ← 特写）

```text
3x3 grid expression sheet of the same character, nine head-and-shoulders portraits,
identical face, hairstyle and default outfit in every cell,
expressions left-to-right top-to-bottom: {卡内表情谱九情绪，逗号分隔},
the surprise cell is restrained: slight eye widening, held breath, no gasp,
plain solid background, consistent lighting across cells,
no text, no watermark, no grid labels
```

- 直出九宫格失败（格间串脸 / 情绪不可辨）→ 降级**逐格生成**：同参考同 seed 出九张，
  ffmpeg xstack 拼 3×3；拼贴板仍**不进生成参考**。
- 惊讶格措辞遵守 `24` §3：正向写克制 + 负面词排除 `gasp, sharp intake of breath`。

## 6 登记与代码边界

- 四件图各在 `tools/assets_manifest.json` 登记一条：特写 text2img 必填 prompt + 固定 seed；
  立绘 / 表情格 / 三视图 img2img 必有 `reference_primary` 指向特写（登记规则见 `05`）。
- **新产物不进 shots.md 资产绑定、无新 asset_id 前缀**：`ASSET_ID_RE` 白名单
  （`char|scene|prop|crowd|icon|voice`，`drama/qc/audit_refs.py`）与角色槽
  `CHARACTER_SLOT_TURNAROUND_ONLY`（`drama/parser/shots_parser.py`）不改——
  视频参考仍只认 `*_turnaround`，立绘/表情格天然被过滤，这正是我们要的。
- 卡是 markdown 文字事实源，不入 manifest、不被 lint 检查；**机器检查不覆盖卡**，
  卡的完整性靠 §7 人工验收。

## 7 验收清单（素材人工验收）

**设定卡**：
- [ ] 九字段齐全（无值写「—」），辨识特征 1–4 条且位置/颜色/材质可指认
- [ ] 着装描述按造型分节，默认造型必填；表情谱行序明确

**四件产物**：
- [ ] 四件同脸（与特写一致），辨识特征跨四件一致，无文字水印
- [ ] 立绘头到脚完整、正面站姿；表情格九格同脸同发型同服装、格位与卡内表情谱一致、惊讶格克制
- [ ] 三视图三面齐全（验收细则见 `21` §8）

**门禁**：
- **主要角色**：卡 + 四件 + 音色缺任何一件 → 素材人工验收**不通过**，回素材阶段补齐。
- **过场角色**（纯特写 / 仅 1 镜且无近景，对齐 `21` §2 豁免口径）：豁免立绘与表情格；
  **设定卡仍必填**（文字成本低，是选角与一致性核对的依据）。
- **台词镜 `BLOCKED` 硬门禁仍只按三件套口径**（契约 #23，`11` §6）：本文件不新增
  机器 BLOCKED 条件；立绘/表情格缺失拦在人工验收，不拦生成任务状态机。

## 8 与其他文件的关系

- 卡字段模板、四件规格、生成顺序、提示词骨架、验收归**本文件**（契约 #24）。
- 命名与目录归 `05`；img2img 纪律与风格常量归 `04`；三视图骨架与种子纪律归 `21`。
- 音色必备件与 `BLOCKED` 归 `11`（契约 #23）；表演禁忌与克制惊讶归 `24`。
- 剧作层如何从六要素推导辨识特征与着装：`short-drama-creator/references/character-design.md`。
- Character Lock 字段（Expression Range / Physical Traits）的具象落地：本文件四件产物。
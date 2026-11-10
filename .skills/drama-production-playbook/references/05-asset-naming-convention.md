# 05 资产命名规范与素材库目录

> 命名即元数据：从文件名就能读出「角色 / 时期 / 造型 / 类型」。
> 素材 ID（manifest 里的 id）与文件名一一对应，贯穿分镜绑定、规格、注册表。

## 素材库目录结构

```
素材库/
├── 01_characters/{角色}/      # 人物（角色子目录小写：venus / hera / ...）
├── 02_scenes/{场景}/          # 场景（forge / olympus_hall / ...）
├── 03_props/props/            # 道具（统一目录）
├── 04_iconic_scenes/          # 名场面
├── 05_index/                  # primary_asset_ids.json + generation_report.json
├── 06_bgm/                    # BGM 风格卡（{编号}_{风格}_{曲名}.mp3，后期用）
└── 06_voiceover/{EPxx}/       # 画外音成片（仅旁白 / 画外音；台词在生成期同期产出）
```

数字前缀即审阅中心呈现顺序；目录层级会完整出现在素材审阅条目的相对路径里。

## 人物命名

```
{角色大写}_{时期/造型}_{类型}.png
```

| 后缀 | 含义 | 用途 |
|---|---|---|
| `_PRIMARY_anchor-portrait.png` | 基准肖像锚点（固定 seed） | 一切人物变体的 img2img 源 |
| `_PRIMARY_anchor-voice.wav` | 音色锚点（5s） | 生成期台词的音色参考（不做后期配音；画外音 TTS 选角同用） |
| `_{EP段}_{造型}_halfbody.png` | 半身像 | 仅作三视图的 img2img 基准，**禁止作种子 / 参考 / 首帧** |
| `_{EP段}_{造型}_turnaround.png` | 三视图（正/侧/背全身） | **视频与关键帧唯一人物参考入口** |
| `_{EPxx}_{造型}_detail.png` | 妆造细节板（污渍 / 破损 / 配饰特写，可选） | 人工逐镜核对用，**不进生成参考** |

示例：`VENUS_PRIMARY_anchor-portrait.png`、`VENUS_EP01-10_white-gown_halfbody.png`、
`VENUS_EP21-30_rosegold-queen_turnaround.png`、`LIN_EP07_hospital-gown_turnaround.png`。

集段口径：`EP段` 可跨集（`EP01-10`），也可单集（`EP07`）。**单集内换装 / 染血 / 受伤 /
卸妆**必须落到单集粒度，即集内状态锚点，见
`ai-video-director/references/21-episode-state-lock.md` §2/§3。

> 种子纪律：只有 `*_turnaround` 能进生成参考。半身照、单张剧照、上一版成片截帧、
> 多图拼贴板（`_detail`、布局总览、九宫格）一律不得作种子——单角度素材一转视角就漂移。

## 场景 / 道具 / 名场面命名

```
{场景大写}_PRIMARY_{exterior|interior}.png     # 锚点必须标 PRIMARY
{场景大写}-{变体}_{exterior|interior}.png      # 变体（如 OLYMPUS-HALL-FESTIVAL）
{场景大写}_EP{xx}_{状态}_{interior}.png        # 集内陈设状态（SICKBED / FUNERAL / RAIN）
PROP_{道具}.png                                # 道具统一前缀
PROP_{道具}_{状态}.png                         # 道具状态变体（撕破 / 碎裂）
EP{xx}_{描述}.png                              # 名场面（如 EP26_return-through-doors.png）
```

## 资产 ID 命名（manifest / 分镜绑定用）

```
char_{角色}_{时期}_{造型}_turnaround   → 01_characters/{角色}/同名.png
char_{角色}_ep{xx}_{造型}_turnaround   → 集内妆造三视图（单集锁定，视频参考入口）
char_{角色}_primary                    → 基准锚点
voice_{角色}                           → anchor-voice.wav（无需 manifest 条目）
scene_{场景}_primary / scene_{场景}_interior
scene_{场景}_ep{xx}_{状态}             → 集内场景状态图（本集陈设：病床 / 灵堂 / 雨夜）
prop_{道具}                            → 03_props/props/PROP_*.png
prop_{道具}_{状态}                     → 道具状态变体（prop_letter_torn）
icon_ep{xx}_{描述}                     → 04_iconic_scenes/
```

约定：全小写 + 下划线；`char_*` 的角色段必须能被 CHARACTER_ALIASES 归属到角色名
（角色资产与角色名/音色的自动配对依赖它）。

> **集内锚点必须寄生在白名单前缀里**（`char_` / `scene_` / `prop_`）。`ASSET_ID_RE` 只认
> `char|scene|prop|crowd|icon|voice`，发明 `state_*` / `wardrobe_*` / `look_*` 会被
> `drama spec` 静默过滤、`drama assets` 审计看不见，等于未登记。
> 例外只有 `rel_*` / `loc_*`（手工组装多参考），见 `ai-video-director/references/19-relationship-keyframe.md` §8。

## manifest 登记规则

- 每个素材一行 assets 条目：id / category / group / mode / filename / prompt（+ seed）
- text2img 必填 prompt；img2img 必有参考锚点（reference_primary / reference_primaries /
  self_reference / use_style_reference 之一）
- primary 锚点必须固定 seed；`drama manifest` 命令校验
- 平台 asset_id 上传后登记到 `tools/asset_registry.json`（或 05_index 的两个文件）

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
└── 06_voiceover/{EPxx}/       # 画外音成片
```

数字前缀即审阅中心呈现顺序；目录层级会完整出现在素材审阅条目的相对路径里。

## 人物命名

```
{角色大写}_{时期/造型}_{类型}.png
```

| 后缀 | 含义 | 用途 |
|---|---|---|
| `_PRIMARY_anchor-portrait.png` | 基准肖像锚点（固定 seed） | 一切人物变体的 img2img 源 |
| `_PRIMARY_anchor-voice.wav` | 音色锚点（5s） | 视频音色参考 / TTS 选角 |
| `_{EP段}_{造型}_halfbody.png` | 半身像 | 生成三视图的 ref 基准 |
| `_{EP段}_{造型}_turnaround.png` | 三视图（正/侧/背） | **视频参考唯一入口** |

示例：`VENUS_PRIMARY_anchor-portrait.png`、`VENUS_EP01-10_white-gown_halfbody.png`、
`VENUS_EP21-30_rosegold-queen_turnaround.png`。

## 场景 / 道具 / 名场面命名

```
{场景大写}_PRIMARY_{exterior|interior}.png     # 锚点必须标 PRIMARY
{场景大写}-{变体}_{exterior|interior}.png      # 变体（如 OLYMPUS-HALL-FESTIVAL）
PROP_{道具}.png                                # 道具统一前缀
EP{xx}_{描述}.png                              # 名场面（如 EP26_return-through-doors.png）
```

## 资产 ID 命名（manifest / 分镜绑定用）

```
char_{角色}_{时期}_{造型}_turnaround   → 01_characters/{角色}/同名.png
char_{角色}_primary                    → 基准锚点
voice_{角色}                           → anchor-voice.wav（无需 manifest 条目）
scene_{场景}_primary / scene_{场景}_interior
prop_{道具}                            → 03_props/props/PROP_*.png
icon_ep{xx}_{描述}                     → 04_iconic_scenes/
```

约定：全小写 + 下划线；`char_*` 的角色段必须能被 CHARACTER_ALIASES 归属到角色名
（角色资产与角色名/音色的自动配对依赖它）。

## manifest 登记规则

- 每个素材一行 assets 条目：id / category / group / mode / filename / prompt（+ seed）
- text2img 必填 prompt；img2img 必有参考锚点（reference_primary / reference_primaries /
  self_reference / use_style_reference 之一）
- primary 锚点必须固定 seed；`drama manifest` 命令校验
- 平台 asset_id 上传后登记到 `tools/asset_registry.json`（或 05_index 的两个文件）

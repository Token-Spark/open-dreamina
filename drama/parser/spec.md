# 分镜脚本格式规范（shots.md）

> 本文件是 `opendreamina drama lint` 的校验依据摘要；项目内会随脚手架生成
> 同内容规范到 `{项目根}/分镜脚本/_SPEC_分镜模板规范.md`（`_` 前缀目录约定：
> 审阅中心扫描自动跳过，供人与 AI 随时查阅）。

## 1. 三级剧本体系

| 层级 | 文件 | 检查方式 |
|---|---|---|
| 第 1 级 剧本大纲 | `剧本大纲.md` | 人工确认 |
| 第 2 级 分集剧本 | `分集剧本/分集剧本_EPxx-xx.md` | 人工确认 |
| 第 3 级 分镜脚本 | `分镜脚本/EPxx/shots.md` | 机器检查（`opendreamina drama lint`） |

## 2. shots.md 固定结构

1. 一级标题：`# EPxx · 集名`
2. 集信息：时长 / 镜头数 / 画幅 / 场景 / 核心情绪
3. 生产说明：全局风格常量（AESTHETIC / MEDIUM / AUDIO / NEGATIVE）、
   音频约定（只剔 BGM，禁止整体静音）、资产绑定说明
4. 总览表（15 列）：镜号 / 时长 / 景别 / 机位 / 运镜 / 构图 / 动作 / 表情 /
   灯光 / 色调 / 环境 / 声音 / 台词 / 特效 / 衔接
5. 逐镜头提示词块：每镜一个 `## EPxx-SNN`
6. 质检清单

## 3. 单镜必填行（顺序即模板）

```
**镜头功能：**  对话 / 反应 / 建立 / POV / 反转 …
**资产绑定：**  角色：char_xx_turnaround ｜ 场景：scene_xx ｜ 道具：prop_xx ｜ 音色：voice_xx
**人物：**      英文名（英文外观锚点，逐字；不入画角色标注「不入画」）
**场景描述：**  场景锚点："英文场景锚点，逐字"
**秒级动作拆解：**
- 0-4s：动作（含运镜说明）
**台词同步：**
- 说话人（语气：沙哑、哽咽、誓言，语速 2.5 字/秒，台词："英文台词逐字"）
**光感：** **色调：** **构图：** **细节：**
**音效设计：** 无背景音乐
**基础环境音：** **动作触发音：** **特效音：**
```

## 4. 硬性规则（lint errors）

- 镜头数 18（±1）；单镜 2-8s；总览表时长合计 = 目标集时长（默认 90s）
- 每镜必填行齐全；总览表 15 列齐全
- 禁止相对引用（「同上」）——外观锚点与场景锚点必须逐字写全
- 台词逐字引用分集剧本，写在引号内（英文/中文引号均可）

## 5. 质量建议（lint warnings）

- 单镜 >6s：多人/长台词镜头建议 ≤6s（多人镜头与超长台词是生成错误重灾区，
  必须多人时提供空间参考素材）
- 每集至少 1 个 POV 主观镜头（沉浸感）
- 摄影取值使用规范枚举（未收录写法编译时丢弃）：
  - 景别：`wide` / `medium` / `close_up` / `extreme_close_up` / `full` / `medium→close_up` / `wide→medium`
  - 机位：`eye-level` / `low-angle` / `high-angle` / `slight-high` / `slight-low` / `overhead` / `ground-level` / `handheld`
  - 运镜：`static` / `slow-push` / `slow-pull` / `slow-pan` / `slow-tilt-up` / `slow-tilt-down` / `handheld-sway` / `follow` / `quick-pan` / `slow-motion` …
- 表情词在 `tools/maps.py` 的 `EXPRESSION_MAP` 收录（未命中按无表情处理）
- 台词行写「语气：」段（、分隔短语，收录进 `TONE_MAP`）——语气/语速是编译后
  delivery 指令的唯一来源，缺失时模型只会平读台词（念白平淡的直接原因）
- 人物资产只绑三视图（`*_turnaround`）；半身照/种子图不进视频参考
- 心理活动 / 对话画面：人物占画面 75% 以上，减少背景描写

## 6. 资产 ID 命名

```
char_{角色}_{时期}_{造型}_turnaround   # 视频参考唯一入口
char_{角色}_PRIMARY_anchor-portrait    # 角色基准锚点（固定 seed）
char_{角色}_{时期}_{造型}_halfbody     # 生成三视图的 ref 基准
voice_{角色}                           # 音色引用（映射 anchor-voice.wav）
scene_{场景}_primary / scene_{场景}_interior
prop_{道具}                            # 文件名 PROP_*.png
icon_ep{xx}_{描述}                     # 名场面
```

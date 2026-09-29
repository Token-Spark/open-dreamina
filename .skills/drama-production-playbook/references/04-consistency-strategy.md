# 04 四层锚点一致性策略

> 一致性不是生成出来的，是**锚定**出来的。四层锚点从风格到镜头逐层收窄自由度。
> 落库位置：`tools/assets_manifest.json` 的 `consistency_strategy` 字段（init 模板已内置骨架）。

## 第 1 层：风格锚点（全集统一）

所有生成（素材图 + 视频）尾部逐字拼接 style 四常量：

- `AESTHETIC`（美学基调）+ `MEDIUM`（媒介质感）→ 正向尾部
- `NEGATIVE`（负面词）→ 负面提示词
- `AUDIO`（音频约定）→ 提示词内的音频指令段

纪律：**逐字复用，禁止逐镜改写**。要换风格 = 改 manifest 一处 + 全量重生成预览镜验证。
`drama compile --with-style` 会自动追加（style 读 manifest，maps.py 的 STYLE 兜底）。

## 第 2 层：角色锚点（每角色一张 primary）

- 每角色**仅一张** primary 基准肖像，固定 seed（如 10001）——身份的唯一事实源
- 所有变体（半身像、三视图、多时期造型）以 primary 作 img2img 重绘
  （strength 0.45-0.75，脸部特征锁死，只改服装/时期）
- 视频生成**一律绑 `*_turnaround` 三视图**（正/侧/背全身，各角度一致性）；
  halfbody 只作三视图的生成基准，不直接进视频参考
- 音色同样锚定：每角色一个 `anchor-voice.wav`（5 秒），TTS 选角记入 voice_manifest

多时期角色（如维纳斯 4 个时期）：每时期一套 `halfbody + turnaround` 配对，
按集段严格选用；基准脸不变，只变服装发型。

## 第 3 层：场景锚点（每场景一张 primary）

- 每场景**仅一张** primary 外观图（固定 seed）
- 内景 / 变体（节庆态、夜晚态）以 primary 重绘派生
- 视频中场景参考只绑 primary 或其直接派生图；提示词中**减少环境文字描写**
  （让参考图说话，文字只做「same as the scene reference image」锚定）

## 第 4 层：名场面合成（双参考）

关键爆点镜头同时引用：角色 primary/turnaround + 场景 primary 双重参考，
必要时叠加道具特写。名场面图（icon_epxx_*）本身也是双参考 img2img 的产物。

## 一致性故障排查顺序

1. 检查引用环节：`drama assets EPxx` ——引用是否落到正确素材与 asset_id？
2. 检查锚点链：该资产是否从 primary 派生（而非 text2img 直出）？
3. 检查提示词：风格常量是否逐字拼接？是否混入改写的锚点？
4. 检查分镜本身：是否踩了 03 号文件的多人/运镜/时长红线？
5. 都没问题 → 才按生成随机性处理（重roll / 加参考 / 拆镜）。

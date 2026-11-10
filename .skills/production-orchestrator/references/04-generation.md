# 关键帧门禁、视频生成与参考传播

> 对应 SKILL.md 索引中的 `references/04-generation.md`。
> 生成关键帧 / 视频时加载。包含：关键帧门禁、视频生成、参考传播。

## 1. 关键帧门禁（Keyframe Gate）

**第 0 步（硬门禁）**：命中多人 / 人物-场景共现 / 共享站位正反打 / 室内跨 ≥2 机位时，
须有已批准且版本 / 朝向正确的 `rel_*` / `loc_*` 锚点；触发条件与判定见
`ai-video-director/references/19-relationship-keyframe.md` §2/§6 与 `20-indoor-layout-anchor.md` §2/§7。
任一不满足 → 任务标记 `BLOCKED`（状态机见本技能 `references/production-schema.md`），
不得进入下面的流程，也不得靠反复生成视频绕过。

对重要镜头：

1. 生成关键帧。
2. 按本技能 `references/06-quality-control.md` §1「关键帧 QC」逐项校验。
3. 批准后再生成视频。

**关键帧失败则修关键帧。**

不要试图通过反复生成视频来解决坏关键帧。

### 1.1 接续门禁（Continuity Gate，硬，先于任何非首镜生成）

关键帧保证「这一镜本身对」，接续门禁保证「它接得上上一镜」。两者都过才允许提交生成。

逐项核对（判定细则见 `ai-video-director/references/22-shot-continuity-in-generation.md` §8）：

1. 该镜「衔接」列有入场态（本集首镜写「起幅态」），且有值要覆盖三条主线：
   人物位置关系、环境、动作与表情。
2. 提交的 prompt 首部有**英文接续句**（`Continuing directly from the previous shot: …`），
   写清位置关系 / 动作到第几拍 / 表情余势 / 光源方位。
   `drama compile` 不产出这句（编译器只吃单镜字段，且「衔接」列不进编译），
   缺了就按 `22` §10 前插，不得指望模型自己接。
3. 位置关系与已批准 `rel_*` 关系帧一致，且与本段其他镜头引用**同一版本**。
4. 无未处理的越轴；换机位时人物相对位置未变。
5. 接续句里没有重述服饰 / 陈设细节（`21` §5）。

任一不成立 → `BLOCKED`，回导演侧改分镜或接续句；**不许用「多抽几次总能接上」当解决手段**。

> 这一关**不涉及首帧**：判的是"戏上接不接得上"，不是"有没有把上一镜画面传过来"。
> 为接续切 `--frame-mode first` 属违规，见 `22` §5.3。

顺序纪律：**批准一镜、生成一镜**为默认串行节奏。批量预生成时以设计稿出场态为准，
上游批准后回头复核衔接，接不上的那镜重生成（`22` §8 第 6 条）。

## 2. 视频生成（Video Generation）

**一个生成视频镜头只放一个主要动作。**

避免把多个复杂动作塞进一次生成。

坏示例：

```text
run → turn → draw weapon → shoot → jump → explosion
```

好示例：

```text
Shot A: run（跑）
Shot B: turn（转身）
Shot C: draw weapon（拔武器）
Shot D: shoot（射击）
Shot E: explosion（爆炸）
```

用剪辑来制造复杂度。

每个视频任务必须定义：

```text
Initial State（初始状态）
Primary Action（主要动作）
Camera Motion（摄影机运动）
Environmental Motion（环境运动）
End State（结束状态）
Duration（时长）
```

保持**屏幕方向**与**时间连续性**：屏幕方向（左→右 / 出画方向）与速度不得跨镜反转，
动作跨镜从**同一拍点**接续而不是从头重演，光源方位与时段延续（`22` §4/§5）。

### 2.1 台词与音频（同期，硬）

台词镜的台词**必须在视频生成时一并产出**，不排后期配音任务：

- 台词逐字进生成 prompt（说话人 + 语气 + 语速），与画面动作同一次生成，模型同步出声与口型。
- 后期只做 BGM 铺设、混音、字幕烧录；**不建 VOICE（配音）与 LIPSYNC（口型同步）任务去补台词镜**。
- 没出声 / 台词错字 / 口型对不上 → 该镜 `RETRY`：改 prompt（台词前置、标说话人）、换支持同步音频的模型，或重新生成；
  不得以「后期配音 + 口型合成」放行。
- 无台词镜显式写「无对白、不出人声」，负面词排除 `voiceover, dialogue, narration`，避免模型自由加话。
- 任务类型边界：`VOICE` 只用于画外音 / 旁白与音色锚点；`LIPSYNC` 仅在有明确授权的情况下用于修复，
  且须记录原因；两者都不得成为台词镜的默认路径。判定与通道事实见
  `drama-production-playbook/references/03-seedance-best-practices.md` 规则 6。

## 3. 参考传播（Reference Propagation）

当工具支持时，用上一个**已批准镜头**的结束帧作为下一个镜头的参考。

推荐链条：

```text
Shot A
  ↓
A End Frame（A 结束帧）
  ↓
Shot B
  ↓
B End Frame（B 结束帧）
  ↓
Shot C
```

用于保持：

* **关系关键帧的组合站位**（优先级高于上一镜结束帧：结束帧会随动作漂移，关系帧是基准）
* 角色身份（character identity）
* 空间连续性（spatial continuity）
* 服装（costume）
* 灯光（lighting）
* 环境（environment）
* 动作方向（action direction）

**不要假设仅靠 seed 就能保证跨镜头一致性。**

> 结束帧只能作**动作接续的弱参考**：不作首帧（见 `03-seedance-best-practices.md` 规则 5）、
> 不作身份 / 妆造判断依据（成片截帧不得作种子，见 `ai-video-director/references/21-episode-state-lock.md` §6）。
> 身份与站位仍走 `*_turnaround` + `rel_*`。

**衔接 ≠ 尾帧接力。** 把上一镜尾帧当下一镜首帧，会把构图钉死、把上一镜的瑕疵一路传下去，
并与 `frame_mode=reference` 的默认纪律冲突。真实的接续手段是
**英文入场句 + 同版本参考复用**；尾帧的用途是和本镜第 0 帧并排核对入场句写得对不对（人工 / agent 比对），
不是喂给模型（`ai-video-director/references/22-shot-continuity-in-generation.md` §5.3）。

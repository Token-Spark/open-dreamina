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

保持**屏幕方向**与**时间连续性**。

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

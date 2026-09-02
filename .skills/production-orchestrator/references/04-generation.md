# 关键帧门禁、视频生成与参考传播

> 对应 SKILL.md 索引中的 `references/04-generation.md`。
> 生成关键帧 / 视频时加载。包含：关键帧门禁、视频生成、参考传播。

## 1. 关键帧门禁（Keyframe Gate）

对重要镜头：

1. 生成关键帧。
2. 校验角色身份（character identity）。
3. 校验场景（location）。
4. 校验构图（composition）。
5. 校验灯光（lighting）。
6. 校验道具（props）。
7. 校验情绪状态（emotional state）。
8. 批准后再生成视频。

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

* 角色身份（character identity）
* 空间连续性（spatial continuity）
* 服装（costume）
* 灯光（lighting）
* 环境（environment）
* 动作方向（action direction）

**不要假设仅靠 seed 就能保证跨镜头一致性。**

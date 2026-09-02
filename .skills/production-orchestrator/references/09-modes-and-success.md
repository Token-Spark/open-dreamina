# 工作模式、响应行为与成功标准

> 对应 SKILL.md 索引中的 `references/09-modes-and-success.md`。
> 切换工作模式 / 最终验收时加载。包含：工作模式、响应行为、成功标准。

## 1. 工作模式（Operating Modes）

### 模式 1：Plan（规划）

- 输入：导演分镜方案（Director Shot Plan）
- 输出：生产计划 + 资产计划 + 依赖图 + 任务队列
- **除非明确要求，不生成资产。**

### 模式 2：Execute（执行）

- 输入：已批准的生产计划（Approved Production Plan）
- 输出：生成产物 + 任务状态 + QC 结果

### 模式 3：Repair（修复）

- 输入：失败的生产任务（Failed production task）
- 输出：诊断 + 纠正措施 + 重试或重设计

### 模式 4：Review（评审）

- 输入：现有生产（Existing production）
- 输出：QC 报告 + 连续性报告 + 成本报告 + 未解决问题

### 模式 5：Deliver（交付）

- 输入：已批准的剧集（Approved episode）
- 输出：最终组装 + 平台变体 + 交付清单

## 2. 响应行为（Response Behavior）

被要求执行生产时，**不要立刻开始生成一切**。

先确定：

```text
生产范围是什么？（production scope）
哪些资产已存在？（existing assets）
缺少哪些依赖？（missing dependencies）
哪些任务可以并行？（parallel tasks）
哪些任务被阻塞？（blocked tasks）
哪些需要人工批准？（human approval needed）
```

然后按**依赖顺序**执行。

对长时生产，报告**有意义的里程碑**，而非叙述每一个内部操作。

## 3. 成功标准（Success Criteria）

一次成功的生产运行具有：

* 高首过成功率（first-pass success rate）
* 低无效重试率（unnecessary retry rate）
* 高资产复用率（asset reuse）
* 强角色一致性（character consistency）
* 强镜头连续性（shot continuity）
* 可追溯的来源（traceable provenance）
* 成本可控（controlled cost）
* 输出可复现（reproducible outputs）
* 失败状态清晰（clear failure states）
* 无隐藏的生产阻塞（no hidden production blockers）

> 优化目标：**单位时间与单位成本内，获得更多可用的已批准成片（Approved usable footage）。**

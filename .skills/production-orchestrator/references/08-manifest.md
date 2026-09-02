# 生产清单（Manifest）

> 对应 SKILL.md 索引中的 `references/08-manifest.md`。
> 维护生产清单时加载。详细字段 Schema 见 `production-schema.md`。

## 1. 目的

为每一集维护一份**机器可读**的生产清单（Manifest），用于：

* 追踪所有资产、任务、镜头的状态与依赖
* 支持自动化执行与校验
* 保证产物可追溯、可复现

## 2. 最小概念结构

```yaml
episode:
  id: E01

assets:
  - id: CHAR-A-V01
    type: CHARACTER
    status: APPROVED

tasks:
  - id: E01-S03-SH07-KEYFRAME
    type: IMAGE
    status: APPROVED
    dependencies:
      - CHAR-A-V01
      - LOC-HOSPITAL-V01

  - id: E01-S03-SH07-VIDEO
    type: VIDEO
    status: QC_PENDING
    dependencies:
      - E01-S03-SH07-KEYFRAME

shots:
  - id: E01-S03-SH07
    keyframe: E01-S03-SH07-KEYFRAME
    video: E01-S03-SH07-VIDEO
```

## 3. 详细 Schema

使用详细字段定义：

`references/production-schema.md`

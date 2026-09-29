# 08 迭代管理与废弃版本沉淀

> 短剧是迭代出来的：奥林匹斯全剧 724 镜中大量镜头经历 2-3 轮返工。
> 迭代的纪律决定「越改越乱」还是「越改越准」。

## 返工分级

| 级别 | 触发 | 动作 | 目录行为 |
|---|---|---|---|
| 微修 | 单镜可用但有小瑕疵 | 改提示词重roll | 新版本直接进 `{镜号}_seedance20/`，旧版移 `_superseded_{原因}/` |
| 重生成 | 整镜不可用（redesign） | 改分镜 15 行 → lint → compile → 生成 | 同上 + shots.md 更新 |
| 风格级 | 全集/全剧风格问题 | 改 manifest style → 重出锚点素材 → 抽样验证 | 保留旧版整套 `_superseded_{日期}/` |

## 废弃版本纪律（绝不直接 rm）

1. 目录内替换：旧文件移入同目录 `_superseded_{原因}/`（如 `_superseded_venuslook/`、
   `_superseded_dialogue_v2/`）——原因写在目录名里，回滚 = 原样移回。
2. 交审片中心删除：镜头审片的「删除文件」会**先把视频复制进归档 media/**
   （删前抢救），再物理删除——废弃即负样本，数据不丢。
3. 「仅移出列表」只删审片条目不动物理文件——拿不准时用这个。

## 审片数据自动归档（无感沉淀）

审阅中心的每个动作自动写入 `data/review_archive/`：

```
review_archive/
├── INDEX.md                        # 全局索引（含已删会话的留存档案标记）
└── {会话}/
    ├── session.md                  # 会话概览 + 镜号索引表（首评/终评/结果）
    └── EPxx/EPxx-Sxx/entry.md      # 单镜版本链：原内容→评分→问题→指引→精修
        └── media/                  # 媒体副本
```

价值：`entry.md` 的完整迭代链是**优化 AI 工作流的训练素材**——哪些词反复出问题、
哪类镜头重生成率高、精修提示词怎么改才有效，全在里面。

## 返工迭代的标准命令序列

```bash
# 1. 定位：审片中心导出的返修清单（或 shot-reviewer 初审报告）
# 2. 改分镜：编辑 分镜脚本/EPxx/shots.md 对应镜块
opendreamina drama lint EPxx --project .                  # 格式守门
opendreamina drama compile EPxx --shot S08 --with-style   # 重编译该镜
opendreamina drama spec EPxx --project . --write --force  # 规格同步
# 3. 旧版本入 _superseded_，重生成，落 video_renders/
# 4. 复验
opendreamina drama qc EPxx --project .
```

## 迭代健康度检查

- lint warnings 趋势：同类警告反复出现 → 回填 maps.py 词库而不是逐次接受
- 返工原因归类：一致性 / 运镜 / 多人 / 台词超时——针对性改分镜规范
- `drama list` 的 render_files 与 spec 状态对齐：有渲染无规格 = 流程被跳过
- 归档 entry.md 抽查：精修提示词是否真的进入下一版生成（闭环没断）

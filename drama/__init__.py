"""Open Dreamina 短剧制作工具链（drama 包）。

从《代号奥林匹斯》实战项目提炼的通用工具链，纯 Python 标准库实现、零第三方依赖，
全部能力通过 `opendreamina drama <action>` 子命令暴露给智能体与脚本：

    opendreamina drama init <项目路径>            初始化标准短剧项目骨架
    opendreamina drama list   [--project ROOT]    列出项目全部集与状态
    opendreamina drama parse  <EP> [--project]    解析分镜脚本 shots.md → 结构化 JSON
    opendreamina drama compile<EP> [--project]    编译镜头提示词（中文结构化 → 英文）
    opendreamina drama lint   <EP> [--project]    校验分镜脚本是否符合格式规范
    opendreamina drama spec   <EP> [--project]    生成分集执行规格（episode_spec）
    opendreamina drama assets <EP> [--project]    资产引用与平台 asset_id 比对
    opendreamina drama manifest   [--project]     校验项目级 manifest（资产/音色）
    opendreamina drama qc     <EP> [--project]    成片技术验收（画幅/时长/音轨）

分层约定：
- `drama.paths`     项目路径解析（项目根 / 分镜脚本 / 素材库 / tools）
- `drama.lexicon`   共享中英词汇表与清洗工具（项目级映射表可注入）
- `drama.parser`    分镜脚本解析（shots.md → 结构化镜头数据）
- `drama.compiler`  提示词编译（映射表与算法分离，词库由项目 tools/maps.py 提供）
- `drama.manifest`  资产清单 / 音色清单 / 分集执行规格
- `drama.qc`        质检（成片技术验收 / 资产引用完整性 / 台词同步）
- `drama.lint`      分镜脚本格式规范校验
- `drama.scaffold`  新项目脚手架
- `drama.cli`       opendreamina drama 子命令分发器
"""

__version__ = "1.0.0"

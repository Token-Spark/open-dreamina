"""提示词编译子包：结构化中文镜头描述 → Seedance-ready 英文提示词。

映射表与算法分离：编译骨架在 prompt_compiler.py（通用），
表情 / 光感 / 色调 / 环境词库由项目级 `tools/maps.py` 注入
（模板见 maps_template.py，`opendreamina drama init` 会生成）。
共享的中英清洗工具在包根 `drama.lexicon`。
"""

from drama.compiler.prompt_compiler import (  # noqa: F401
    apply_maps,
    compile_prompt,
    compile_role_binding,
    compile_dialogue_line,
    compile_shot_function,
)

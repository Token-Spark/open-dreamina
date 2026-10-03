"""项目级映射表模板（tools/maps.py 的生成底稿）。

`opendreamina drama init` 会把 MAPS_TEMPLATE 写入 `{项目根}/tools/maps.py`；
新项目按注释填充词库即可复用编译器（drama.compiler.prompt_compiler）。

加载机制：drama.lexicon.load_maps_file 执行该文件并取全部顶层 dict/str 赋值，
再由 `drama.compiler.prompt_compiler.apply_maps(data)` 与 `drama.lexicon.apply(data)`
分别注入编译器与解析器。所有键都是可选的；未提供的表保持为空。
"""

MAPS_TEMPLATE = '''"""项目级中英映射表（由 opendreamina drama init 生成）。

被 `opendreamina drama parse / compile / lint / spec` 自动加载（可用 --maps 覆盖路径）。
所有键均为可选：留空的表表示「该类中文描述不做翻译」，编译时会原样丢弃并告警，
绝不把中文泄漏进英文提示词。

填充建议：随分镜脚本撰写逐步扩充；lint 会列出未命中的词，命中后再回填到对应表。
"""

# 角色名与配角/群像称谓 → 英文代称（长键优先匹配）。
# 例："维纳斯": "Venus"、"侍女": "a handmaiden"、"众神群像": "the assembled gods"
LABEL_ZH_EN = {}

# 素材 ID 的角色标识 → 角色名别名（小写）。
# 用于把 char_venus_s2_turnaround 归属到角色名 Venus：
# 例："venus": ("venus", "aphrodite")
CHARACTER_ALIASES = {}

# 表情 / 情绪关键词 → 英文。例："伪善笃定": "sanctimonious certainty"
EXPRESSION_MAP = {}

# 台词语气短语 → 英文 delivery 指令（念白情感起伏的唯一来源）。
# 写在台词行的「语气：」段内、以、分隔；未命中会告警并按无语气处理。
# 例："声音沙哑": "hoarse voice"、"嗤笑": "snorting with mockery"
TONE_MAP = {}

# 光感 / 灯光关键词 → 英文。例："午后金色侧逆光": "afternoon golden rim light from behind"
LIGHT_MAP = {}

# 色调关键词 → 英文。例："暖金+暗绿": "warm gold and dark green"
COLOR_MAP = {}

# 环境 / 场景名称 → 英文。例："锻造坊": "the forge"
ENV_MAP = {}

# 动作短语 → 英文（组合匹配，长键优先）。
# 例："停下脚步": "coming to a halt"
ACTION_FRAGMENTS = {}

# 全局风格常量（可选兜底；优先读 tools/assets_manifest.json 的 style 字段）。
# 生成执行层会把它们逐字追加到每条镜头提示词尾部。
STYLE = {
    "AESTHETIC": "",   # 美学基调，如 "ethereal Greek mythological aesthetic, ..."
    "MEDIUM": "",      # 媒介质感，如 "1990s television drama production still, film grain, ..."
    "AUDIO": "",       # 音频约定，如 "keep the spoken dialogue ... no background music, ..."
    "NEGATIVE": "",    # 负面词，如 "text, watermark, logo, subtitles, background music, ..."
}
'''

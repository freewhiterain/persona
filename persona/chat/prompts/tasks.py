"""Per-agent task instructions and output schemas.

Templates use only ``{character_name}`` and ``{user_name}`` placeholders
(filled from ctx by ``LLMAgent`` rendering).  Preset-independent.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# 1. query rewrite
# --------------------------------------------------------------------------- #
TASK_QUERY_REWRITE = """## 你的任务
{character_name} 正在和 {user_name} 聊天。根据"上下文"（尤其是历史对话与最新消息），判断需要从下面几个资料库检索什么。
对每个库给出「查询语句」和「查询关键词」；不需要检索时，两者都填 "空"。
- 查询语句：一段精确的描述性名词，可用 "-" 表示层级，不要包含角色名字。例如：日常习惯-宠物。
- 查询关键词：逗号分隔的 1-3 个同义/相关词，每个不超过 4 字。例如：午饭,伙食,单身,恋爱。

资料库：
- 角色人物设定（{character_name} 是谁、性格、经历、习惯）
- 用户资料（{user_name} 的情况）
- 角色的知识与技能（{character_name} 擅长/了解的东西）"""

SCHEMA_QUERY_REWRITE = {
    "InnerMonologue": "角色此刻的简短内心独白",
    "CharacterSettingQueryQuestion": "针对角色人物设定的查询语句，或 空",
    "CharacterSettingQueryKeywords": "针对角色人物设定的查询关键词，或 空",
    "UserProfileQueryQuestion": "针对用户资料的查询语句，或 空",
    "UserProfileQueryKeywords": "针对用户资料的查询关键词，或 空",
    "CharacterKnowledgeQueryQuestion": "针对角色知识与技能的查询语句，或 空",
    "CharacterKnowledgeQueryKeywords": "针对角色知识与技能的查询关键词，或 空",
}

# --------------------------------------------------------------------------- #
# 2. respond
# --------------------------------------------------------------------------- #
TASK_RESPOND = """## 你的任务
{character_name} 正在微信上和 {user_name} 聊天。{user_name} 刚发来最新消息。请以 {character_name} 的身份，结合全部"上下文"推理出这一轮的回复。
要求：
- 回复必须贴合人设、说话风格、当前情绪、目标与当前关系。亲密度/信任度不同，回复也应不同。
- 涉及角色擅长的领域时要具体、专业，多引用角色的知识与经历。
- 用「分段消息」模拟真人：可以拆成 1-3 条短消息（Segments 数组），不是越多越好。
- 不要用括号动作/旁白，不要 emoji（除非人设如此）。
- 当亲密度与信任度都大于 60 时，{character_name} 更可能接受或主动表达好感。"""

SCHEMA_RESPOND = {
    "InnerMonologue": "角色的内心独白",
    "Reply": "角色的完整文字回复，句子之间可用 <br> 表示分段",
    "Segments": '数组，每项形如 {"type":"text","content":"..."}，即最终发出的分段消息（1-3 条）',
    "KnowledgeInvolved": "本轮回复是否涉及角色的专业知识/人设故事，填 是 或 否",
    "RelationDelta": '对象 {"Closeness": 整数, "Trustness": 整数}，本轮关系数值变化，通常在 -5 到 5 之间，无明显变化填 0',
    "FutureResponse": '对象 {"FutureResponseTime": "xxxx年xx月xx日xx时xx分" 或 无, "FutureResponseAction": "10-20字描述" 或 无}，表示若对方一直不回，角色下次主动找话的时间与内容',
}

# --------------------------------------------------------------------------- #
# 3. refine (free-form)
# --------------------------------------------------------------------------- #
TASK_REFINE = """## 你的任务
{character_name} 已经想好了对 {user_name} 的"初步回复"。请在保持人设与语气的前提下重写它，让它更自然、更有细节、更像真人随手发的微信。
- 输出一个 JSON 数组，每项形如 {{"type":"text","content":"..."}}。
- 1-3 条短消息，不要用括号动作，不要 emoji（除非人设如此）。
- 只输出这个 JSON 数组，不要额外文字。"""

# --------------------------------------------------------------------------- #
# 4. post-analyze / summarise
# --------------------------------------------------------------------------- #
TASK_POST_ANALYZE = """## 你的任务
下面是 {character_name} 和 {user_name} 刚刚新增的对话（"最新消息" + "最新回复"）。只针对这部分新对话做总结，不要总结历史对话。
每条总结用 "key：value" 一行，多条之间用 <br> 分隔；key 可用 "-" 表示层级（如 工作-实习-趣事）；value 一般大于 30 字。
若某条 key 与"上下文"里已有的 key 相同，说明是更新——请把新旧 value 融合后再输出。没有可总结的填 "无"。"""

SCHEMA_POST_ANALYZE = {
    "InnerMonologue": "复盘这轮对话的简短独白",
    "CharacterPublicSettings": "针对角色的、可公开的新增人设（key：value / <br>），或 无",
    "CharacterPrivateSettings": "针对角色的、只与该用户相关的私有人设，或 无",
    "CharacterKnowledges": "角色新增的知识/技能点，或 无",
    "UserSettings": "针对用户的新增人设，或 无",
    "UserRealName": "本轮得知的用户真名，或 无",
    "UserHobbyName": "本轮双方约定的用户昵称，或 无",
    "UserDescription": "结合上下文更新后的、角色对用户的印象（<=200字）",
    "CharacterPurpose": "角色更新后的短期目标（可含卖关子/试探等心理），或 无",
    "CharacterAttitude": "角色对用户的最新态度，或 无",
    "RelationDescription": "两人关系的最新描述；无变化就输出原关系",
    "Dislike": "反感度数值变化，整数，-20 到 20；被侮辱/骚扰/刷屏则为正，友好则可为负",
}

# --------------------------------------------------------------------------- #
# 5. proactive (respond variant)
# --------------------------------------------------------------------------- #
TASK_PROACTIVE = """## 你的任务
之前 {character_name} 规划了一个要主动发起的话题（见"你之前规划的主动行动"）。现在到了执行的时候。
请以 {character_name} 的身份，结合"上下文"，主动给 {user_name} 发一条消息，开启这个话题。
要求同日常回复：贴合人设，分段 1-3 条，不要括号动作，不要 emoji（除非人设如此），不要显得突兀。"""

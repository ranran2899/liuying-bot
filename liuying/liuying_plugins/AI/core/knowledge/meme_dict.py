"""网络梗数据库

预置常用网络梗解释，支持查询与动态新增。
供LLM在生成回复时理解网络梗语境，避免语义偏差。
"""


class MemeDictionary:
    """网络梗词典

    支持按词条查询解释，预置常用网络梗数据。
    """

    def __init__(self) -> None:
        """初始化网络梗词典"""
        self._dict: dict[str, str] = dict(_PRESET_MEMES)
        """梗 -> 解释"""

    def lookup(self, term: str) -> str | None:
        """查询网络梗解释

        参数:
            term: 梗词

        返回:
            str | None: 解释文本，不存在返回None
        """
        if not term:
            return None
        key = term.strip()
        if not key:
            return None
        if key in self._dict:
            return self._dict[key]
        lower = key.lower()
        for k, v in self._dict.items():
            if k.lower() == lower:
                return v
        return None

    def add(self, term: str, explanation: str) -> None:
        """新增或更新网络梗

        参数:
            term: 梗词
            explanation: 解释
        """
        term = (term or "").strip()
        explanation = (explanation or "").strip()
        if not term or not explanation:
            return
        self._dict[term] = explanation

    def remove(self, term: str) -> bool:
        """删除网络梗

        参数:
            term: 梗词

        返回:
            bool: 是否删除成功
        """
        if term in self._dict:
            self._dict.pop(term)
            return True
        return False

    def all(self) -> dict[str, str]:
        """获取全部梗数据

        返回:
            dict: 梗词 -> 解释的副本
        """
        return dict(self._dict)

    def build_prompt_block(self, terms: list[str]) -> str:
        """构建梗解释提示词块

        参数:
            terms: 命中的梗词列表

        返回:
            str: 提示词文本，无命中返回空串
        """
        if not terms:
            return ""
        lines = ["\n\n[网络梗解释]"]
        for term in terms:
            expl = self.lookup(term)
            if expl:
                lines.append(f"- {term}: {expl}")
        return "\n".join(lines) if len(lines) > 1 else ""


_PRESET_MEMES: dict[str, str] = {
    "yyds": "永远的神，表示对某人或某物的极度赞美",
    "xswl": "笑死我了，形容非常搞笑",
    "awsl": "啊我死了，被可爱或感动到无法自持",
    "kdl": "嗑到了，指看到喜欢的CP互动而满足",
    "zqsg": "真情实感，指投入了真实感情",
    "u1s1": "有一说一，表示客观地讲",
    "ssfd": "瑟瑟发抖，形容害怕或紧张",
    "bdjw": "不懂就问，常用于提问前",
    "bhys": "不好意思，用于道歉或客套",
    "pyq": "朋友圈，微信社交功能",
    "cp": "配对，指把两人凑成情侣关系",
    "dd": "顶顶，表示支持；也指弟弟",
    "233": "哈哈大笑，源自猫扑表情编号",
    "666": "牛牛牛，表示很厉害",
    "999": "比666还厉害，极致赞美",
    "草": "一种植物，常表示无语或好笑",
    "芭比Q": "完了，源自烧烤梗，指事情搞砸了",
    "摸鱼": "上班时间偷懒做与工作无关的事",
    "内卷": "同行间非理性竞争，互相加码",
    "躺平": "放弃竞争，维持最低生活标准",
    "破防": "心理防线被突破，被触动或震惊",
    "打call": "为某人或某事应援、加油",
    "种草": "看到推荐后产生购买欲望",
    "拔草": "买下了之前种草的东西",
    "社死": "社会性死亡，指当众极其尴尬",
    "绝绝子": "极好或极差，看语境",
    "emo": "情绪低落、伤感",
    "贴贴": "亲昵地靠在一起，表示喜爱",
    "栓Q": "thank you的谐音，常带无奈语气",
    "芜湖": "起飞的欢呼，源自主播口头禅",
}
"""预置网络梗数据"""


meme_dictionary = MemeDictionary()
"""网络梗词典单例"""

"""内置技能包集合

目录式技能包结构（参考参考插件 skillpacks 设计）：
每个技能包为独立目录，包含 skill.yaml + scripts/main.py + scripts/impl.py。

内置技能包：
- news: 新闻查询
- weather: 天气查询
- datetime_tool: 日期时间
- wiki: Wiki百科查询
- game_info: 游戏信息查询

技能包通过 SkillRuntime 依赖注入访问主插件服务，
由 SkillpackLoader 扫描目录并自动加载。
"""

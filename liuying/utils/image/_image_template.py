"""图片模板模块

提供图片模板生成功能，包括表格、文档、Markdown 和 Notebook 格式
"""

from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import random
from typing import ClassVar, Self, TypeAlias

from nonebot_plugin_htmlrender import md_to_pic, template_to_pic
from PIL.ImageFont import FreeTypeFont

from liuying.configs.path_config import TEMPLATE_PATH
from liuying.utils.image._build_image import BuildImage

ColorType: TypeAlias = str | tuple[int, int, int]
TableDataItem: TypeAlias = str | int | tuple[Path | BuildImage | bytes, int, int]


@dataclass(slots=True)
class RowStyle:
    """行样式配置"""

    font: FreeTypeFont | str | Path | None = "HYWenHei-85W.ttf"
    font_size: int = 20
    font_color: ColorType = (0, 0, 0)


class ImageTemplate:
    """图片模板生成类"""

    COLOR_LIST: ClassVar[list[str]] = ["#C2CEFE", "#FFA94C", "#3FE6A0", "#D1D4F5"]

    @classmethod
    async def hl_page(
        cls,
        head_text: str,
        items: dict[str, str],
        row_space: int = 10,
        padding: int = 30,
    ) -> BuildImage:
        """列文档 (如插件帮助)

        参数:
            head_text: 头标签文本
            items: 列内容
            row_space: 列间距.
            padding: 间距.

        返回:
            BuildImage: 图片
        """
        font = BuildImage.load_font("HYWenHei-85W.ttf", 20)
        width, height = BuildImage.get_text_size(head_text, font)

        for title, item in items.items():
            title_width, title_height = await cls.__get_text_size(title, font)
            it_width, it_height = await cls.__get_text_size(item, font)
            width = max(width, title_width, it_width)
            height += title_height + it_height

        width = max(width + padding * 2 + 100, 300)
        height = max(height + padding * 2 + 150, 100)

        A = BuildImage(width + padding * 2, height + padding * 2, color="#FAF9FE")
        top_head = BuildImage(width, 100, color="#FFFFFF", font_size=40)
        await top_head.line((0, 1, width, 1), "#C2CEFE", 2)
        await top_head.text((15, 20), head_text, "#9FA3B2", "center")
        await top_head.circle_corner()
        await A.paste(top_head, (0, 20), "width")

        _min_width = top_head.width - 60
        cur_h = top_head.height + 35 + row_space * len(items)

        for title, item in items.items():
            title_width, title_height = BuildImage.get_text_size(title, font)
            title_background = BuildImage(
                title_width + 6, title_height + 10, font=font, color="#C1CDFF"
            )
            await title_background.text((3, 5), title)
            await title_background.circle_corner(5)

            _text_width, _text_height = await cls.__get_text_size(item, font)
            _width = max(title_background.width, _text_width, _min_width)
            text_image = await cls.__build_text_image(
                item, _width, _text_height, font, color="#FDFCFA"
            )

            B = BuildImage(_width + 20, title_height + text_image.height + 40)
            await B.paste(title_background, (10, 10))
            await B.paste(text_image, (10, 20 + title_background.height))
            await B.line((0, 0, 0, B.height), random.choice(cls.COLOR_LIST))
            await A.paste(B, (0, cur_h), "width")
            cur_h += B.height + row_space

        return A

    @classmethod
    async def table_page(
        cls,
        head_text: str,
        tip_text: str | None,
        column_name: list[str],
        data_list: list[list[TableDataItem]],
        row_space: int = 35,
        column_space: int = 30,
        padding: int = 5,
        text_style: Callable[[str, str], RowStyle] | None = None,
    ) -> BuildImage:
        """表格页

        参数:
            head_text: 标题文本.
            tip_text: 标题注释.
            column_name: 表头列表.
            data_list: 数据列表.
            row_space: 行间距.
            column_space: 列间距.
            padding: 文本内间距.
            text_style: 文本样式.

        返回:
            BuildImage: 表格图片
        """
        font = BuildImage.load_font(font_size=50)
        min_width, _ = BuildImage.get_text_size(head_text, font)
        table = await cls.table(
            column_name, data_list, row_space, column_space, padding, text_style
        )
        await table.circle_corner()

        table_bk = BuildImage(
            max(table.width, min_width) + 100, table.height + 50, "#EAEDF2"
        )
        await table_bk.paste(table, center_type="center")

        height = table_bk.height + 200
        background = BuildImage(table_bk.width, height, (255, 255, 255), font_size=50)
        await background.paste(table_bk, (0, 200))
        await background.text((0, 50), head_text, "#334762", center_type="width")

        if tip_text:
            text_image = await BuildImage.build_text_image(tip_text, size=22)
            await background.paste(text_image, (0, 110), center_type="width")

        return background

    @classmethod
    async def table(
        cls,
        column_name: list[str],
        data_list: list[list[TableDataItem]],
        row_space: int = 25,
        column_space: int = 10,
        padding: int = 5,
        text_style: Callable[[str, str], RowStyle] | None = None,
    ) -> BuildImage:
        """表格

        参数:
            column_name: 表头列表
            data_list: 数据列表
            row_space: 行间距.
            column_space: 列间距.
            padding: 文本内间距.
            text_style: 文本样式.

        返回:
            BuildImage: 表格图片
        """
        font = BuildImage.load_font("HYWenHei-85W.ttf", 20)

        column_data: list[list] = []
        for i in range(len(column_name)):
            col: list = []
            for item in data_list:
                if len(item) > i:
                    cell = item[i]
                    col.append(cell if isinstance(cell, tuple | list) else str(cell))
                else:
                    col.append("")
            column_data.append(col)

        _, base_h = BuildImage.get_text_size("A", font)
        build_data_list = []

        for i, column_list in enumerate(column_data):
            name_width, _ = BuildImage.get_text_size(column_name[i], font)
            max_width = name_width

            for s in column_list:
                if isinstance(s, tuple):
                    w = s[1]
                else:
                    w = BuildImage.get_text_size(str(s), font)[0]
                max_width = max(max_width, w)

            build_data_list.append({"width": max_width, "data": column_list})

        column_name_image_list = [
            await BuildImage.build_text_image(name, font, 12, "#C8CCCF")
            for name in column_name
        ]
        max_h = max(c.height for c in column_name_image_list)

        column_image_list = []
        for i, data in enumerate(build_data_list):
            width = data["width"] + padding * 2
            height = (base_h + row_space) * (len(data["data"]) + 1) + padding * 2
            background = BuildImage(width, height, (255, 255, 255))

            column_name_image = column_name_image_list[i]
            await background.paste(column_name_image, (0, 20), center_type="width")

            cur_h = max_h + row_space + 20
            for item in data["data"]:
                style = (
                    text_style(column_name[i], item)
                    if text_style
                    else RowStyle(font=font)
                )

                match item:
                    case (Path() | BuildImage() | bytes(), int(w), int(h)):
                        image_ = cls._create_image_from_data(item[0], w, h)
                        if image_:
                            await background.paste(image_, (padding, cur_h))
                    case _:
                        await background.text(
                            (padding, cur_h),
                            item if item is not None else "",
                            style.font_color,
                            font=style.font,
                            font_size=style.font_size,
                        )
                cur_h += base_h + row_space

            column_image_list.append(background)

        return await BuildImage.auto_paste(
            column_image_list, len(column_image_list), column_space
        )

    @staticmethod
    def _create_image_from_data(
        data: Path | BuildImage | bytes, width: int, height: int
    ) -> BuildImage | None:
        """从数据创建图片

        参数:
            data: 图片数据
            width: 宽度
            height: 高度

        返回:
            BuildImage | None: 图片对象
        """
        match data:
            case Path():
                return BuildImage(width, height, background=data)
            case bytes():
                return BuildImage(width, height, background=BytesIO(data))
            case BuildImage():
                return data
            case _:
                return None

    @classmethod
    async def __build_text_image(
        cls,
        text: str,
        width: int,
        height: int,
        font: FreeTypeFont,
        font_color: ColorType = (0, 0, 0),
        color: ColorType = (255, 255, 255),
    ) -> BuildImage:
        """文本转图片

        参数:
            text: 文本
            width: 宽度
            height: 长度
            font: 字体
            font_color: 文本颜色
            color: 背景颜色

        返回:
            BuildImage: 文本转图片
        """
        _, h = BuildImage.get_text_size("A", font)
        A = BuildImage(width, height, color=color)
        cur_h = 0

        for s in text.split("\n"):
            text_image = await BuildImage.build_text_image(
                s, font, font_color=font_color
            )
            await A.paste(text_image, (0, cur_h))
            cur_h += h

        return A

    @classmethod
    async def __get_text_size(cls, text: str, font: FreeTypeFont) -> tuple[int, int]:
        """获取文本所占大小

        参数:
            text: 文本
            font: 字体

        返回:
            tuple[int, int]: 宽, 高
        """
        _, h = BuildImage.get_text_size("A", font)
        lines = text.split("\n")
        width = max(
            (BuildImage.get_text_size(s.strip() or "A", font)[0] for s in lines),
            default=0,
        )
        return width, h * len(lines)


class MarkdownTable:
    """Markdown 表格生成类"""

    __slots__ = ("headers", "rows")

    def __init__(self, headers: list[str], rows: list[list[str]]):
        self.headers = headers
        self.rows = rows

    def to_markdown(self) -> str:
        """将表格转换为Markdown格式"""
        header_row = "| " + " | ".join(self.headers) + " |"
        separator_row = "| " + " | ".join(["---"] * len(self.headers)) + " |"
        data_rows = "\n".join(
            "| " + " | ".join(map(str, row)) + " |" for row in self.rows
        )
        return f"{header_row}\n{separator_row}\n{data_rows}"


class Markdown:
    """Markdown 文档生成类"""

    __slots__ = ("_data",)

    def __init__(self, data: list[str] | None = None):
        self._data = data or []

    def text(self, text: str) -> Self:
        """添加Markdown文本"""
        self._data.append(text)
        return self

    def head(self, text: str, level: int = 1) -> Self:
        """添加Markdown标题

        参数:
            text: 标题文本
            level: 标题级别 (1-6)

        返回:
            Self: Markdown

        异常:
            ValueError: 标题级别不在1-6范围内
        """
        if not 1 <= level <= 6:
            raise ValueError("标题级别必须在1到6之间")
        self._data.append(f"{'#' * level} {text}")
        return self

    def image(self, content: str | Path, add_empty_line: bool = True) -> Self:
        """添加Markdown图片

        参数:
            content: 图片内容，可以是url地址，图片路径或base64字符串.
            add_empty_line: 默认添加换行.

        返回:
            Self: Markdown
        """
        if isinstance(content, Path):
            content = str(content.absolute())

        if content.startswith("base64"):
            content = f"data:image/png;base64,{content.split('base64://', 1)[-1]}"

        self._data.append(f"![image]({content})")

        if add_empty_line:
            self._add_empty_line()

        return self

    def quote(self, text: str | list[str]) -> Self:
        """添加Markdown引用文本

        参数:
            text: 引用文本内容，可以是字符串或字符串列表.

        返回:
            Self: Markdown
        """
        match text:
            case str():
                self._data.append(f"> {text}")
            case list():
                self._data.extend(f"> {t}" for t in text)

        self._add_empty_line()
        return self

    def code(self, code: str, language: str = "python") -> Self:
        """添加Markdown代码块"""
        self._data.append(f"```{language}\n{code}\n```")
        return self

    def table(self, headers: list[str], rows: list[list[str]]) -> Self:
        """添加Markdown表格"""
        table = MarkdownTable(headers, rows)
        self._data.append(table.to_markdown())
        return self

    def list(self, items: list[str | list[str]]) -> Self:
        """添加Markdown列表"""
        self._add_empty_line()
        _text = "\n".join(
            f"- {item}"
            if isinstance(item, str)
            else "\n".join(f"- {sub_item}" for sub_item in item)
            for item in items
        )
        self._data.append(_text)
        return self

    def _add_empty_line(self):
        """添加空行"""
        self._data.append("")

    async def build(self, width: int = 800, css_path: Path | None = None) -> bytes:
        """构建Markdown文本

        参数:
            width: 图片宽度
            css_path: CSS样式文件路径

        返回:
            bytes: 图片字节数据
        """
        md_content = "\n".join(self._data)
        if css_path is not None:
            return await md_to_pic(
                md=md_content, width=width, css_path=str(css_path.absolute())
            )
        return await md_to_pic(md=md_content, width=width)


class Notebook:
    """Notebook 文档生成类"""

    __slots__ = ("_data",)

    def __init__(self, data: list[dict] | None = None):
        self._data = data or []

    def text(self, text: str) -> Self:
        """添加Notebook文本"""
        self._data.append({"type": "paragraph", "text": text})
        return self

    def head(self, text: str, level: int = 1) -> Self:
        """添加Notebook标题

        参数:
            text: 标题文本
            level: 标题级别 (1-4)

        返回:
            Self: Notebook

        异常:
            ValueError: 标题级别不在1-4范围内
        """
        if not 1 <= level <= 4:
            raise ValueError("标题级别必须在1-4之间")
        self._data.append({"type": "heading", "text": text, "level": level})
        return self

    def image(self, content: str | Path, caption: str | None = None) -> Self:
        """添加Notebook图片

        参数:
            content: 图片内容，可以是url地址，图片路径或base64字符串.
            caption: 图片说明.

        返回:
            Self: Notebook
        """
        if isinstance(content, Path):
            content = str(content.absolute())

        if content.startswith("base64"):
            content = f"data:image/png;base64,{content.split('base64://', 1)[-1]}"

        self._data.append({"type": "image", "src": content, "caption": caption})
        return self

    def quote(self, text: str | list[str]) -> Self:
        """添加Notebook引用文本

        参数:
            text: 引用文本内容，可以是字符串或字符串列表.

        返回:
            Self: Notebook
        """
        match text:
            case str():
                self._data.append({"type": "blockquote", "text": text})
            case list():
                self._data.extend({"type": "blockquote", "text": t} for t in text)

        return self

    def code(self, code: str, language: str = "python") -> Self:
        """添加Notebook代码块"""
        self._data.append({"type": "code", "code": code, "language": language})
        return self

    def list(self, items: list[str], ordered: bool = False) -> Self:
        """添加Notebook列表"""
        self._data.append({"type": "list", "data": items, "ordered": ordered})
        return self

    def add_divider(self) -> Self:
        """添加分隔线"""
        self._data.append({"type": "divider"})
        return self

    async def build(self) -> bytes:
        """构建Notebook

        返回:
            bytes: 图片字节数据
        """
        return await template_to_pic(
            template_path=str((TEMPLATE_PATH / "notebook").absolute()),
            template_name="main.html",
            templates={"elements": self._data},
            pages={
                "viewport": {"width": 700, "height": 10},
                "base_url": f"file://{TEMPLATE_PATH}",
            },
            wait=2,
        )

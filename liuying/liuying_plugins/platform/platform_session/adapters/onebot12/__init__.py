"""OneBot V12 适配器加载器"""

from ...constraint import SupportAdapter
from ...fetch import InfoFetcher
from ...loader import BaseLoader
from .main import fetcher


class Loader(BaseLoader):
    """OneBot V12 会话抓取器加载器"""

    def get_adapter(self) -> SupportAdapter:
        return SupportAdapter.onebot12

    def get_fetcher(self) -> InfoFetcher:
        return fetcher

"""QQ 官方适配器加载器"""

from ...constraint import SupportAdapter
from ...fetch import InfoFetcher
from ...loader import BaseLoader
from .main import fetcher


class Loader(BaseLoader):
    """QQ 官方会话抓取器加载器"""

    def get_adapter(self) -> SupportAdapter:
        return SupportAdapter.qq

    def get_fetcher(self) -> InfoFetcher:
        return fetcher

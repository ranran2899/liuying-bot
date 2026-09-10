"""嵌入服务封装

统一管理记忆系统的向量生成,支持两种模式:
1. 本地哈希 BoW 方案(默认,零依赖,64维)
2. LLM 嵌入模型(配置 EMBEDDING_PROVIDER + EMBEDDING_MODEL 后启用)

LLM 模式下 API 调用失败时自动降级到本地方案,保证可用性。
通过 model_version 标识区分不同嵌入源,查询时按版本过滤,
避免不同维度向量混合导致相似度计算异常。
"""

from liuying.utils.log import logger

from ...config import get_config
from ..llm import llm_helper
from ._common import MemoryEmbeddingUtils

_HASH_BOW_VERSION = "hash_bow"
"""本地哈希 BoW 模型版本标识"""


class EmbeddingService:
    """嵌入向量生成服务

    根据配置自动选择 LLM 嵌入模型或本地哈希方案,
    并提供批量生成与降级能力。

    Attributes:
        model_version: 当前嵌入模型版本标识
        embedding_dim: 当前嵌入维度
    """

    def __init__(self) -> None:
        """初始化嵌入服务

        读取配置判断是否启用 LLM 嵌入,计算当前模型版本与维度。
        """
        self._use_llm = bool(
            get_config("MEMORY_USE_LLM_EMBEDDING", False)
        )
        self._llm_ready = False
        self.model_version: str = _HASH_BOW_VERSION
        self.embedding_dim: int = MemoryEmbeddingUtils.default_dim()

        if self._use_llm:
            embedding_cfg = get_config("EMBEDDING", {})
            provider = embedding_cfg.get("provider", None)
            model = embedding_cfg.get("model", None)
            if provider and model:
                self._llm_ready = True
                self.model_version = f"llm:{provider}:{model}"
                self.embedding_dim = self._detect_dimension(
                    provider, model
                )
            else:
                logger.warning(
                    "MEMORY_USE_LLM_EMBEDDING已启用但"
                    "EMBEDDING_PROVIDER/EMBEDDING_MODEL未配置,"
                    "回退到本地哈希方案",
                    command="AI",
                )
                self._use_llm = False

    @staticmethod
    def _detect_dimension(
        provider: str, model: str
    ) -> int:
        """探测嵌入模型维度

        参数:
            provider: 供应商名
            model: 模型名

        返回:
            int: 嵌入维度,未知时回退到本地默认维度
        """
        dim_map: dict[str, int] = {
            "embedding-3": 2048,
            "embedding-2": 1024,
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return dim_map.get(model, MemoryEmbeddingUtils.default_dim())

    async def embed_text(self, text: str) -> list[float]:
        """生成单条文本的嵌入向量

        LLM 模式下调用嵌入 API,失败时降级到本地哈希。
        本地模式直接用 hash_bow 生成。

        参数:
            text: 输入文本

        返回:
            list[float]: 嵌入向量
        """
        if not text or not text.strip():
            return [0.0] * self.embedding_dim
        if not self._llm_ready:
            return MemoryEmbeddingUtils.hash_bow_embedding(
                text, self.embedding_dim
            )
        try:
            result = await llm_helper.embedding(text)
            return self._unwrap_single(result)
        except Exception as e:
            logger.debug(
                f"LLM嵌入生成失败,降级到本地哈希: {e}",
                command="AI",
                e=e,
            )
            # 降级向量维度必须与当前模型维度一致，
            # 否则与已入库向量做相似度计算时失真
            return MemoryEmbeddingUtils.hash_bow_embedding(
                text, self.embedding_dim
            )

    async def embed_batch(
        self, texts: list[str]
    ) -> list[list[float]]:
        """批量生成嵌入向量

        LLM 模式下利用智谱 API 的批量输入能力,单次请求处理多条文本。
        失败时整体降级到本地哈希。

        参数:
            texts: 文本列表

        返回:
            list[list[float]]: 嵌入向量列表,与输入顺序一致
        """
        if not texts:
            return []
        if not self._llm_ready:
            return [
                MemoryEmbeddingUtils.hash_bow_embedding(
                    t, self.embedding_dim
                )
                for t in texts
            ]
        try:
            result = await llm_helper.embedding(texts)
            return self._unwrap_batch(result, len(texts))
        except Exception as e:
            logger.debug(
                f"LLM批量嵌入生成失败,降级到本地哈希: {e}",
                command="AI",
                e=e,
            )
            return [
                MemoryEmbeddingUtils.hash_bow_embedding(
                    t, self.embedding_dim
                )
                for t in texts
            ]

    @staticmethod
    def _unwrap_single(
        result: object,
    ) -> list[float]:
        """从 API 返回值提取单条向量

        llm_helper.embedding 类型标注为 list[float],
        但底层 emb_cap.create 实际返回 list[list[float]],
        此处做运行时类型兼容。

        参数:
            result: API 返回值

        返回:
            list[float]: 单条嵌入向量
        """
        if not isinstance(result, list) or not result:
            return []
        first = result[0]
        if isinstance(first, list):
            return first
        return result  # type: ignore[return-value]

    @staticmethod
    def _unwrap_batch(
        result: object, expected: int
    ) -> list[list[float]]:
        """从 API 返回值提取批量向量

        类型混淆时记录 warning 并降级处理,避免静默
        返回空列表导致下游去重/聚合失效且无迹可查:
        - 扁平结构且仅期望单条时包装为嵌套列表返回;
        - 完全无法解析时返回空列表,下游将因缺少
          向量跳过该批数据的去重/聚合。

        参数:
            result: API 返回值
            expected: 期望的向量数量

        返回:
            list[list[float]]: 嵌入向量列表
        """
        if not isinstance(result, list):
            logger.warning(
                "LLM批量嵌入返回类型异常(非列表),"
                "本批向量解析失败,下游去重/聚合将跳过该批数据",
                command="AI",
            )
            return []
        if result and isinstance(result[0], list):
            return result  # type: ignore[return-value]
        if expected == 1:
            logger.warning(
                "LLM批量嵌入返回扁平结构(期望嵌套向量列表),"
                "已降级包装为单条结果",
                command="AI",
            )
            return [result]  # type: ignore[list-item]
        logger.warning(
            f"LLM批量嵌入返回结构异常且与期望数量不符"
            f"(期望{expected}条),本批向量解析失败,"
            "下游去重/聚合将跳过该批数据",
            command="AI",
        )
        return []

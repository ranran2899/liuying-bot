# vision_caller 参考资料

## 依赖服务

- `core/vision.vision_router.route_vision_request(prefer_provider=, prefer_model=)` → `VisionRouteResult`
- `core/vision.vision_router.get_capability_summary()` → `dict`

### VisionRouteResult 字段

| 字段 | 含义 |
|---|---|
| `success` | 是否成功路由到支持视觉的模型 |
| `provider` / `model` | 命中的 provider 与模型名 |
| `info` | `VisionCapabilityInfo`，含 `confidence`、`detection_method` |
| `fallback_used` / `fallback_reason` | 是否走降级通道及原因 |

### get_capability_summary 字段

`cached_probes`、`preferred_provider`、`preferred_model`、`vision_supported`

## 探测方式

| detection_method | 中文标签 | 说明 |
|---|---|---|
| `keyword` | 模型名关键词匹配 | 按模型名推断，最快但置信度最低 |
| `probe` | 真实请求探测 | 发一次真实请求验证，最准 |
| `config` | 配置显式声明 | 配置中已声明支持视觉 |

## 常量

| 常量 | 值 | 说明 |
|---|---|---|
| `_ROUTE_TIMEOUT` | 20.0 | 探测超时（秒） |

`vision_router` 内部能力缓存 TTL 为 6 小时，本技能不再叠加缓存。

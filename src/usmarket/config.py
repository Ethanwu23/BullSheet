"""配置加载：YAML 文件 < 环境变量 < CLI 参数（后者覆盖前者）。

敏感配置只从环境变量读取，配置文件中不得存放密钥（FR-061）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from usmarket.errors import ConfigError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"

# 需要保密的配置键名：日志与错误输出中不得出现其值
SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "token",
        "secret",
        "password",
        "cookie",
        "authorization",
        "app_secret",
        "access_token",
    }
)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"环境变量 {name} 必须为整数，实际值: {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"环境变量 {name} 必须为数字，实际值: {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_json(name: str, default: dict) -> dict:
    """解析 JSON 对象型环境变量（如厂商特有额外请求体）。"""
    raw = _env(name)
    if raw is None:
        return dict(default)
    import json

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"环境变量 {name} 必须为 JSON 对象") from exc
    if not isinstance(parsed, dict):
        raise ConfigError(f"环境变量 {name} 必须为 JSON 对象")
    return parsed


@dataclass(frozen=True)
class AccountConfig:
    name: str = "美股日报"
    handle: str = ""


@dataclass(frozen=True)
class WatchlistConfig:
    indices: tuple[str, ...] = ("^GSPC", "^IXIC", "^DJI")
    tickers: tuple[str, ...] = ("NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA")
    topics: tuple[str, ...] = ("earnings", "fed", "inflation", "ai", "semiconductor")


@dataclass(frozen=True)
class FeedConfig:
    name: str
    url: str
    trust: str = "established"  # official | established | aggregator
    kind: str = "market"  # market | ticker_query | macro
    enabled: bool = True


@dataclass(frozen=True)
class NewsConfig:
    lookback_hours: int = 48
    max_items_per_source: int = 20
    min_items_for_confidence: int = 3
    request_timeout_seconds: int = 15
    max_retries: int = 3
    feeds: tuple[FeedConfig, ...] = ()
    ticker_query_template: str = (
        "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    )
    edgar_enabled: bool = True
    edgar_forms: tuple[str, ...] = ("8-K",)
    edgar_user_agent: str = "USMarketDailyXHS/0.1 (contact@example.com)"


@dataclass(frozen=True)
class MarketConfig:
    provider: str = "yahoo"
    stale_minutes: int = 60
    timeout_seconds: int = 15
    max_retries: int = 3
    finnhub_api_key: str = ""
    alphavantage_api_key: str = ""


# 阿里百炼（DashScope）OpenAI 兼容端点
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# 百炼可用模型（实测 2026-10-27 端点返回 182 个 model id，含 qwen3.8-flash / qwen3.8-max / qwen3.8-27b）
# 可通过 `usmarket llm-models` 列出当前 key 可用的模型
DASHSCOPE_DEFAULT_MODEL = "qwen3.8-flash"


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "rule_based"  # openai_compatible | dashscope | anthropic | rule_based
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 4000
    timeout_seconds: int = 120
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    # 厂商特有的额外请求体（如百炼关闭思考链：
    # {"chat_template_kwargs": {"enable_thinking": false}}），由 LLM_EXTRA_BODY_JSON 注入
    extra_body: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ContentConfig:
    top_news_min: int = 3
    top_news_max: int = 5
    body_max_chars: int = 800
    title_max_chars: int = 30
    max_tags: int = 10
    tags: tuple[str, ...] = ("#美股", "#美股日报", "#投资理财", "#财经", "#纳斯达克")
    disclaimer: str = (
        "本文仅为公开信息整理，不构成投资建议；行情数据可能存在延迟，请以交易所与官方渠道为准。"
    )


@dataclass(frozen=True)
class ThemeConfig:
    background: str = "#0F172A"
    surface: str = "#16213E"
    accent: str = "#F97316"
    positive: str = "#22C55E"
    negative: str = "#EF4444"
    text_primary: str = "#F8FAFC"
    text_secondary: str = "#94A3B8"
    muted: str = "#334155"
    font_regular: str = ""
    font_bold: str = ""


@dataclass(frozen=True)
class ImageConfig:
    width: int = 1080
    height: int = 1440
    min_pages: int = 5
    max_pages: int = 7
    template: str = "daily_review"  # daily_review | flash_brief
    margin: int = 80
    theme: ThemeConfig = field(default_factory=ThemeConfig)


@dataclass(frozen=True)
class PublishConfig:
    publisher: str = "mock"  # mock | manual_export | browser
    max_retries: int = 3
    backoff_seconds: float = 1.0
    enable_browser: bool = False
    mock_fail_first: int = 0


@dataclass(frozen=True)
class ScheduleConfig:
    mode: str = "after_close"  # after_close | pre_open（pre_open 第一版不启用）
    timezone: str = "America/New_York"
    cron_utc: str = "30 22 * * 1-5"


@dataclass(frozen=True)
class AppConfig:
    account: AccountConfig = field(default_factory=AccountConfig)
    watchlist: WatchlistConfig = field(default_factory=WatchlistConfig)
    news: NewsConfig = field(default_factory=NewsConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    content: ContentConfig = field(default_factory=ContentConfig)
    image: ImageConfig = field(default_factory=ImageConfig)
    publish: PublishConfig = field(default_factory=PublishConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    data_dir: Path = field(default_factory=lambda: Path("data"))
    offline: bool = False
    log_level: str = "INFO"

    def with_overrides(
        self,
        *,
        tickers: tuple[str, ...] | None = None,
        provider: str | None = None,
        template: str | None = None,
        offline: bool | None = None,
        data_dir: Path | None = None,
    ) -> AppConfig:
        """返回应用了 CLI 覆盖后的新配置（不可变）。"""
        cfg = self
        if tickers:
            cfg = replace(cfg, watchlist=replace(cfg.watchlist, tickers=tuple(tickers)))
        if provider:
            cfg = replace(cfg, llm=replace(cfg.llm, provider=provider))
        if template:
            cfg = replace(cfg, image=replace(cfg.image, template=template))
        if offline is not None:
            cfg = replace(cfg, offline=offline)
        if data_dir is not None:
            cfg = replace(cfg, data_dir=data_dir)
        return cfg


def _tuple_of_str(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return tuple(x.strip() for x in value.split(",") if x.strip())
    return tuple(str(x).strip() for x in value if str(x).strip())


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件 {path} 顶层必须是映射")
    return data


def _build_from_yaml(raw: dict[str, Any]) -> AppConfig:
    account_raw = raw.get("account") or {}
    wl_raw = raw.get("watchlist") or {}
    news_raw = raw.get("news") or {}
    market_raw = raw.get("market") or {}
    llm_raw = raw.get("llm") or {}
    content_raw = raw.get("content") or {}
    image_raw = raw.get("image") or {}
    theme_raw = image_raw.get("theme") or {}
    publish_raw = raw.get("publish") or {}
    schedule_raw = raw.get("schedule") or {}

    feeds = tuple(
        FeedConfig(
            name=str(f.get("name", "unnamed")),
            url=str(f.get("url", "")),
            trust=str(f.get("trust", "established")),
            kind=str(f.get("kind", "market")),
            enabled=bool(f.get("enabled", True)),
        )
        for f in (news_raw.get("feeds") or [])
        if f.get("url")
    )

    return AppConfig(
        account=AccountConfig(
            name=str(account_raw.get("name", "美股日报")),
            handle=str(account_raw.get("handle", "")),
        ),
        watchlist=WatchlistConfig(
            indices=_tuple_of_str(wl_raw.get("indices"), WatchlistConfig.indices),
            tickers=_tuple_of_str(wl_raw.get("tickers"), WatchlistConfig.tickers),
            topics=_tuple_of_str(wl_raw.get("topics"), WatchlistConfig.topics),
        ),
        news=NewsConfig(
            lookback_hours=int(news_raw.get("lookback_hours", 48)),
            max_items_per_source=int(news_raw.get("max_items_per_source", 20)),
            min_items_for_confidence=int(news_raw.get("min_items_for_confidence", 3)),
            request_timeout_seconds=int(news_raw.get("request_timeout_seconds", 15)),
            max_retries=int(news_raw.get("max_retries", 3)),
            feeds=feeds,
            ticker_query_template=str(
                news_raw.get("ticker_query_template", NewsConfig.ticker_query_template)
            ),
            edgar_enabled=bool(news_raw.get("edgar_enabled", True)),
            edgar_forms=_tuple_of_str(news_raw.get("edgar_forms"), ("8-K",)),
            edgar_user_agent=str(
                news_raw.get("edgar_user_agent", NewsConfig.edgar_user_agent)
            ),
        ),
        market=MarketConfig(
            provider=str(market_raw.get("provider", "yahoo")),
            stale_minutes=int(market_raw.get("stale_minutes", 60)),
            timeout_seconds=int(market_raw.get("timeout_seconds", 15)),
            max_retries=int(market_raw.get("max_retries", 3)),
        ),
        llm=LLMConfig(
            provider=str(llm_raw.get("provider", "rule_based")),
            base_url=str(llm_raw.get("base_url", LLMConfig.base_url)),
            model=str(llm_raw.get("model", LLMConfig.model)),
            temperature=float(llm_raw.get("temperature", 0.3)),
            max_tokens=int(llm_raw.get("max_tokens", 4000)),
            timeout_seconds=int(llm_raw.get("timeout_seconds", 120)),
            anthropic_model=str(llm_raw.get("anthropic_model", LLMConfig.anthropic_model)),
        ),
        content=ContentConfig(
            top_news_min=int(content_raw.get("top_news_min", 3)),
            top_news_max=int(content_raw.get("top_news_max", 5)),
            body_max_chars=int(content_raw.get("body_max_chars", 800)),
            title_max_chars=int(content_raw.get("title_max_chars", 30)),
            max_tags=int(content_raw.get("max_tags", 10)),
            tags=_tuple_of_str(content_raw.get("tags"), ContentConfig.tags),
            disclaimer=str(content_raw.get("disclaimer", ContentConfig.disclaimer)),
        ),
        image=ImageConfig(
            width=int(image_raw.get("width", 1080)),
            height=int(image_raw.get("height", 1440)),
            min_pages=int(image_raw.get("min_pages", 5)),
            max_pages=int(image_raw.get("max_pages", 7)),
            template=str(image_raw.get("template", "daily_review")),
            margin=int(image_raw.get("margin", 80)),
            theme=ThemeConfig(
                background=str(theme_raw.get("background", ThemeConfig.background)),
                surface=str(theme_raw.get("surface", ThemeConfig.surface)),
                accent=str(theme_raw.get("accent", ThemeConfig.accent)),
                positive=str(theme_raw.get("positive", ThemeConfig.positive)),
                negative=str(theme_raw.get("negative", ThemeConfig.negative)),
                text_primary=str(theme_raw.get("text_primary", ThemeConfig.text_primary)),
                text_secondary=str(
                    theme_raw.get("text_secondary", ThemeConfig.text_secondary)
                ),
                muted=str(theme_raw.get("muted", ThemeConfig.muted)),
                font_regular=str(theme_raw.get("font_regular", "")),
                font_bold=str(theme_raw.get("font_bold", "")),
            ),
        ),
        publish=PublishConfig(
            publisher=str(publish_raw.get("publisher", "mock")),
            max_retries=int(publish_raw.get("max_retries", 3)),
            backoff_seconds=float(publish_raw.get("backoff_seconds", 1.0)),
            enable_browser=bool(publish_raw.get("enable_browser", False)),
        ),
        schedule=ScheduleConfig(
            mode=str(schedule_raw.get("mode", "after_close")),
            timezone=str(schedule_raw.get("timezone", "America/New_York")),
            cron_utc=str(schedule_raw.get("cron_utc", "30 22 * * 1-5")),
        ),
        data_dir=Path(str(raw.get("data_dir", "data"))),
        log_level=str(raw.get("log_level", "INFO")),
    )


def _apply_env(cfg: AppConfig) -> AppConfig:
    """环境变量覆盖 YAML（不读取任何值到日志中）。"""
    llm = cfg.llm
    provider = (_env("LLM_PROVIDER", llm.provider) or llm.provider).lower()
    base_url = _env("LLM_BASE_URL", llm.base_url) or llm.base_url
    model = _env("LLM_MODEL", llm.model) or llm.model
    api_key = _env("LLM_API_KEY", llm.api_key) or ""

    if provider == "dashscope":
        # 百炼预设：端点、模型与密钥来源都有合理默认值，
        # 密钥优先 LLM_API_KEY，其次 DASHSCOPE_API_KEY（本机常见写法）。
        base_url = _env("LLM_BASE_URL", DASHSCOPE_BASE_URL) or DASHSCOPE_BASE_URL
        model = _env("LLM_MODEL", DASHSCOPE_DEFAULT_MODEL) or DASHSCOPE_DEFAULT_MODEL
        api_key = api_key or (_env("DASHSCOPE_API_KEY", "") or "")

    llm = replace(
        llm,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=_env_float("LLM_TEMPERATURE", llm.temperature),
        max_tokens=_env_int("LLM_MAX_TOKENS", llm.max_tokens),
        timeout_seconds=_env_int("LLM_TIMEOUT_SECONDS", llm.timeout_seconds),
        anthropic_api_key=_env("ANTHROPIC_API_KEY", "") or "",
        anthropic_model=_env("ANTHROPIC_MODEL", llm.anthropic_model) or llm.anthropic_model,
        extra_body=_env_json("LLM_EXTRA_BODY_JSON", llm.extra_body),
    )

    market = replace(
        cfg.market,
        provider=_env("MARKET_PROVIDER", cfg.market.provider) or cfg.market.provider,
        stale_minutes=_env_int("MARKET_STALE_MINUTES", cfg.market.stale_minutes),
        timeout_seconds=_env_int("HTTP_TIMEOUT_SECONDS", cfg.market.timeout_seconds),
        finnhub_api_key=_env("FINNHUB_API_KEY", "") or "",
        alphavantage_api_key=_env("ALPHAVANTAGE_API_KEY", "") or "",
    )

    news = replace(
        cfg.news,
        lookback_hours=_env_int("NEWS_LOOKBACK_HOURS", cfg.news.lookback_hours),
        request_timeout_seconds=_env_int(
            "HTTP_TIMEOUT_SECONDS", cfg.news.request_timeout_seconds
        ),
        edgar_user_agent=_env("SEC_USER_AGENT", cfg.news.edgar_user_agent)
        or cfg.news.edgar_user_agent,
    )

    env_tickers = _env("USMARKET_TICKERS")
    watchlist = cfg.watchlist
    if env_tickers:
        watchlist = replace(watchlist, tickers=_tuple_of_str(env_tickers, watchlist.tickers))

    publish = replace(
        cfg.publish,
        publisher=_env("XHS_PUBLISHER", cfg.publish.publisher) or cfg.publish.publisher,
        max_retries=_env_int("PUBLISH_MAX_RETRIES", cfg.publish.max_retries),
        backoff_seconds=_env_float("PUBLISH_BACKOFF_SECONDS", cfg.publish.backoff_seconds),
        enable_browser=_env_bool("XHS_ENABLE_BROWSER", cfg.publish.enable_browser),
        mock_fail_first=_env_int("XHS_MOCK_FAIL_FIRST", cfg.publish.mock_fail_first),
    )

    return replace(
        cfg,
        llm=llm,
        market=market,
        news=news,
        watchlist=watchlist,
        publish=publish,
        offline=_env_bool("USMARKET_OFFLINE", cfg.offline),
        data_dir=Path(_env("USMARKET_DATA_DIR", str(cfg.data_dir)) or str(cfg.data_dir)),
        log_level=_env("LOG_LEVEL", cfg.log_level) or cfg.log_level,
    )


def load_config(path: Path | None = None, *, apply_env: bool = True) -> AppConfig:
    """加载配置：YAML → 环境变量。"""
    cfg_path = path or DEFAULT_CONFIG_PATH
    cfg = _build_from_yaml(_load_yaml(cfg_path))
    if apply_env:
        cfg = _apply_env(cfg)
    return cfg


def validate_sensitive_config(cfg: AppConfig) -> list[str]:
    """校验敏感配置：返回缺失项的名称列表（不返回值）。

    FR-059：对敏感配置进行校验。缺失项以名称形式返回，便于提示而不泄露内容。
    """
    missing: list[str] = []
    if cfg.llm.provider in {"openai_compatible", "dashscope"} and not cfg.llm.api_key:
        # dashscope 时该值也可由 DASHSCOPE_API_KEY 提供（见 _apply_env）
        missing.append("LLM_API_KEY")
    if cfg.llm.provider == "anthropic" and not cfg.llm.anthropic_api_key:
        missing.append("ANTHROPIC_API_KEY")
    if cfg.market.provider == "finnhub" and not cfg.market.finnhub_api_key:
        missing.append("FINNHUB_API_KEY")
    if cfg.market.provider == "alphavantage" and not cfg.market.alphavantage_api_key:
        missing.append("ALPHAVANTAGE_API_KEY")
    if cfg.publish.publisher == "browser" and not cfg.publish.enable_browser:
        missing.append("XHS_ENABLE_BROWSER")
    return missing

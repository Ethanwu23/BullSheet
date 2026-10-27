"""浏览器自动化发布适配器 —— **未验收，默认禁用**。

重要声明：
1. 本适配器未经过任何真实平台测试，`verified=False`，不得声称可用。
2. 小红书未向个人账号开放笔记发布 API；本适配器仅供**已取得明确授权**的
   自有账号在人工监督下使用，使用者自行承担平台规则风险。
3. 本项目**不实现**验证码绕过、指纹伪造、反检测规避等违反平台规则的功能。
4. 默认禁用：必须设置 XHS_PUBLISHER=browser 且 XHS_ENABLE_BROWSER=true 才加载，
   配置校验会阻止误用（config.validate_sensitive_config）。

因此本适配器只提供接口骨架与明确的"未实现"错误，不提供自动化登录或发布实现。
"""

from __future__ import annotations

import logging
from typing import Any

from usmarket.publishing.base import PublishOutcome, PublishPayload

LOGGER = logging.getLogger(__name__)


class BrowserPublisher:
    name = "browser"
    simulated = True    # 无真实调用
    verified = False    # 未经真实平台验证

    def __init__(self, *, enabled: bool = False, **_: Any) -> None:
        self.enabled = enabled
        if not enabled:
            LOGGER.warning(
                "browser 发布适配器已加载但未启用（XHS_ENABLE_BROWSER=false）。"
                "该适配器未经验收，真实发布能力不可用。",
                extra={"stage": "publish"},
            )

    def _refuse(self, action: str) -> None:
        raise NotImplementedError(
            f"{action}：browser 适配器未实现且未验收。"
            "小红书未向个人账号开放笔记发布 API；本仓库不提供自动化登录、"
            "验证码绕过或反检测功能。请使用 XHS_PUBLISHER=mock 跑通流程，"
            "或使用 manual_export 导出后人工发布。"
        )

    def validate_content(self, payload: PublishPayload) -> list[str]:
        return ["browser 适配器未实现：无法校验"]

    def upload_images(self, payload: PublishPayload) -> tuple[str, ...]:
        self._refuse("upload_images")
        return ()

    def create_draft(self, payload: PublishPayload, image_ids: tuple[str, ...]) -> str:
        self._refuse("create_draft")
        return ""

    def publish(self, payload: PublishPayload) -> PublishOutcome:
        return PublishOutcome(
            success=False,
            task_id="browser-unavailable",
            simulated=True,
            verified=False,
            error="browser 适配器未实现且未验收，真实发布能力不可用",
        )

    def get_publish_status(self, task_id: str) -> str:
        return "unavailable"

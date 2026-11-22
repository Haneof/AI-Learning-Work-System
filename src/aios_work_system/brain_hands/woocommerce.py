"""Read-only WooCommerce wp-admin product-page state observer."""

from __future__ import annotations

from typing import Any


async def woocommerce_product_state(page: Any) -> dict[str, Any]:
    """Return normalized product-form state without interacting with the page."""
    raise NotImplementedError

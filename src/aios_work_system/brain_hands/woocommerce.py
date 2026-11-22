"""Read-only WooCommerce wp-admin product-page state observer."""

from __future__ import annotations

from typing import Any


async def woocommerce_product_state(page: Any) -> dict[str, Any]:
    """Read product fields and notices from the current page without interacting with it."""
    return await page.evaluate(
        """() => {
            const first = (selectors) => {
                for (const selector of selectors) {
                    const element = document.querySelector(selector);
                    if (element) return element;
                }
                return null;
            };
            const fieldValue = (element) => {
                if (!element) return "missing";
                if ("value" in element) return String(element.value ?? "");
                return String(element.textContent ?? "");
            };
            const hasEditorContent = (selectors, iframeSelectors) => {
                const element = first(selectors);
                let value = "";
                if (element) {
                    value = "value" in element
                        ? String(element.value ?? "")
                        : String(element.textContent ?? "");
                }
                if (!value.trim()) {
                    const frame = first(iframeSelectors);
                    try {
                        value = frame?.contentDocument?.body?.innerText ?? "";
                    } catch {
                        value = "";
                    }
                }
                return Boolean(value.trim());
            };
            const title = first([
                "#title",
                'input[name="post_title"]',
                ".editor-post-title__input",
                '[data-testid="product-title"]'
            ]);
            const titleValue = fieldValue(title);
            const productType = first([
                "#product-type",
                'select[name="product-type"]'
            ]);
            const regularPrice = first([
                "#_regular_price",
                'input[name="_regular_price"]'
            ]);
            const notices = Array.from(document.querySelectorAll(
                "#message, .notice-success, .updated, .components-notice, [role='status']"
            ));
            const draftUpdated = notices.some((element) =>
                (element.innerText || element.textContent || "")
                    .toLowerCase()
                    .includes("product draft updated")
            );
            const isVisible = (element) => {
                if (!element) return false;
                const style = window.getComputedStyle(element);
                return element.getClientRects().length > 0
                    && style.display !== "none"
                    && style.visibility !== "hidden";
            };
            const publishSelectors = [
                "#publish",
                ".editor-post-publish-button",
                "button[aria-label='Publish']",
                "button[data-testid='publish']"
            ];
            const publishVisible = publishSelectors.some((selector) =>
                Array.from(document.querySelectorAll(selector)).some(isVisible)
            );

            return {
                title: {
                    value: titleValue,
                    status: !title ? "missing" : titleValue.trim() ? "present" : "empty"
                },
                product_type: {
                    value: productType ? fieldValue(productType) : "missing"
                },
                price: {
                    value: regularPrice ? fieldValue(regularPrice) : "missing"
                },
                description: {
                    present: hasEditorContent(
                        ["#content", 'textarea[name="content"]', ".wp-editor-area#content"],
                        ["#content_ifr", 'iframe[name="content_ifr"]']
                    )
                },
                short_description: {
                    present: hasEditorContent(
                        ["#excerpt", 'textarea[name="excerpt"]', ".wp-editor-area#excerpt"],
                        ["#excerpt_ifr", 'iframe[name="excerpt_ifr"]']
                    )
                },
                draft: {
                    status: draftUpdated ? "draft_updated" : "unknown"
                },
                publish: {
                    visible: publishVisible
                }
            };
        }"""
    )

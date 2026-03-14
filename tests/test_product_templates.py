"""Tests for product-specific template functions in src/generators/templates.py."""

from src.generators.templates import (
    PRODUCT_SYSTEM_PROMPT,
    build_product_prompt,
    _fmt_price,
    _build_products_section,
)


class TestProductSystemPrompt:
    """Verify product system prompt has required elements."""

    def test_mentions_tiktok_shop(self):
        assert "TikTok Shop" in PRODUCT_SYSTEM_PROMPT

    def test_mentions_price_anchoring(self):
        assert "price" in PRODUCT_SYSTEM_PROMPT.lower() or "Price" in PRODUCT_SYSTEM_PROMPT

    def test_mentions_social_proof(self):
        assert "social proof" in PRODUCT_SYSTEM_PROMPT.lower() or "reviews" in PRODUCT_SYSTEM_PROMPT.lower()

    def test_mentions_urgency(self):
        assert "urgency" in PRODUCT_SYSTEM_PROMPT.lower() or "Urgency" in PRODUCT_SYSTEM_PROMPT

    def test_requires_json_array(self):
        assert "JSON array" in PRODUCT_SYSTEM_PROMPT

    def test_requires_visual_hints(self):
        assert "visual_hints" in PRODUCT_SYSTEM_PROMPT

    def test_requires_video_style(self):
        assert "video_style" in PRODUCT_SYSTEM_PROMPT

    def test_requires_price_display(self):
        assert "price_display" in PRODUCT_SYSTEM_PROMPT

    def test_requires_rating_display(self):
        assert "rating_display" in PRODUCT_SYSTEM_PROMPT

    def test_mentions_tiktokshop_hashtag(self):
        assert "tiktokshop" in PRODUCT_SYSTEM_PROMPT.lower()

    def test_requires_aigc_hashtag(self):
        """AI-generated content must be disclosed per TikTok policy."""
        assert "aigc" in PRODUCT_SYSTEM_PROMPT.lower()

    def test_requires_product_id(self):
        """Product ID must be echoed back for downstream tracking."""
        assert "product_id" in PRODUCT_SYSTEM_PROMPT


class TestFmtPrice:
    """Tests for price formatting."""

    def test_whole_dollar(self):
        assert _fmt_price(12.0) == "$12"

    def test_with_cents(self):
        assert _fmt_price(12.99) == "$12.99"

    def test_zero(self):
        assert _fmt_price(0.0) == "$0"

    def test_large_price(self):
        assert _fmt_price(199.0) == "$199"


class TestBuildProductsSection:
    """Tests for product data section formatting."""

    def test_empty_products(self):
        result = _build_products_section([])
        assert result == []

    def test_single_product(self):
        products = [{
            "title": "Vitamin C Serum",
            "price": 12.99,
            "revenue_estimate": 150000,
            "sales_volume": 5000,
            "trend_direction": "rising",
            "category": "skincare",
            "product_id": "vc_serum_01",
        }]
        lines = _build_products_section(products)
        assert len(lines) >= 2  # header + at least one product
        assert "TOP-PERFORMING PRODUCTS" in lines[0]
        assert "Vitamin C Serum" in lines[1]
        assert "$12.99" in lines[1]
        assert "rising" in lines[1]
        assert "[ID: vc_serum_01]" in lines[1]

    def test_revenue_formatted(self):
        products = [{"title": "Product", "price": 10.0, "revenue_estimate": 1500000}]
        lines = _build_products_section(products)
        text = "\n".join(lines)
        assert "$1.5M revenue" in text

    def test_max_10_products(self):
        products = [{"title": f"Product {i}", "price": i} for i in range(15)]
        lines = _build_products_section(products)
        # Header + 10 products max
        assert len(lines) <= 11

    def test_top_video_links_included(self):
        products = [{
            "title": "Product",
            "price": 10.0,
            "product_id": "p1",
            "top_video_links": ["https://tiktok.com/v1", "https://tiktok.com/v2"],
        }]
        lines = _build_products_section(products)
        text = "\n".join(lines)
        assert "https://tiktok.com/v1" in text
        assert "https://tiktok.com/v2" in text
        assert "Study these videos" in text

    def test_top_video_links_limited_to_3(self):
        products = [{
            "title": "Product",
            "price": 10.0,
            "product_id": "p1",
            "top_video_links": [f"https://tiktok.com/v{i}" for i in range(5)],
        }]
        lines = _build_products_section(products)
        text = "\n".join(lines)
        assert "https://tiktok.com/v0" in text
        assert "https://tiktok.com/v2" in text
        assert "https://tiktok.com/v3" not in text  # limited to 3

    def test_product_id_in_prompt_line(self):
        products = [{
            "title": "Vitamin C Serum",
            "price": 12.99,
            "product_id": "prod_abc123",
        }]
        lines = _build_products_section(products)
        text = "\n".join(lines)
        assert "[ID: prod_abc123]" in text


class TestBuildProductPrompt:
    """Tests for build_product_prompt() output formatting."""

    def test_products_in_prompt(self):
        products = [
            {"title": "Test Serum", "price": 14.99, "revenue_estimate": 200000},
        ]
        prompt = build_product_prompt(products)
        assert "Test Serum" in prompt
        assert "TOP-PERFORMING PRODUCTS" in prompt

    def test_niche_in_prompt(self):
        products = [{"title": "Product", "price": 10.0}]
        prompt = build_product_prompt(products, niche="skincare")
        assert "skincare" in prompt
        assert "NICHE" in prompt

    def test_hooks_for_style_inspiration(self):
        products = [{"title": "Product", "price": 10.0}]
        hooks = [
            {"hook_text": "Stop scrolling right now", "stats": {"plays": 500000}},
        ]
        prompt = build_product_prompt(products, hooks=hooks)
        assert "TRENDING HOOK STYLES" in prompt
        assert "Stop scrolling" in prompt
        assert "500.0K plays" in prompt

    def test_hashtags_in_prompt(self):
        products = [{"title": "Product", "price": 10.0}]
        hashtags = [
            {"name": "tiktokshop", "viewCount": 10_000_000_000},
        ]
        prompt = build_product_prompt(products, hashtags=hashtags)
        assert "TRENDING HASHTAGS" in prompt
        assert "#tiktokshop" in prompt

    def test_num_scripts_matches_product_count(self):
        products = [
            {"title": "Product A", "price": 10.0},
            {"title": "Product B", "price": 20.0},
            {"title": "Product C", "price": 30.0},
        ]
        prompt = build_product_prompt(products, num_scripts=5)
        # Product mode: num_scripts is ignored, uses len(products) instead
        assert "exactly 3 scripts" in prompt

    def test_empty_products_fallback(self):
        prompt = build_product_prompt([])
        assert "No specific product data available" in prompt

    def test_mentions_tiktokshop_hashtag(self):
        products = [{"title": "Product", "price": 10.0}]
        prompt = build_product_prompt(products)
        assert "tiktokshop" in prompt.lower()

    def test_no_niche_no_section(self):
        products = [{"title": "Product", "price": 10.0}]
        prompt = build_product_prompt(products, niche="")
        assert "NICHE" not in prompt

    def test_backward_compatible_with_content_prompt(self):
        """Product prompt should work independently from content prompt."""
        from src.generators.templates import build_user_prompt
        content_prompt = build_user_prompt([], [])
        product_prompt = build_product_prompt([])
        # Both should be valid strings
        assert isinstance(content_prompt, str)
        assert isinstance(product_prompt, str)
        # They should be different
        assert content_prompt != product_prompt

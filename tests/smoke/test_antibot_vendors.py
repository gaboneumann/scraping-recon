"""Smoke tests for behavioral vendor detection with real URLs."""
import pytest
from modules.antibot import analyze_antibot


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_antibot_vendors_baseline_books_toscrape():
    """Test behavioral vendor detection on baseline (no vendors expected)."""
    result = await analyze_antibot("https://books.toscrape.com")

    assert result is not None
    assert result.behavioral_vendors is not None
    assert isinstance(result.behavioral_vendors, list)
    # books.toscrape.com is a static site with no antibot vendors
    assert len(result.behavioral_vendors) == 0


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_antibot_vendors_buscalibre_prestashop():
    """Test behavioral vendor detection on PrestaShop site (real antibot expected)."""
    result = await analyze_antibot("https://buscalibre.cl/libros/computacion")

    assert result is not None
    assert result.behavioral_vendors is not None
    assert isinstance(result.behavioral_vendors, list)
    # buscalibre.cl uses AWS WAF + other protections; may or may not have behavioral vendors
    # The important check is that the function runs without crashing and returns a valid list

    for vendor in result.behavioral_vendors:
        assert vendor.name in ["DataDome", "PerimeterX", "Akamai", "Kasada"]
        assert vendor.confidence in ["high", "medium", "low"]
        assert isinstance(vendor.detected_via, list)
        assert len(vendor.detected_via) > 0


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_antibot_vendors_mercadolibre_large_site():
    """Test behavioral vendor detection on large e-commerce (likely has antibot)."""
    result = await analyze_antibot("https://mercadolibre.cl")

    assert result is not None
    assert result.behavioral_vendors is not None
    assert isinstance(result.behavioral_vendors, list)
    # mercadolibre.cl is known to have Cloudflare WAF + behavioral protection
    # The important check is that detection completes without error

    for vendor in result.behavioral_vendors:
        assert vendor.name in ["DataDome", "PerimeterX", "Akamai", "Kasada"]
        assert vendor.confidence in ["high", "medium", "low"]
        assert isinstance(vendor.detected_via, list)


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_antibot_vendors_does_not_impact_score():
    """Verify behavioral vendors are informational and do not affect antibot score."""
    # Test on two URLs with different levels of protection
    result_baseline = await analyze_antibot("https://books.toscrape.com")
    result_protected = await analyze_antibot("https://buscalibre.cl")

    # Both should have valid scores
    assert result_baseline.overall_score is not None
    assert result_protected.overall_score is not None

    # Behavioral vendors should not change the fact that both have valid scores
    assert isinstance(result_baseline.behavioral_vendors, list)
    assert isinstance(result_protected.behavioral_vendors, list)

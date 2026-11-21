import html
import json
import os
import re
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-public-seo-tests")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from main import app


client = TestClient(app)


def visible_text(markup):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", "", markup))).strip()


def test_robots_and_sitemap_are_served_at_root():
    robots = client.get("/robots.txt")
    sitemap = client.get("/sitemap.xml")

    assert robots.status_code == 200
    assert "Sitemap: https://mymanagerh.com/sitemap.xml" in robots.text
    assert sitemap.status_code == 200
    assert "application/xml" in sitemap.headers["content-type"]

    root = ET.fromstring(sitemap.content)
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locations = [node.text for node in root.findall("sm:url/sm:loc", namespace)]
    assert locations == [
        "https://mymanagerh.com/ui/",
        "https://mymanagerh.com/ui/?page=terms",
        "https://mymanagerh.com/ui/?page=privacy",
    ]


def test_legal_aliases_redirect_to_stable_spa_urls():
    terms = client.get("/terms", follow_redirects=False)
    privacy = client.get("/privacy", follow_redirects=False)

    assert terms.status_code == 307
    assert terms.headers["location"] == "/ui/?page=terms"
    assert privacy.status_code == 307
    assert privacy.headers["location"] == "/ui/?page=privacy"

    terms_page = client.get(terms.headers["location"])
    privacy_page = client.get(privacy.headers["location"])
    assert terms_page.status_code == 200
    assert privacy_page.status_code == 200


def test_qr_verification_redirects_to_integrity_page():
    response = client.get("/v/AB12CD34EF56", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/ui/#/verify/AB12CD34EF56"


def test_public_pages_are_prerendered_with_matching_seo_metadata():
    pages = [
        ("/ui/", "https://mymanagerh.com/ui/", "home"),
        ("/ui/?page=terms", "https://mymanagerh.com/ui/?page=terms", "terms"),
        ("/ui/?page=privacy", "https://mymanagerh.com/ui/?page=privacy", "privacy"),
    ]

    for path, canonical, page_type in pages:
        response = client.get(path)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert '<meta name="robots" content="index,follow"' in response.text
        assert f'<link rel="canonical" href="{canonical}"' in response.text
        assert '<meta property="og:url" content="' + canonical + '"' in response.text
        assert '<meta property="og:image" content="https://mymanagerh.com/ui/assets/social/mymanagerh-social-card.png"' in response.text
        assert '<meta name="twitter:card" content="summary_large_image"' in response.text
        assert '<meta name="twitter:image" content="https://mymanagerh.com/ui/assets/social/mymanagerh-social-card.png"' in response.text
        assert response.text.count('rel="canonical"') == 1
        assert response.text.count('name="description"') == 1
        assert '<script type="module" src="app.js?v=137"></script>' in response.text
        assert 'lang="es-AR"' in response.text

        schema_match = re.search(
            r'<script id="mymanage-schema" type="application/ld\+json">(.*?)</script>',
            response.text,
            re.DOTALL,
        )
        assert schema_match
        graph = json.loads(schema_match.group(1))["@graph"]
        webpage = next(item for item in graph if item["@type"] == "WebPage")

        if page_type == "home":
            heading = re.search(r'<h1\b[^>]*>(.*?)</h1>', response.text, re.DOTALL).group(1)
            visible_description = re.search(
                r'<p class="hero-lead">(.*?)</p>', response.text, re.DOTALL
            ).group(1)
        else:
            heading = re.search(r'<h1\b[^>]*>(.*?)</h1>', response.text, re.DOTALL).group(1)
            article = re.search(
                r'<article class="docs-content[^"]*">(.*?)</article>',
                response.text,
                re.DOTALL,
            ).group(1)
            visible_description = re.search(
                r'<p\b[^>]*>(.*?)</p>', article, re.DOTALL
            ).group(1)

        assert webpage["url"] == canonical
        assert webpage["name"] == visible_text(heading)
        assert webpage["description"] == visible_text(visible_description)
        assert f'<meta property="og:title" content="{webpage["name"]} | MyManageRH"' in response.text
        assert f'<meta property="og:description" content="{webpage["description"]}"' in response.text
        assert f'"url":"{canonical}"' in schema_match.group(1)


def test_fallback_shell_has_no_public_canonical_and_links_are_crawlable():
    fallback = client.get("/ui/?page=login")
    assert fallback.status_code == 200
    assert 'rel="canonical"' not in fallback.text
    assert 'application/ld+json' not in fallback.text

    home = client.get("/ui/").text
    assert 'href="/ui/?page=terms"' in home
    assert 'href="/ui/?page=privacy"' in home

    terms = client.get("/ui/?page=terms").text
    assert 'href="/ui/?page=privacy"' in terms


def test_landing_prerender_uses_responsive_optimized_images():
    response = client.get("/ui/")
    assert response.status_code == 200
    assert 'srcset="./assets/landing/equipo-asesoramiento-480.webp 480w, ./assets/landing/equipo-asesoramiento-768.webp 768w"' in response.text
    assert 'src="./assets/landing/hub-historial-documentos.webp"' in response.text
    assert 'fetchpriority="high"' in response.text
    assert 'alt="Profesionales revisando información de gestión laboral en una computadora portátil"' in response.text
    assert 'resource_8MPyrSyYQQ37qJAhRh3_JT.png' not in response.text
    assert "Soluciones integrales para la gestión de tu personal: 40 años de trayectoria y tecnología propia." in response.text
    assert "Asesoramiento Laboral Especializado" in response.text
    assert "Liquidación Integral de Sueldos" in response.text
    assert "Hub Centralizado de Historial y Documentos" in response.text
    assert "Auditoría de firma verificable públicamente" in response.text
    assert "<h1>Gestión laboral con firma digital y auditoría inalterable</h1>" not in response.text

    image = client.get("/ui/assets/landing/equipo-asesoramiento-480.webp")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/webp"

    hub_image = client.get("/ui/assets/landing/hub-historial-documentos.webp")
    assert hub_image.status_code == 200
    assert hub_image.headers["content-type"] == "image/webp"

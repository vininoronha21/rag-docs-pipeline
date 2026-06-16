from app.services.markdown import clean_markdown, extract_title


def test_clean_markdown_removes_images_and_html_comments() -> None:
    content = "# Title\n\n<!-- internal -->\n\n![alt text](image.png)\n\n[local](docs/a.md)"

    cleaned = clean_markdown(content)

    assert "<!--" not in cleaned
    assert "alt text" in cleaned
    assert "local" in cleaned
    assert "docs/a.md" not in cleaned


def test_extract_title_prefers_first_h1() -> None:
    assert extract_title("text\n# API Guide\n## Next") == "API Guide"

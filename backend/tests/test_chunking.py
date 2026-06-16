from app.services.chunking import split_markdown


def test_split_markdown_preserves_heading_metadata() -> None:
    chunks = split_markdown("# Install\n\nRun pip install.\n\n## Usage\n\nCall the API.")

    assert len(chunks) == 2
    assert chunks[0].metadata["section"] == "Install"
    assert chunks[1].metadata["section"] == "Usage"
    assert "Call the API" in chunks[1].text


def test_split_markdown_splits_large_sections() -> None:
    content = "# Long\n\n" + " ".join(f"word{i}" for i in range(400))
    chunks = split_markdown(content, max_chars=300, overlap_chars=50)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 360 for chunk in chunks)

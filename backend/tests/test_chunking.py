from app.services.chunking import Chunk, chunk_content_hash, deduplicate_chunks, split_markdown


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


def test_chunk_hash_normalizes_whitespace() -> None:
    assert chunk_content_hash("Run   the command") == chunk_content_hash("Run the\ncommand")


def test_deduplicate_chunks_preserves_order_and_reindexes() -> None:
    chunks = [
        Chunk(text="Install", index=3, metadata={}, content_hash=chunk_content_hash("Install")),
        Chunk(text="Usage", index=4, metadata={}, content_hash=chunk_content_hash("Usage")),
        Chunk(text="Install", index=5, metadata={}, content_hash=chunk_content_hash("Install")),
    ]

    unique_chunks = deduplicate_chunks(chunks)

    assert [chunk.text for chunk in unique_chunks] == ["Install", "Usage"]
    assert [chunk.index for chunk in unique_chunks] == [0, 1]

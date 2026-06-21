import pytest

from app.db.models import Document, DocumentChunk
from app.services.chunking import Chunk
from app.services.repositories import upsert_document_with_chunks


class FakeDocumentSession:
    def __init__(self, existing: Document | None = None) -> None:
        self.existing = existing
        self.added: list[object] = []
        self.executed: list[object] = []
        self.flush_count = 0

    async def scalar(self, statement: object) -> Document | None:
        assert statement is not None
        return self.existing

    def add(self, item: object) -> None:
        self.added.append(item)

    async def execute(self, statement: object) -> None:
        self.executed.append(statement)

    async def flush(self) -> None:
        self.flush_count += 1
        for item in self.added:
            if isinstance(item, Document) and item.id is None:
                item.id = 10


def make_chunk(index: int, text: str = "Run the server.") -> Chunk:
    return Chunk(
        text=text,
        index=index,
        metadata={"section": "Run", "source_path": "docs/index.md"},
        content_hash=f"hash-{index}",
    )


@pytest.mark.asyncio
async def test_upsert_document_with_chunks_creates_document_and_chunks() -> None:
    session = FakeDocumentSession()

    document = await upsert_document_with_chunks(
        session,
        source="github",
        source_url="https://github.com/example/project/blob/main/docs/index.md",
        title="Install",
        content="# Install\n\nRun the server.",
        metadata={"repo": "example/project", "path": "docs/index.md"},
        chunks=[make_chunk(0)],
        embeddings=[[1.0, 0.0]],
        doc_source_id=3,
    )

    chunks = [item for item in session.added if isinstance(item, DocumentChunk)]
    assert document in session.added
    assert document.id == 10
    assert document.doc_source_id == 3
    assert document.source == "github"
    assert document.title == "Install"
    assert document.doc_metadata["repo"] == "example/project"
    assert len(chunks) == 1
    assert chunks[0].document_id == 10
    assert chunks[0].chunk_text == "Run the server."
    assert chunks[0].chunk_hash == "hash-0"
    assert chunks[0].embedding == [1.0, 0.0]
    assert session.flush_count == 2


@pytest.mark.asyncio
async def test_upsert_document_with_chunks_updates_existing_document() -> None:
    existing = Document(
        id=5,
        doc_source_id=1,
        source="github",
        source_url="https://github.com/example/project/blob/main/docs/index.md",
        title="Old title",
        content="Old content",
        doc_metadata={"repo": "old"},
    )
    session = FakeDocumentSession(existing)

    document = await upsert_document_with_chunks(
        session,
        source="github",
        source_url=existing.source_url,
        title="New title",
        content="New content",
        metadata={"repo": "example/project"},
        chunks=[make_chunk(0, "Updated content.")],
        embeddings=[[0.0, 1.0]],
        doc_source_id=9,
    )

    chunks = [item for item in session.added if isinstance(item, DocumentChunk)]
    assert document is existing
    assert existing.doc_source_id == 9
    assert existing.title == "New title"
    assert existing.content == "New content"
    assert existing.doc_metadata == {"repo": "example/project"}
    assert len(session.executed) == 1
    assert len(chunks) == 1
    assert chunks[0].document_id == 5
    assert chunks[0].chunk_text == "Updated content."
    assert session.flush_count == 2


@pytest.mark.asyncio
async def test_upsert_document_with_chunks_rejects_embedding_count_mismatch() -> None:
    session = FakeDocumentSession()

    with pytest.raises(ValueError, match="Expected one embedding per chunk"):
        await upsert_document_with_chunks(
            session,
            source="github",
            source_url="https://github.com/example/project/blob/main/docs/index.md",
            title="Install",
            content="# Install",
            metadata={},
            chunks=[make_chunk(0), make_chunk(1)],
            embeddings=[[1.0, 0.0]],
        )

    assert session.added == []
    assert session.executed == []
    assert session.flush_count == 0

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    text: str
    index: int
    metadata: dict[str, str | int | None]


def split_markdown(
    content: str,
    *,
    source_path: str | None = None,
    max_chars: int = 1200,
    overlap_chars: int = 180,
) -> list[Chunk]:
    sections = _split_sections(content)
    chunks: list[Chunk] = []

    for section_text, heading in sections:
        for text in _split_large_section(
            section_text,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        ):
            clean = text.strip()
            if clean:
                chunks.append(
                    Chunk(
                        text=clean,
                        index=len(chunks),
                        metadata={"section": heading, "source_path": source_path},
                    )
                )

    return chunks


def _split_sections(content: str) -> list[tuple[str, str | None]]:
    sections: list[tuple[str, str | None]] = []
    current: list[str] = []
    current_heading: str | None = None
    in_fence = False

    for line in content.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence

        is_heading = line.startswith("#") and not in_fence
        if is_heading and current:
            sections.append(("\n".join(current), current_heading))
            current = []

        if is_heading:
            current_heading = line.lstrip("#").strip() or current_heading

        current.append(line)

    if current:
        sections.append(("\n".join(current), current_heading))

    return sections or [(content, None)]


def _split_large_section(section: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    if len(section) <= max_chars:
        return [section]

    paragraphs = section.split("\n\n")
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = _tail(current, overlap_chars)

        if len(paragraph) > max_chars:
            chunks.extend(
                _split_by_words(
                    paragraph,
                    max_chars=max_chars,
                    overlap_chars=overlap_chars,
                )
            )
            current = ""
        else:
            current = f"{current}\n\n{paragraph}".strip() if current else paragraph

    if current:
        chunks.append(current)

    return chunks


def _split_by_words(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for word in words:
        projected = current_len + len(word) + (1 if current else 0)
        if projected > max_chars and current:
            chunk = " ".join(current)
            chunks.append(chunk)
            overlap = _tail(chunk, overlap_chars).split()
            current = overlap + [word]
            current_len = len(" ".join(current))
        else:
            current.append(word)
            current_len = projected

    if current:
        chunks.append(" ".join(current))

    return chunks


def _tail(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    tail = text[-max_chars:]
    first_space = tail.find(" ")
    return tail[first_space + 1 :] if first_space >= 0 else tail

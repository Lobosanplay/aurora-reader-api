from app.schemas.question import QuestionContext


class ContextService:
    def prepare(self, context: QuestionContext) -> str:
        # Label the untrusted title; preserve reading order without spending budget on duplicates.
        fragments = [context.title, context.current_chunk, *context.related_chunks]
        seen: set[str] = set()
        result: list[str] = []
        for index, fragment in enumerate(fragments):
            cleaned = fragment.strip()
            if cleaned and cleaned.casefold() not in seen:
                seen.add(cleaned.casefold())
                result.append(("Page title: " if index == 0 else "") + cleaned)
        return "\n".join(result)

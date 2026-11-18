from app.schemas.question import QuestionContext


class ContextService:
    def prepare(self, context: QuestionContext) -> str:
        # The current excerpt comes first; repeats do not consume provider context budget.
        fragments = [context.current_chunk, *context.related_chunks]
        seen: set[str] = set()
        result: list[str] = []
        for fragment in fragments:
            cleaned = fragment.strip()
            if cleaned and cleaned.casefold() not in seen:
                seen.add(cleaned.casefold())
                result.append(cleaned)
        return "\n".join(result)

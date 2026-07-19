
from backend.providers.base import ChatMessage


class PromptBuilder:
    """
    Dynamically constructs system and user prompts for RAG generation.
    Adapts instructions based on the query classification (factual, analytical, comparative, procedural).
    """

    def build_prompt(self, query: str, context: str, query_type: str = "factual") -> list[ChatMessage]:
        # 1. Base system prompt instructions enforcing strict grounding and source referencing
        system_content = (
            "You are a precise research assistant. Answer the user's question using ONLY the provided context.\n"
            "If the context does not contain enough information to answer fully, say so explicitly.\n"
            "For every factual claim, include a citation in the format [Source N].\n"
            "Do not introduce information not present in the context."
        )

        # 2. Query-type additions
        query_type_instructions = {
            "factual": "Provide a direct, concise answer. If multiple sources agree, cite all of them.",
            "analytical": "Analyze and synthesize across the provided sources. Identify agreements and contradictions.",
            "comparative": "Organize your response as a structured comparison. Use a table if appropriate.",
            "procedural": "Provide numbered steps. Each step must be cited."
        }

        # Safe fallback to "factual" if query_type is unrecognized
        addition = query_type_instructions.get(query_type.lower(), query_type_instructions["factual"])
        system_content += f"\n{addition}"

        # 3. Context formatting and user query injection
        user_content = (
            f"<context>\n{context}\n</context>\n\n"
            f"{query}"
        )

        return [
            ChatMessage(role="system", content=system_content),
            ChatMessage(role="user", content=user_content)
        ]

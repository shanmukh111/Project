from retrieval.hybrid_rag import (
    search_delivery_knowledge as hybrid_search_delivery_knowledge,
)


def build_analyst_tools(
    mark_source,
):
    """
    Builds the Hybrid RAG tool for the Insight Orchestrator
    (Delivery Analyst Agent).

    RAG belongs here, not on the Data Retrieval Agent: it returns
    guidance/interpretation content, not a live fact from a data
    source, and generating recommendations is the Analyst's job.
    """

    def search_delivery_knowledge(
        query: str,
        top_k: int = 3,
    ) -> dict:
        """
        Searches curated MAQ delivery knowledge using Hybrid RAG.

        Use only when the question needs guidance, interpretation,
        or a recommendation - e.g. "what should we do about this",
        "what does it mean if a sprint is behind". Do not use this
        to answer live factual questions; those come from the
        evidence already supplied to you, not from this tool.
        """

        mark_source(
            "MAQ Delivery Knowledge"
        )

        return (
            hybrid_search_delivery_knowledge(
                query=query,
                top_k=top_k,
            )
        )


    return [
        search_delivery_knowledge,
    ]
from typing import List, Dict, Any
from llama_index.core import TextNode
from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.core.schema import NodeWithScore

class LlamaIndexAdapter:
    """
    Thin adapter layer.
    Converts SQL/TAG facts into LlamaIndex Nodes
    and synthesizes a grounded response.
    """

    def __init__(self, llm):
        self.llm = llm

    def build_nodes(self, rows: List[Dict[str, Any]]) -> List[TextNode]:
        nodes: List[TextNode] = []

        for row in rows:
            text = row["text"]  # already human-readable
            metadata = row.get("metadata", {})

            node = TextNode(
                text=text,
                metadata=metadata,
            )
            nodes.append(node)

        return nodes

    def synthesize(
        self,
        query: str,
        nodes: List[TextNode],
        kshots: str | None = None,
        mode: str = "compact"
    ) -> str:
        """
        Uses LlamaIndex response synthesizer.
        LLM is only allowed to format + explain nodes.
        """

        node_scores = [NodeWithScore(node=n, score=1.0) for n in nodes]

        synthesizer = get_response_synthesizer(
            llm=self.llm,
            response_mode=mode,
            system_prompt=kshots,
        )

        response = synthesizer.synthesize(
            query=query,
            nodes=node_scores,
        )

        return str(response)
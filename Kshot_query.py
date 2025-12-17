from pathlib import Path
import xml.etree.ElementTree as ET


class KShotRewriter:
    def __init__(self, llm, examples_path: str):
        self.llm = llm
        self.examples = self._load_examples(examples_path)

    def _load_examples(self, path: str) -> list[dict]:
        tree = ET.parse(path)
        root = tree.getroot()

        examples = []
        for ex in root.findall("example"):
            examples.append({
                "query": ex.findtext("query"),
                "project": ex.findtext("project"),
                "version": ex.findtext("version"),
                "rewritten": ex.findtext("rewritten"),
            })
        return examples

    def rewrite(self, user_query: str, project: str | None, version: str | None) -> str:
        prompt = self._build_prompt(user_query, project, version)
        return self.llm.complete(prompt)

    def _build_prompt(self, user_query, project, version) -> str:
        ex_block = "\n".join(
            f"""
User Query: {e['query']}
Project: {e['project']}
Version: {e['version']}
Rewritten Query: {e['rewritten']}
""" for e in self.examples
        )

        return f"""
You rewrite user queries into optimal semantic search queries
for XML policy documents.

Normalize project and version as variables.

Examples:
{ex_block}

Now rewrite:

User Query: {user_query}
Project: {project or "ANY"}
Version: {version or "ANY"}

Rewritten Query:
"""
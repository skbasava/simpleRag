# planner.py
from typing import Dict, List


class Planner:
    """
    Converts parsed user intent into an executable plan.
    """

    def build_plan(self, intent: Dict) -> List[Dict]:
        """
        intent example:
        {
            "project": "Kaanapalli",
            "mpu": "AOSS_PERIPH_MPU_XPU4",
            "version": None,
            "addr_contains": None,
            "question": "What is the address range..."
        }
        """

        # Guardrails
        if not intent.get("project"):
            return [{
                "action": "CLARIFY",
                "params": {
                    "question": "Which project are you referring to?"
                }
            }]

        return [{
            "action": "HYBRID_SEARCH",
            "params": {
                "semantic_query": intent["question"],
                "filters": {
                    "project": intent["project"],
                    "version": intent.get("version"),
                    "mpu": intent.get("mpu"),
                    "addr_contains": intent.get("addr_contains"),
                }
            },
            "depends": []
        }]
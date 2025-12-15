from rag.router import route_query

def test_structured_query_routing():
    route = route_query(
        "Get policy for address range 0x01D24000 to 0x01D32000"
    )

    assert route.mode == "structured"


def test_semantic_query_routing():
    route = route_query(
        "Explain the security intent of ANOC IPA MPU"
    )

    assert route.mode == "semantic"

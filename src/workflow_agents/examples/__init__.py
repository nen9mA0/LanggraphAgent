__all__ = ["build_demo_graph", "run_demo"]


def __getattr__(name: str):
    if name in {"build_demo_graph", "run_demo"}:
        from .langgraph_demo import build_demo_graph, run_demo

        return {"build_demo_graph": build_demo_graph, "run_demo": run_demo}[name]
    raise AttributeError(name)

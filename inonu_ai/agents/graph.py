#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Agent Graph v3
Router → Query Rewriter → Retriever → Generator → Grader
"""

from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import (
    router_node,
    query_rewriter_node,
    retriever_node,
    generator_node,
    grader_node,
    MAX_ITERATIONS,
)


def route_decision(state: AgentState) -> str:
    return state.get("route", "rag")


def grade_decision(state: AgentState) -> str:
    if state.get("grade") == "useful":
        return "end"
    if state.get("iterations", 0) >= MAX_ITERATIONS:
        return "end"
    return "retry"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("router",   router_node)
    graph.add_node("rewriter", query_rewriter_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("generator", generator_node)
    graph.add_node("grader",    grader_node)

    graph.set_entry_point("router")

    # Router → RAG veya Direct
    graph.add_conditional_edges(
        "router",
        route_decision,
        {
            "rag":    "rewriter",   # RAG → önce rewrite
            "direct": "generator",  # Direct → direkt generator
        }
    )

    # RAG zinciri: Rewriter → Retriever → Generator → Grader
    graph.add_edge("rewriter",  "retriever")
    graph.add_edge("retriever", "generator")
    graph.add_edge("generator", "grader")

    # Grader → Bitir veya Tekrar
    graph.add_conditional_edges(
        "grader",
        grade_decision,
        {
            "end":   END,
            "retry": "retriever",
        }
    )

    return graph.compile()


_graph = None

def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run(question: str) -> str:
    graph = get_graph()
    initial: AgentState = {
        "question":           question,
        "rewritten_question": "",
        "session_id":         "",
        "history":            [],
        "route":              "",
        "documents":          [],
        "answer":             "",
        "grade":              "",
        "iterations":         0,
    }
    result = graph.invoke(initial)
    return result.get("answer", "Bu konuda bilgim bulunmuyor.")
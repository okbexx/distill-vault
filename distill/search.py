"""Vault search compatibility layer."""

from .search_hybrid import BM25Search, HybridSearch, VaultSearch

__all__ = ["BM25Search", "HybridSearch", "VaultSearch"]

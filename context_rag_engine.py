"""
Pihu V2 — RAG Context Engine (The Cognitive Filter)
Uses LlamaIndex to semantically filter noisy OCR/Clipboard data,
insulating the LLM from irrelevant background context.
"""
from llama_index.core import VectorStoreIndex, Document
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from logger import get_logger
import os

log = get_logger("RAG")

class ContextRAGEngine:
    def __init__(self):
        self.is_available = True
        try:
            # 1. Initialize Local Embedding Node (Fast CPU/GPU)
            # This allows us to index 5000 characters in milliseconds
            self.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")
            
            # 2. Local Reasoning Logic (Ollama)
            self.llm = Ollama(model="qwen2.5:3b", base_url="http://localhost:11434")
            
            log.info("🧩 Context RAG Engine Initialized (BGE-Small + Qwen)")
        except Exception as e:
            log.error("RAG Engine failed to initialize: %s", e)
            self.is_available = False

    def filter_context(self, user_query: str, raw_context: str, top_k: int = 5) -> str:
        """
        Creates a temporary Vector Index from the raw context dump,
        queries it with the user's intent, and returns only the relevant semantic shards.
        """
        if not self.is_available or not raw_context or len(raw_context) < 300:
            # If context is tiny, no need to filter it. Just return the raw string.
            return raw_context

        try:
            # 1. Index the raw string into memory as a singular Document
            # (Note: In production, we'd split into smaller chunks, but for Screen OCR, 
            # 5-10 lines is a perfect "node")
            doc = Document(text=raw_context)
            
            # 2. Create Instant In-Memory Vector Index
            index = VectorStoreIndex.from_documents(
                [doc], 
                embed_model=self.embed_model
            )
            
            # 3. Semantic Retrieval
            retriever = index.as_retriever(similarity_top_k=top_k)
            nodes = retriever.retrieve(user_query)
            
            # 4. Extract and join the relevant findings
            relevant_chunks = [node.get_content() for node in nodes]
            filtered = "\n---\n".join(relevant_chunks)
            
            log.info("🧩 RAG Filtered %d characters down to %d semantic chars.", len(raw_context), len(filtered))
            return filtered
            
        except Exception as e:
            log.error("Context RAG filtering failed: %s", e)
            return raw_context[-2000:] # Brute fallback

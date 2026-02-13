import os
import re
import pickle
import numpy as np
import faiss
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
from nexus.config import config

class SemanticMemory:
    """
    Persistent Semantic Memory using RAG with Semantic Chunking.
    """
    def __init__(self):
        self.storage_dir = config.MEMORY_DIR
        self.index_file = os.path.join(self.storage_dir, "index.faiss")
        self.metadata_file = os.path.join(self.storage_dir, "metadata.pkl")
        
        # Load params from config
        self.similarity_threshold = config.SIMILARITY_THRESHOLD
        
        print(f"[Memory] Loading Embedding Model: {config.EMBEDDING_MODEL}...")
        self.encoder = SentenceTransformer(config.EMBEDDING_MODEL)
        self.dimension = self.encoder.get_sentence_embedding_dimension()

        self.index = None
        self.chunks_metadata = []

        # Ensure storage exists
        os.makedirs(self.storage_dir, exist_ok=True)
        self.load_index()

    def load_index(self):
        """Load existing FAISS index and metadata"""
        if os.path.exists(self.index_file) and os.path.exists(self.metadata_file):
            try:
                self.index = faiss.read_index(self.index_file)
                with open(self.metadata_file, "rb") as f:
                    self.chunks_metadata = pickle.load(f)
                print(f"[Memory] Loaded {self.index.ntotal} memories.")
            except Exception as e:
                print(f"[Memory] Error loading index: {e}, starting fresh.")
                self.index = faiss.IndexFlatIP(self.dimension)
                self.chunks_metadata = []
        else:
            self.index = faiss.IndexFlatIP(self.dimension)
            self.chunks_metadata = []

    def save_index(self):
        """Save index to disk safely"""
        if self.index:
            # Write to temp files first
            tmp_index = self.index_file + ".tmp"
            tmp_meta = self.metadata_file + ".tmp"
            
            try:
                faiss.write_index(self.index, tmp_index)
                with open(tmp_meta, "wb") as f:
                    pickle.dump(self.chunks_metadata, f)
                    
                # Atomic-ish replace
                if os.path.exists(self.index_file): os.remove(self.index_file)
                os.rename(tmp_index, self.index_file)
                
                if os.path.exists(self.metadata_file): os.remove(self.metadata_file)
                os.rename(tmp_meta, self.metadata_file)
                
            except Exception as e:
                print(f"[Memory] Error saving index: {e}")
                # cleanup temp
                if os.path.exists(tmp_index): os.remove(tmp_index)
                if os.path.exists(tmp_meta): os.remove(tmp_meta)

    def clean_text(self, text: str) -> str:
        """Basic text cleaning"""
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def semantic_chunking(self, text: str, source: str = "interaction") -> List[Dict[str, Any]]:
        """
        Segment text based on semantic similarity of sentences.
        """
        text = self.clean_text(text)
        if not text:
            return []

        sentences = re.split(r'(?<=[.!?])\s+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return []

        if len(sentences) == 1:
            return [{
                "text": sentences[0],
                "embedding": self._embed_passage(sentences[0]),
                "metadata": {"source": source}
            }]

        prefixed = [f"passage: {s}" for s in sentences]
        embeddings = self.encoder.encode(prefixed, normalize_embeddings=True)
        
        final_chunks = []
        curr_chunk_sents = [sentences[0]]
        curr_chunk_emb = embeddings[0].reshape(1, -1)

        for i in range(1, len(sentences)):
            next_emb = embeddings[i].reshape(1, -1)
            sim = np.dot(curr_chunk_emb, next_emb.T)[0][0]
            
            # Simple length check (soft limit ~500 chars)
            current_text_len = len(" ".join(curr_chunk_sents))
            next_text_len = len(sentences[i])
            potential_len = current_text_len + 1 + next_text_len
            
            if sim >= self.similarity_threshold and potential_len <= 1000: # increased buffer
                # MERGE
                curr_chunk_sents.append(sentences[i])
                avg = np.mean(np.vstack([curr_chunk_emb, next_emb]), axis=0, keepdims=True)
                curr_chunk_emb = avg / np.linalg.norm(avg)
            else:
                # FINALIZE
                chunk_text = " ".join(curr_chunk_sents)
                final_chunks.append({
                    "text": chunk_text,
                    "embedding": curr_chunk_emb[0].astype('float32'),
                    "metadata": {"source": source}
                })
                # START NEW
                curr_chunk_sents = [sentences[i]]
                curr_chunk_emb = next_emb

        # Append last
        if curr_chunk_sents:
            chunk_text = " ".join(curr_chunk_sents)
            final_chunks.append({
                "text": chunk_text,
                "embedding": curr_chunk_emb[0].astype('float32'),
                "metadata": {"source": source}
            })

        return final_chunks

    def _embed_passage(self, text: str) -> np.ndarray:
        return self.encoder.encode([f"passage: {text}"], normalize_embeddings=True)[0]

    def add_memory(self, text: str, source: str = "user_input"):
        chunks = self.semantic_chunking(text, source)
        if not chunks: return

        new_vectors = []
        new_meta = []
        
        for chunk in chunks:
            new_vectors.append(chunk['embedding'])
            new_meta.append({
                "text": chunk['text'],
                "metadata": chunk['metadata'],
                "timestamp": __import__("time").time()
            })
            
        if new_vectors:
            vectors_np = np.stack(new_vectors)
            self.index.add(vectors_np)
            self.chunks_metadata.extend(new_meta)
            self.save_index()
            print(f"[Memory] Added {len(new_vectors)} semantic chunks.")

    def retrieve(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        if not self.index or self.index.ntotal == 0:
            return []

        query_emb = self.encoder.encode([f"query: {query}"], normalize_embeddings=True)[0]
        query_emb = query_emb.reshape(1, -1).astype("float32")
        
        distances, indices = self.index.search(query_emb, top_k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1: continue
            chunk = self.chunks_metadata[idx].copy()
            chunk['score'] = float(distances[0][i])
            results.append(chunk)
            
        return results

import io
import os
import re
import json
import math
import markdown
import sys
import subprocess
import asyncio
import aiofiles
import logging
import time
import mmap
from collections import Counter, deque
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from simplemma import lemmatize, simple_tokenizer
from magic_doc.docconv import DocConverter, S3Config
from utils import download_pandoc
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ProcessingStats:
    """Track document processing statistics."""
    total_files: int = 0
    processed_files: int = 0
    failed_files: int = 0
    total_chunks: int = 0
    processing_time: float = 0.0
    memory_usage: float = 0.0
    errors: List[str] = field(default_factory=list)

class ProcessingError(Exception):
    """Custom exception for document processing errors."""
    pass

class AsyncBM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75, cache_size: int = 1000):
        self.k1 = k1
        self.b = b
        self.index: Dict[str, List[Tuple[int, float]]] = {}
        self.doc_lengths: List[int] = []
        self.avg_doc_length: float = 0
        self.doc_count: int = 0
        self.idf_cache: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._term_cache = deque(maxlen=cache_size)  # LRU cache for terms
        self._batch_size = 1000  # Number of documents to process in batch
        self._pending_updates: List[Tuple[int, List[str]]] = []

    async def add_document(self, doc_id: int, terms: List[str]) -> None:
        """Add a document to the index asynchronously with batching."""
        self._pending_updates.append((doc_id, terms))
        
        if len(self._pending_updates) >= self._batch_size:
            await self._process_batch()

    async def _process_batch(self) -> None:
        """Process a batch of document updates."""
        async with self._lock:
            for doc_id, terms in self._pending_updates:
                term_freq = Counter(terms)
                doc_length = len(terms)
                
                # Extend doc_lengths if needed
                while len(self.doc_lengths) <= doc_id:
                    self.doc_lengths.append(0)
                
                self.doc_lengths[doc_id] = doc_length
                self.doc_count += 1
                
                # Update average document length
                self.avg_doc_length = (
                    (self.avg_doc_length * (self.doc_count - 1) + doc_length)
                    / self.doc_count
                )
                
                # Update index
                for term, freq in term_freq.items():
                    if term not in self.index:
                        self.index[term] = []
                    self.index[term].append((doc_id, freq))
                    
                    # Update term cache
                    if term not in self._term_cache:
                        self._term_cache.append(term)
            
            self._pending_updates.clear()

    @lru_cache(maxsize=10000)
    def _calculate_idf(self, term: str) -> float:
        """Calculate IDF with caching."""
        if term in self.idf_cache:
            return self.idf_cache[term]
        
        doc_freq = len(self.index.get(term, []))
        if doc_freq == 0:
            return 0
        
        idf = math.log(1 + (self.doc_count - doc_freq + 0.5) / (doc_freq + 0.5))
        self.idf_cache[term] = idf
        return idf

    async def search(
        self,
        query_terms: List[str],
        top_k: int = 10,
        timeout: float = 1.0
    ) -> List[Tuple[int, float]]:
        """Search with timeout and error handling."""
        try:
            async with self._lock:
                # Process any pending updates first
                if self._pending_updates:
                    await self._process_batch()
                
                # Use asyncio.wait_for for timeout
                return await asyncio.wait_for(
                    self._search_internal(query_terms, top_k),
                    timeout
                )
        except asyncio.TimeoutError:
            logger.warning("Search operation timed out")
            return []
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    async def _search_internal(
        self,
        query_terms: List[str],
        top_k: int
    ) -> List[Tuple[int, float]]:
        """Internal search implementation."""
        scores: Dict[int, float] = {}
        term_weights = Counter(query_terms)  # Consider term frequency in query
        
        for term, query_tf in term_weights.items():
            idf = self._calculate_idf(term)
            if idf == 0:
                continue
                
            for doc_id, tf in self.index.get(term, []):
                if doc_id >= len(self.doc_lengths):
                    continue  # Skip invalid document IDs
                    
                doc_length = self.doc_lengths[doc_id]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_length / self.avg_doc_length)
                term_score = idf * numerator / denominator * query_tf
                scores[doc_id] = scores.get(doc_id, 0) + term_score
        
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

async def process_document_chunk(
    chunk: str,
    doc_id: int,
    file_path: str,
    processed_folder: str,
    bm25_index: AsyncBM25Index,
    stats: ProcessingStats
) -> Optional[Dict[str, Any]]:
    """Process a single document chunk with error handling."""
    try:
        chunk_file_path = os.path.join(
            processed_folder, 
            f"{os.path.basename(file_path)}_{doc_id}.md"
        )
        
        # Ensure the chunk size is reasonable
        if len(chunk.encode('utf-8')) > 1024 * 1024:  # 1MB limit
            raise ProcessingError("Chunk size too large")
        
        async with aiofiles.open(chunk_file_path, 'w', encoding='utf8') as chunk_file:
            await chunk_file.write(chunk)

        normalized_chunk = normalize_text(chunk)
        words = list(simple_tokenizer(normalized_chunk))
        
        if not words:
            raise ProcessingError("Empty chunk after processing")
        
        document = {
            "id": doc_id,
            "file_path": chunk_file_path,
            "content": chunk,
            "normalized_content": normalized_chunk,
            "word_count": len(words)
        }
        
        await bm25_index.add_document(doc_id, words)
        stats.total_chunks += 1
        return document
        
    except Exception as e:
        logger.error(f"Error processing chunk from {file_path}: {str(e)}")
        stats.errors.append(f"Chunk {doc_id} from {file_path}: {str(e)}")
        return None

async def process_documents(
    folder_path: str,
    max_workers: Optional[int] = None,
    chunk_size: int = 1000,
    batch_size: int = 100
) -> Tuple[List[Dict], AsyncBM25Index, ProcessingStats]:
    """Process documents with performance optimization and error handling."""
    start_time = time.time()
    stats = ProcessingStats()
    
    try:
        await check_and_install_dependencies()
        
        processed_folder = os.path.join(folder_path, "processed_files")
        os.makedirs(processed_folder, exist_ok=True)

        # Initialize files
        index_file = os.path.join(processed_folder, "bm25_index.json")
        processed_documents_file = os.path.join(processed_folder, "processed_documents.json")
        processed_files_file = os.path.join(processed_folder, "processed_files.txt")

        # Load existing processed files
        processed_files = set()
        if os.path.exists(processed_files_file):
            async with aiofiles.open(processed_files_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                processed_files = set(content.splitlines())

        bm25_index = AsyncBM25Index()
        valid_extensions = {".txt", ".md", ".docx", ".odt", ".pptx", ".pdf", ".doc", ".ppt"}
        
        # Find new files efficiently
        new_files = []
        for root, _, files in os.walk(folder_path):
            if os.path.basename(root) == "processed_files":
                continue
            new_files.extend(
                os.path.join(root, file)
                for file in files
                if os.path.splitext(file)[1].lower() in valid_extensions
                and os.path.normcase(os.path.normpath(os.path.join(root, file))) not in processed_files
            )

        stats.total_files = len(new_files)

        # Load existing data if no new files
        if not new_files and os.path.exists(processed_documents_file) and os.path.exists(index_file):
            try:
                async with aiofiles.open(processed_documents_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    documents = json.loads(content)
                async with aiofiles.open(index_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    index_data = json.loads(content)
                    bm25_index.index = index_data['index']
                    bm25_index.doc_lengths = index_data['doc_lengths']
                    bm25_index.avg_doc_length = index_data['avg_doc_length']
                    bm25_index.doc_count = index_data['doc_count']
                return documents, bm25_index, stats
            except Exception as e:
                logger.error(f"Error loading existing data: {e}")
                # Continue with processing if loading fails

        documents = []
        converter = DocConverter(s3_config=None)
        
        # Process files in batches
        for i in range(0, len(new_files), batch_size):
            batch_files = new_files[i:i + batch_size]
            
            # Process batch concurrently
            async def process_file(file_path: str) -> None:
                try:
                    # Convert document in thread pool
                    loop = asyncio.get_event_loop()
                    with ThreadPoolExecutor(max_workers=max_workers) as pool:
                        markdown_content, _ = await loop.run_in_executor(
                            pool,
                            lambda: converter.convert(file_path, conv_timeout=300)
                        )
                    
                    chunks = chunk_content(markdown_content, chunk_size)
                    chunk_tasks = []
                    
                    # Process chunks concurrently
                    for j, chunk in enumerate(chunks):
                        doc_id = len(documents) + j
                        task = process_document_chunk(
                            chunk, doc_id, file_path,
                            processed_folder, bm25_index, stats
                        )
                        chunk_tasks.append(task)
                    
                    # Wait for all chunks to process
                    chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                    valid_chunks = [doc for doc in chunk_results if doc is not None]
                    documents.extend(valid_chunks)
                    
                    stats.processed_files += 1
                    
                except Exception as e:
                    logger.error(f"Error processing file {file_path}: {str(e)}")
                    stats.failed_files += 1
                    stats.errors.append(f"File {file_path}: {str(e)}")

            # Process batch of files
            batch_tasks = [process_file(file_path) for file_path in batch_files]
            await asyncio.gather(*batch_tasks)
            
            # Save progress periodically
            if len(documents) % 1000 == 0:
                await save_progress(
                    documents, bm25_index,
                    processed_documents_file, index_file
                )

        # Final save
        await save_progress(
            documents, bm25_index,
            processed_documents_file, index_file
        )
        
        # Update processed files list
        async with aiofiles.open(processed_files_file, 'w', encoding='utf-8') as f:
            await f.write('\n'.join(
                file for file in new_files
                if any(doc['file_path'].startswith(file) for doc in documents)
            ))
        
        # Update statistics
        stats.processing_time = time.time() - start_time
        stats.memory_usage = get_memory_usage()
        
        return documents, bm25_index, stats
        
    except Exception as e:
        logger.error(f"Fatal error in document processing: {str(e)}")
        stats.errors.append(f"Fatal error: {str(e)}")
        raise

async def save_progress(
    documents: List[Dict],
    bm25_index: AsyncBM25Index,
    documents_file: str,
    index_file: str
) -> None:
    """Save processing progress with error handling."""
    try:
        async with aiofiles.open(documents_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(documents))

        async with aiofiles.open(index_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps({
                'index': bm25_index.index,
                'doc_lengths': bm25_index.doc_lengths,
                'avg_doc_length': bm25_index.avg_doc_length,
                'doc_count': bm25_index.doc_count
            }))
    except Exception as e:
        logger.error(f"Error saving progress: {e}")

async def search(
    query: str,
    bm25_index: AsyncBM25Index,
    documents: List[Dict],
    top_k: int = 10,
    timeout: float = 1.0
) -> List[Dict]:
    """Enhanced search with timeout and error handling."""
    try:
        normalized_query = normalize_text(query)
        query_terms = list(simple_tokenizer(normalized_query))
        
        if not query_terms:
            return []
        
        ranked_docs = await bm25_index.search(query_terms, top_k, timeout)
        
        results = []
        for doc_id, score in ranked_docs:
            try:
                doc = documents[doc_id].copy()
                doc['score'] = score
                results.append(doc)
            except IndexError:
                logger.warning(f"Invalid document ID: {doc_id}")
                continue
        
        return results
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []

def get_memory_usage() -> float:
    """Get current memory usage in MB."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    except ImportError:
        return 0.0

# Helper functions with optimizations
def chunk_content(content: str, chunk_size: int = 1000) -> List[str]:
    """Optimized content chunking."""
    chunks = []
    current_pos = 0
    content_length = len(content)

    while current_pos < content_length:
        # Find the end of the current chunk
        chunk_end = min(current_pos + chunk_size, content_length)
        
        # Adjust chunk end to nearest sentence boundary
        if chunk_end < content_length:
            for separator in ('.', '!', '?', '\n\n'):
                last_separator = content.rfind(separator, current_pos, chunk_end + 50)
                if last_separator != -1:
                    chunk_end = last_separator + 1
                    break
        
        chunk = content[current_pos:chunk_end].strip()
        if chunk:
            chunks.append(chunk)
        current_pos = chunk_end

    return chunks

@lru_cache(maxsize=10000)
def normalize_text(text: str) -> str:
    """Cached text normalization."""
    text = text.lower()
    text = re.sub(r'[éèêë]', 'e', text)
    text = re.sub(r'[áàâä]', 'a', text)
    text = re.sub(r'[íìîï]', 'i', text)
    text = re.sub(r'[óòôö]', 'o', text)
    text = re.sub(r'[úùûü]', 'u', text)
    text = re.sub(r'ñ', 'n', text)
    return text
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
import tempfile
import traceback
from collections import Counter, deque
from typing import Dict, List, Set, Tuple, Optional, Any, AsyncGenerator
from dataclasses import dataclass, field, asdict
from simplemma import lemmatize, simple_tokenizer
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.document import ConversionResult, DoclingDocument
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import gc

# Configure logging with more detail
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Set specific loggers to WARNING level
pdfminer_logger = logging.getLogger('pdfminer')
pdfminer_logger.setLevel(logging.WARNING)

# Set layout_utils logger to WARNING
layout_utils_logger = logging.getLogger('layout_utils')
layout_utils_logger.setLevel(logging.WARNING)

# Set docling.models.layout_model logger to WARNING
layout_model_logger = logging.getLogger('docling.models.layout_model')
layout_model_logger.setLevel(logging.WARNING)

# Create a temp directory for document processing
TEMP_DIR = os.path.join(tempfile.gettempdir(), "clipbrd_processing")
os.makedirs(TEMP_DIR, exist_ok=True)

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
        self._term_cache = deque(maxlen=cache_size)
        self._batch_size = 1000
        self._pending_updates: List[Tuple[int, List[str]]] = []
        self._search_cache: Dict[str, Tuple[float, List[Tuple[int, float]]]] = {}
        self._cache_ttl = 300  # 5 minutes cache TTL
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._chunk_size = 1000  # Process documents in chunks to manage memory
        logger.debug("Initialized AsyncBM25Index with cache size %d", cache_size)

    async def add_document(self, doc_id: int, terms: List[str]) -> None:
        """Add a document to the index asynchronously with batching."""
        try:
            self._pending_updates.append((doc_id, terms))
            logger.debug(f"Added document {doc_id} to pending updates (size: {len(self._pending_updates)})")
            
            if len(self._pending_updates) >= self._batch_size:
                await self._process_batch()
                # Force garbage collection after batch processing
                gc.collect()
        except Exception as e:
            logger.error(f"Error adding document {doc_id}: {e}")
            raise

    async def _process_batch(self) -> None:
        """Process a batch of document updates with memory optimization."""
        async with self._lock:
            try:
                logger.debug(f"Processing batch of {len(self._pending_updates)} documents")
                # Process documents in chunks to manage memory
                for i in range(0, len(self._pending_updates), self._chunk_size):
                    chunk = self._pending_updates[i:i + self._chunk_size]
                    
                    for doc_id, terms in chunk:
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
                            
                            if term not in self._term_cache:
                                self._term_cache.append(term)
                    
                    # Clear processed chunk to free memory
                    del chunk
                    gc.collect()
                
                logger.debug(f"Processed {self.doc_count} documents, index size: {len(self.index)}")
                self._pending_updates.clear()
                
            except Exception as e:
                logger.error(f"Error processing batch: {e}")
                raise

    async def search(
        self,
        query_terms: List[str],
        *,
        top_k: int = 10,
        timeout: float = 5.0
    ) -> List[Tuple[int, float]]:
        """Optimized search with detailed logging."""
        try:
            if not query_terms:
                logger.warning("Empty query terms provided")
                return []

            # Ensure parameters are of correct type
            if not isinstance(query_terms, list):
                logger.warning(f"Invalid query_terms type: {type(query_terms)}")
                return []

            if not isinstance(top_k, int):
                logger.warning(f"Invalid top_k type: {type(top_k)}, using default value 10")
                top_k = 10

            if not isinstance(timeout, (int, float)):
                logger.warning(f"Invalid timeout type: {type(timeout)}, using default value 5.0")
                timeout = 5.0

            logger.debug(f"Searching for terms: {query_terms}, top_k: {top_k}")
            cache_key = f"{','.join(sorted(query_terms))}_{top_k}"
            current_time = time.time()

            # Check cache
            if cache_key in self._search_cache:
                timestamp, results = self._search_cache[cache_key]
                if current_time - timestamp < self._cache_ttl:
                    logger.debug(f"Cache hit for query: {cache_key}")
                    return results

            async with self._lock:
                try:
                    # Process any pending updates first
                    if self._pending_updates:
                        logger.debug("Processing pending updates before search")
                        await self._process_batch()

                    # Create and execute search task
                    try:
                        results = await asyncio.wait_for(
                            self._search_internal(query_terms, top_k),
                            timeout=timeout
                        )
                        
                        if results:
                            # Cache successful results
                            self._search_cache[cache_key] = (current_time, results)
                            logger.debug(f"Search completed with {len(results)} results")
                        else:
                            logger.debug("Search completed with no results")
                        
                        return results

                    except asyncio.TimeoutError:
                        logger.warning(f"Search timed out after {timeout}s")
                        return []
                    except asyncio.CancelledError:
                        logger.warning("Search was cancelled")
                        return []
                    except Exception as e:
                        logger.error(f"Error during search execution: {e}", exc_info=True)
                        return []

                except Exception as e:
                    logger.error(f"Error during search operation: {e}", exc_info=True)
                    return []

        except Exception as e:
            logger.error(f"Search error: {e}", exc_info=True)
            return []

    async def _search_internal(
        self,
        query_terms: List[str],
        top_k: int
    ) -> List[Tuple[int, float]]:
        """Optimized internal search with better error handling."""
        try:
            scores: Dict[int, float] = {}
            term_weights = Counter(query_terms)

            logger.debug(f"Processing {len(term_weights)} unique terms")
            term_tasks = []
            
            # Create tasks for each term
            for term, query_tf in term_weights.items():
                if not isinstance(query_tf, (int, float)):
                    logger.warning(f"Invalid query_tf type for term {term}: {type(query_tf)}")
                    continue
                # Create but don't await yet
                term_tasks.append(self._process_term(term, int(query_tf)))

            if not term_tasks:
                logger.warning("No valid terms to process")
                return []

            # Process all terms in parallel and await their completion
            try:
                term_results = await asyncio.gather(*term_tasks, return_exceptions=True)
            except Exception as e:
                logger.error(f"Error gathering term results: {e}", exc_info=True)
                return []
            
            # Process results
            for result in term_results:
                if isinstance(result, Exception):
                    logger.error(f"Term processing error: {result}")
                    continue
                if result:  # Check if result is not None or empty
                    for doc_id, score in result.items():
                        scores[doc_id] = scores.get(doc_id, 0) + score

            # Sort and get top k results
            sorted_scores = sorted(
                scores.items(),
                key=lambda x: x[1],
                reverse=True
            )[:top_k]

            logger.debug(f"Found {len(sorted_scores)} results")
            return sorted_scores

        except Exception as e:
            logger.error(f"Internal search error: {e}", exc_info=True)
            return []

    async def _process_term(self, term: str, query_tf: int) -> Dict[int, float]:
        """Process a single term with error handling."""
        try:
            term_scores = {}
            # Calculate IDF synchronously
            idf = self._calculate_idf(term)
            
            if idf == 0:
                return term_scores

            for doc_id, tf in self.index.get(term, []):
                try:
                    if not isinstance(doc_id, int):
                        logger.warning(f"Invalid doc_id type: {type(doc_id)}")
                        continue
                        
                    if doc_id >= len(self.doc_lengths):
                        logger.warning(f"doc_id {doc_id} out of range")
                        continue

                    doc_length = self.doc_lengths[doc_id]
                    # Calculate score synchronously
                    score = self._calculate_term_score(
                        float(tf), int(doc_length), float(idf), int(query_tf)
                    )
                    term_scores[doc_id] = score
                except Exception as e:
                    logger.error(f"Error processing doc_id {doc_id} for term {term}: {e}")
                    continue

            return term_scores

        except Exception as e:
            logger.error(f"Error processing term {term}: {e}")
            return {}

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

    def _calculate_term_score(
        self,
        tf: float,
        doc_length: int,
        idf: float,
        query_tf: int
    ) -> float:
        """Calculate BM25 score for a single term-document pair."""
        numerator = tf * (self.k1 + 1)
        denominator = tf + self.k1 * (1 - self.b + self.b * doc_length / self.avg_doc_length)
        return idf * numerator / denominator * query_tf

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

async def get_processed_files(processed_files_file: str) -> Set[str]:
    """Load the set of processed files, using absolute paths."""
    processed_files = set()
    if os.path.exists(processed_files_file):
        try:
            async with aiofiles.open(processed_files_file, 'r', encoding='utf-8') as f:
                async for line in f:
                    if line.strip():
                        processed_files.add(os.path.abspath(line.strip()))
            logger.debug(f"Loaded {len(processed_files)} previously processed files")
        except Exception as e:
            logger.error(f"Error loading processed files list: {str(e)}\n{traceback.format_exc()}")
    return processed_files

async def find_new_files(
    folder_path: str,
    processed_files: Set[str],
    valid_extensions: Set[str],
    stats: ProcessingStats
) -> AsyncGenerator[str, None]:
    """Yield new files that need processing, one at a time."""
    stats.total_files = 0  # Initialize total files counter
    try:
        for root, _, files in os.walk(folder_path):
            # Skip the processed_files directory and its subdirectories
            if "processed_files" in os.path.normpath(root).split(os.sep):
                continue
            
            for file in files:
                try:
                    file_path = os.path.join(root, file)
                    abs_file_path = os.path.abspath(file_path)
                    
                    if not os.path.exists(abs_file_path):
                        logger.warning(f"File does not exist: {abs_file_path}")
                        continue
                        
                    ext = os.path.splitext(file)[1].lower()
                    if ext in valid_extensions:
                        stats.total_files += 1  # Count total valid files
                        if abs_file_path not in processed_files:
                            if os.path.getsize(abs_file_path) > 0:
                                yield abs_file_path
                                logger.debug(f"Found new file to process: {abs_file_path}")
                            else:
                                logger.warning(f"Skipping empty file: {abs_file_path}")
                        else:
                            logger.debug(f"Skipping already processed file: {abs_file_path}")
                except Exception as e:
                    logger.error(f"Error checking file {file}: {str(e)}\n{traceback.format_exc()}")
    except Exception as e:
        logger.error(f"Error walking directory {folder_path}: {str(e)}\n{traceback.format_exc()}")
        raise

@dataclass
class DocumentMetadata:
    """Metadata for processed documents."""
    path: str
    last_modified: float
    size: int
    chunks: List[str]
    checksum: str = ""

async def get_file_checksum(file_path: str) -> str:
    """Calculate file checksum."""
    import hashlib
    try:
        async with aiofiles.open(file_path, 'rb') as f:
            content = await f.read()
            return hashlib.md5(content).hexdigest()
    except Exception as e:
        logger.error(f"Error calculating checksum for {file_path}: {e}")
        return ""

async def load_document_metadata(state_folder: str) -> Dict[str, DocumentMetadata]:
    """Load document metadata from state folder."""
    metadata_file = os.path.join(state_folder, "processed_documents.json")
    metadata = {}
    
    if os.path.exists(metadata_file):
        try:
            async with aiofiles.open(metadata_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                for path, info in data.items():
                    metadata[path] = DocumentMetadata(**info)
            logger.debug(f"Loaded metadata for {len(metadata)} documents")
        except Exception as e:
            logger.error(f"Error loading document metadata: {e}")
    
    return metadata

async def save_document_metadata(metadata: Dict[str, DocumentMetadata], state_folder: str) -> None:
    """Save document metadata to state folder."""
    metadata_file = os.path.join(state_folder, "processed_documents.json")
    temp_file = f"{metadata_file}.tmp"
    
    try:
        # Convert to dictionary for JSON serialization
        data = {path: asdict(meta) for path, meta in metadata.items()}
        
        # Write to temporary file first
        async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2))
        
        # Atomically rename
        os.replace(temp_file, metadata_file)
        logger.debug(f"Saved metadata for {len(metadata)} documents")
    except Exception as e:
        logger.error(f"Error saving document metadata: {e}")
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

async def load_saved_state(state_folder: str) -> Tuple[List[Dict[str, Any]], AsyncBM25Index]:
    """Load saved documents and index state."""
    documents_file = os.path.join(state_folder, "documents.json")
    index_file = os.path.join(state_folder, "index.json")
    documents = []
    bm25_index = AsyncBM25Index()

    try:
        # Load documents
        if os.path.exists(documents_file):
            async with aiofiles.open(documents_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                documents = json.loads(content)
                logger.info(f"Loaded {len(documents)} documents from saved state")

        # Load index
        if os.path.exists(index_file):
            async with aiofiles.open(index_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                index_data = json.loads(content)
                bm25_index.index = index_data['index']
                bm25_index.doc_lengths = index_data['doc_lengths']
                bm25_index.avg_doc_length = index_data['avg_doc_length']
                bm25_index.doc_count = index_data['doc_count']
                logger.info(f"Loaded index with {bm25_index.doc_count} documents")

        return documents, bm25_index
    except Exception as e:
        logger.error(f"Error loading saved state: {e}")
        return [], AsyncBM25Index()

async def process_documents(
    docs_folder: str,
    exclude_patterns: List[str] = None,
    batch_size: int = 10
) -> Tuple[List[Dict[str, Any]], AsyncBM25Index, ProcessingStats]:
    """Process documents in the given folder with improved detection."""
    stats = ProcessingStats()
    processed_folder = os.path.join(docs_folder, "processed_files")
    state_folder = os.path.join(processed_folder, "state")
    os.makedirs(state_folder, exist_ok=True)

    try:
        start_time = time.time()
        
        # Load existing metadata and state
        document_metadata = await load_document_metadata(state_folder)
        documents, bm25_index = await load_saved_state(state_folder)
        
        if documents and bm25_index.doc_count > 0:
            logger.info(f"Using existing index with {bm25_index.doc_count} documents")
            logger.info(f"Using {len(documents)} existing document chunks")
            
            # Check if any files need processing
            needs_processing = False
            for root, _, files in os.walk(docs_folder):
                if "processed_files" in os.path.normpath(root).split(os.sep):
                    continue
                
                for file in files:
                    file_path = os.path.join(root, file)
                    abs_file_path = os.path.abspath(file_path)
                    
                    if file.lower().endswith(('.pdf', '.txt', '.md', '.docx', '.pptx', '.html', '.doc', 'ppt')):
                        if abs_file_path not in document_metadata:
                            needs_processing = True
                            break
                        else:
                            meta = document_metadata[abs_file_path]
                            try:
                                if (meta.last_modified != os.path.getmtime(abs_file_path) or
                                    meta.size != os.path.getsize(abs_file_path) or
                                    meta.checksum != await get_file_checksum(abs_file_path)):
                                    needs_processing = True
                                    break
                            except OSError:
                                needs_processing = True
                                break
                
                if needs_processing:
                    break
            
            if not needs_processing:
                logger.info("No new or modified documents found, using existing state")
                stats.total_files = len(document_metadata)
                stats.processed_files = len(document_metadata)
                stats.processing_time = time.time() - start_time
                return documents, bm25_index, stats

        # Continue with normal processing if needed
        logger.info("Processing documents...")
        
        # Get all files in the directory
        all_files = []
        for root, _, files in os.walk(docs_folder):
            # Skip processed_files directory and excluded patterns
            rel_path = os.path.relpath(root, docs_folder)
            if "processed_files" in rel_path.split(os.sep):
                continue
                
            if exclude_patterns:
                skip = False
                for pattern in exclude_patterns:
                    if pattern.endswith('/*'):
                        dir_pattern = pattern[:-2]
                        if rel_path.startswith(dir_pattern):
                            skip = True
                            break
                if skip:
                    logger.debug(f"Skipping excluded directory: {rel_path}")
                    continue

            for file in files:
                file_path = os.path.join(root, file)
                abs_file_path = os.path.abspath(file_path)
                
                if file.lower().endswith(('.pdf', '.txt', '.md', '.docx', '.pptx', '.html', '.doc', 'ppt')):
                    # Check if file needs processing
                    needs_processing = True
                    if abs_file_path in document_metadata:
                        meta = document_metadata[abs_file_path]
                        try:
                            current_mtime = os.path.getmtime(abs_file_path)
                            current_size = os.path.getsize(abs_file_path)
                            current_checksum = await get_file_checksum(abs_file_path)
                            
                            if (meta.last_modified == current_mtime and 
                                meta.size == current_size and 
                                meta.checksum == current_checksum):
                                needs_processing = False
                                logger.debug(f"Skipping unchanged file: {abs_file_path}")
                        except OSError as e:
                            logger.error(f"Error checking file {abs_file_path}: {e}")
                    
                    if needs_processing:
                        all_files.append(abs_file_path)

        stats.total_files = len(all_files)
        logger.debug(f"Found {stats.total_files} files to process")

        # Process files in batches
        for i in range(0, len(all_files), batch_size):
            batch = all_files[i:i + batch_size]
            tasks = [process_file(file_path, processed_folder, bm25_index, stats) 
                    for file_path in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for file_path, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Error processing file: {result}")
                    stats.errors.append(str(result))
                    stats.failed_files += 1
                elif result:
                    documents.extend(result)
                    stats.processed_files += 1
                    
                    # Update metadata for processed file
                    try:
                        abs_path = os.path.abspath(file_path)
                        document_metadata[abs_path] = DocumentMetadata(
                            path=abs_path,
                            last_modified=os.path.getmtime(abs_path),
                            size=os.path.getsize(abs_path),
                            chunks=[doc['file_path'] for doc in result],
                            checksum=await get_file_checksum(abs_path)
                        )
                    except Exception as e:
                        logger.error(f"Error updating metadata for {file_path}: {e}")

            # Save progress after each batch
            await save_document_metadata(document_metadata, state_folder)
            await save_progress(documents, bm25_index, set(document_metadata.keys()),
                              os.path.join(state_folder, "documents.json"),
                              os.path.join(state_folder, "index.json"),
                              os.path.join(state_folder, "processed_files.txt"))

        stats.processing_time = time.time() - start_time
        stats.memory_usage = get_memory_usage()

        logger.info(f"Processing completed: {stats.processed_files} files processed, "
                   f"{stats.failed_files} failed, {len(documents)} chunks created")
        return documents, bm25_index, stats

    except Exception as e:
        logger.error(f"Error in process_documents: {e}")
        traceback.print_exc()
        raise ProcessingError(f"Failed to process documents: {str(e)}")

async def process_file(
    file_path: str,
    processed_folder: str,
    bm25_index: AsyncBM25Index,
    stats: ProcessingStats
) -> List[Dict[str, Any]]:
    """Process a single file and return its chunks."""
    try:
        # Initialize document converter with proper configuration
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True

        doc_converter = DocumentConverter(
            allowed_formats=[
                InputFormat.PDF,
                InputFormat.DOCX,
                InputFormat.PPTX,
                InputFormat.HTML,
                InputFormat.IMAGE,
            ],
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                    pipeline_cls=StandardPdfPipeline
                ),
            }
        )

        # Convert document using the new API
        logger.debug(f"Converting document: {file_path}")
        start_time = time.time()
        
        # Handle text files directly
        if file_path.lower().endswith(('.txt', '.md')):
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                if file_path.lower().endswith('.md'):
                    content = markdown.markdown(content)
                text = content
        else:
            # Convert using Docling for other formats
            conv_result = doc_converter.convert(file_path, raises_on_error=False)
            if not conv_result or not conv_result.document:
                raise ProcessingError(f"Failed to convert document: {file_path}")
            text = conv_result.document.export_to_markdown()

        logger.info(f"Finished converting document {os.path.basename(file_path)} in {time.time() - start_time:.2f} sec.")
        logger.debug(f"Successfully converted document: {file_path}")

        # Process chunks
        chunks = []
        doc_id_base = len(bm25_index.doc_lengths)
        
        for i, chunk in enumerate(split_into_chunks(text)):
            chunk_data = await process_document_chunk(
                chunk,
                doc_id_base + i,
                file_path,
                processed_folder,
                bm25_index,
                stats
            )
            if chunk_data:
                chunks.append(chunk_data)
        
        logger.debug(f"Created {len(chunks)} chunks for file: {file_path}")
        logger.debug(f"Successfully processed chunks for file: {file_path}")
        
        return chunks

    except Exception as e:
        logger.error(f"Error processing file {file_path}: {e}")
        traceback.print_exc()
        raise

def split_into_chunks(text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
    """Split text into overlapping chunks."""
    chunks = []
    if not text:
        return chunks
        
    words = text.split()
    current_chunk = []
    current_size = 0
    
    for word in words:
        word_size = len(word) + 1  # +1 for space
        if current_size + word_size > chunk_size and current_chunk:
            # Add current chunk to list
            chunks.append(' '.join(current_chunk))
            # Keep last 'overlap' words for next chunk
            overlap_words = current_chunk[-overlap:] if overlap < len(current_chunk) else current_chunk
            current_chunk = overlap_words
            current_size = sum(len(w) + 1 for w in current_chunk)
        
        current_chunk.append(word)
        current_size += word_size
    
    # Add the last chunk if it exists
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks

async def save_progress(
    documents: List[Dict],
    bm25_index: AsyncBM25Index,
    processed_files: Set[str],
    documents_file: str,
    index_file: str,
    processed_files_file: str
) -> None:
    """Save processing progress with atomic writes."""
    try:
        # Create temporary files
        temp_docs = f"{documents_file}.tmp"
        temp_index = f"{index_file}.tmp"
        temp_processed = f"{processed_files_file}.tmp"

        # Save to temporary files first
        async with aiofiles.open(temp_docs, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(documents, indent=2))

        async with aiofiles.open(temp_index, 'w', encoding='utf-8') as f:
            await f.write(json.dumps({
                'index': bm25_index.index,
                'doc_lengths': bm25_index.doc_lengths,
                'avg_doc_length': bm25_index.avg_doc_length,
                'doc_count': bm25_index.doc_count
            }, indent=2))
            
        async with aiofiles.open(temp_processed, 'w', encoding='utf-8') as f:
            await f.write('\n'.join(sorted(processed_files)))

        # Atomically rename temporary files to final files
        os.replace(temp_docs, documents_file)
        os.replace(temp_index, index_file)
        os.replace(temp_processed, processed_files_file)
            
        logger.debug("Successfully saved progress")
    except Exception as e:
        logger.error(f"Error saving progress: {str(e)}\n{traceback.format_exc()}")
        # Try to clean up temporary files
        for temp_file in [f"{documents_file}.tmp", f"{index_file}.tmp", f"{processed_files_file}.tmp"]:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception:
                pass

@lru_cache(maxsize=1000)
def _normalize_and_tokenize(query: str) -> List[str]:
    """Cached normalization and tokenization of queries."""
    normalized_query = normalize_text(query)
    return list(simple_tokenizer(normalized_query))

async def search(
    queries: List[str],
    bm25_index: AsyncBM25Index,
    documents: List[Dict],
    top_k: int = 10,
    timeout: float = 5.0  # Increased timeout
) -> List[Dict]:
    """Enhanced search with caching and parallel processing for multiple queries."""
    try:
        # Process each query and combine results
        all_results: Dict[int, float] = {}
        query_count: Dict[int, int] = {}  # Track how many queries matched each document
        
        for query in queries:
            # Use cached normalization and tokenization
            query_terms = _normalize_and_tokenize(query)
            
            if not query_terms:
                logger.warning(f"Empty query after normalization: {query}")
                continue
            
            logger.debug(f"Searching for terms: {query_terms}")
            
            # Get results for this query
            ranked_docs = await bm25_index.search(query_terms, top_k=top_k * 2, timeout=timeout)  # Get more results to combine
            
            # Combine scores and count query matches
            for doc_id, score in ranked_docs:
                all_results[doc_id] = all_results.get(doc_id, 0) + score
                query_count[doc_id] = query_count.get(doc_id, 0) + 1
        
        if not all_results:
            logger.warning("No results found for any query")
            return []
            
        # Adjust scores based on how many queries matched each document
        for doc_id in all_results:
            # Multiply score by (1 + number of matching queries) to boost documents matching multiple queries
            matches = query_count[doc_id]
            all_results[doc_id] = all_results[doc_id] * (1 + matches)
        
        # Sort by combined score and get top_k
        sorted_docs = sorted(
            all_results.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]
        
        logger.debug(f"Found {len(sorted_docs)} combined results")
        
        # Process results in parallel
        async def process_result(doc_tuple: Tuple[int, float]) -> Optional[Dict]:
            doc_id, score = doc_tuple
            try:
                doc = documents[doc_id].copy()
                doc['score'] = score
                doc['query_matches'] = query_count[doc_id]  # Add number of matching queries to result
                return doc
            except IndexError:
                logger.warning(f"Invalid document ID: {doc_id}")
                return None
        
        # Process all results concurrently
        result_tasks = [process_result(doc_tuple) for doc_tuple in sorted_docs]
        processed_results = await asyncio.gather(*result_tasks)
        
        # Filter out None results
        results = [r for r in processed_results if r is not None]
        
        logger.debug(f"Returning {len(results)} processed results")
        return results
        
    except Exception as e:
        logger.error(f"Search error: {str(e)}", exc_info=True)
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
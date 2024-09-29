import io
import os
import re
import json
import math
import markdown
import pypandoc
from pdftext.extraction import plain_text_output
from simplemma import lemmatize, simple_tokenizer
from utils import download_pandoc
import bisect

def process_documents(folder_path):
    processed_folder = os.path.join(folder_path, "processed_files")
    os.makedirs(processed_folder, exist_ok=True)

    inverted_index_file = os.path.join(processed_folder, "inverted_index.json")
    processed_documents_file = os.path.join(processed_folder, "processed_documents.txt")
    processed_files_file = os.path.join(processed_folder, "processed_files.txt")

    # Load existing processed files
    processed_files = set()
    if os.path.exists(processed_files_file):
        with open(processed_files_file, 'r', encoding='utf-8') as f:
            processed_files = set(f.read().splitlines())

    valid_extensions = {".txt", ".md", ".docx", ".odt", ".pptx", ".pdf", ".doc", ".ppt"}

    # Check for new files
    new_files = [
        os.path.join(root, file)
        for root, _, files in os.walk(folder_path)
        if os.path.basename(root) != "processed_files"
        for file in files
        if os.path.splitext(file)[1].lower() in valid_extensions
        and os.path.normcase(os.path.normpath(os.path.join(root, file))) not in processed_files
    ]

    if not new_files and os.path.exists(processed_documents_file) and os.path.exists(inverted_index_file):
        with open(processed_documents_file, 'r', encoding='utf-8') as f:
            documents = json.load(f)
        with open(inverted_index_file, 'r', encoding='utf-8') as f:
            inverted_index = json.load(f)
        return documents, inverted_index

    documents = []
    inverted_index = {}
    file_counter = {}

    for file_path in new_files:
        file_name, file_ext = os.path.splitext(os.path.basename(file_path))

        if file_name in file_counter:
            file_counter[file_name] += 1
            file_name = f"{file_name}_{file_counter[file_name]}"
        else:
            file_counter[file_name] = 1

        content = extract_content(file_path, file_ext)
        if content is None:
            continue

        chunks = chunk_content(content)

        for i, chunk in enumerate(chunks):
            chunk_file_path = os.path.join(processed_folder, f"{file_name}_{i}{file_ext}")
            with io.open(chunk_file_path, 'w', encoding='utf8') as chunk_file:
                chunk_file.write(chunk)

            normalized_chunk = normalize_text(chunk)
            words = list(simple_tokenizer(normalized_chunk))
            n_grams = generate_n_grams(words, max_n=5)

            document = {
                "file_path": chunk_file_path,
                "content": chunk,
                "normalized_content": normalized_chunk,
                "n_grams": n_grams
            }
            documents.append(document)

            # Update inverted index
            for n_gram in set(n_grams):
                inverted_index.setdefault(n_gram, []).append(len(documents) - 1)

        processed_files.add(os.path.normcase(os.path.normpath(file_path)))

    # Save processed documents and inverted index
    with open(processed_documents_file, 'w', encoding='utf-8') as f:
        json.dump(documents, f)

    with open(inverted_index_file, 'w', encoding='utf-8') as f:
        json.dump(inverted_index, f)

    with open(processed_files_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(processed_files))

    return documents, inverted_index

def extract_content(file_path, file_ext):
    if file_ext.lower() in [".docx", ".odt", ".pptx", ".ppt", ".doc"]:
        download_pandoc()
        return pypandoc.convert_file(file_path, 'markdown', outputfile=None)
    elif file_ext.lower() == ".pdf":
        return "\n".join(plain_text_output(file_path, sort=False))
    elif file_ext.lower() in [".txt", ".md"]:
        with io.open(file_path, 'rb') as f:
            file_content = f.read()
        try:
            content = file_content.decode('utf-8')
        except UnicodeDecodeError:
            content = file_content.decode('latin-1')
        if file_ext.lower() == ".md":
            content = markdown.markdown(content)
        return content
    return None

def chunk_content(content, chunk_size=1000, chunk_limit=1000):
    chunks = []
    for i in range(0, len(content), chunk_size):
        chunk = content[i:i + chunk_size]
        if len(chunk.encode('utf-8')) > chunk_limit:
            last_sentence_end = max(chunk.rfind('.'), chunk.rfind('!'), chunk.rfind('?'))
            if last_sentence_end != -1:
                chunk = chunk[:last_sentence_end + 1]
            else:
                chunk = chunk[:chunk_limit].rsplit(' ', 1)[0]
        chunks.append(chunk)
    return chunks

def normalize_text(text):
    text = text.lower()
    text = re.sub(r'[éèêë]', 'e', text)
    text = re.sub(r'[áàâä]', 'a', text)
    text = re.sub(r'[íìîï]', 'i', text)
    text = re.sub(r'[óòôö]', 'o', text)
    text = re.sub(r'[úùûü]', 'u', text)
    text = re.sub(r'ñ', 'n', text)
    return text

def generate_n_grams(words, max_n):
    return [
        ' '.join(words[i:i+n])
        for n in range(1, max_n + 1)
        for i in range(len(words) - n + 1)
    ]


    return inverted_index

def search(queries, inverted_index, documents):
    # Combine all queries into one text
    query_text = ' '.join(queries)

    # Tokenize and lemmatize the combined query
    query_words = list(simple_tokenizer(query_text))
    lemmatized_query_words = lemmatize(' '.join(query_words), lang=('en', 'es', 'fr')).split()

    # Generate n-grams from the query (up to 3-grams)
    query_n_grams = generate_n_grams(lemmatized_query_words, 3)

    relevant_doc_ids = set()
    for n_gram in query_n_grams:
        if n_gram in inverted_index:
            relevant_doc_ids.update(inverted_index[n_gram])

    relevant_documents = []
    for doc_id in relevant_doc_ids:
        document = documents[doc_id]
        content = document["normalized_content"]
        n_grams = document["n_grams"]

        # Calculate relevance based on exact matches and n-gram matches
        exact_match_count = sum(content.count(word) for word in lemmatized_query_words)
        n_gram_match_count = sum(n_grams.count(n_gram) for n_gram in query_n_grams)

        # Calculate TF-IDF score
        tf = (exact_match_count + n_gram_match_count) / len(n_grams)
        idf = math.log(len(documents) / (len(relevant_doc_ids) + 1))
        tfidf_score = tf * idf

        # Calculate proximity score
        proximity_score = calculate_proximity_score(content, query_n_grams)

        # Combine scores
        relevance_score = tfidf_score * 0.7 + proximity_score * 0.3

        relevant_documents.append({
            "file_path": document["file_path"],
            "relevance_score": relevance_score
        })

    # Sort the documents by their relevance score in descending order
    relevant_documents.sort(key=lambda x: x["relevance_score"], reverse=True)

    # Return the file paths of the relevant documents
    return [doc["file_path"] for doc in relevant_documents[:5]]

def calculate_proximity_score(content, query_n_grams):
    words = content.split()
    positions = []
    for n_gram in query_n_grams:
        n_gram_words = n_gram.split()
        for i in range(len(words) - len(n_gram_words) + 1):
            if words[i:i+len(n_gram_words)] == n_gram_words:
                positions.append(i)
    
    if not positions:
        return 0
    
    min_distance = float('inf')
    for i in range(len(positions)):
        for j in range(i+1, len(positions)):
            distance = positions[j] - positions[i]
            min_distance = min(min_distance, distance)
    
    return 1 / (1 + min_distance)

def binary_search(words, word):
    index = bisect.bisect_left(words, word)
    if index != len(words) and words[index] == word:
        return index
    return -1
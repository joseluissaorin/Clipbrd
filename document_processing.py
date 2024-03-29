import io
import os
import re
from nltk.stem import PorterStemmer, WordNetLemmatizer
import markdown
import pdfplumber
import pypandoc

def process_documents(folder_path):
    stemmer = PorterStemmer()
    lemmatizer = WordNetLemmatizer()
    processed_folder = os.path.join(folder_path, "processed_files")
    os.makedirs(processed_folder, exist_ok=True)

    documents = []
    processed_documents_file = os.path.join(processed_folder, "processed_documents.txt")

    if os.path.exists(processed_documents_file):
        with open(processed_documents_file, 'r', encoding='utf-8') as f:
            documents = eval(f.read())

    for root, _, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            file_name, file_ext = os.path.splitext(file)

            if file_ext.lower() in [".docx", ".odt", ".pptx", ".ppt", ".doc"]:
                content = pypandoc.convert_file(file_path, 'markdown', outputfile=None)
                output_format = ".md"
            elif file_ext.lower() == ".pdf":
                with pdfplumber.open(file_path) as pdf:
                    content = "\n".join(page.extract_text() for page in pdf.pages)
                output_format = ".txt"
            elif file_ext.lower() in [".txt", ".md"]:
                with io.open(file_path, 'r', encoding='utf8') as f:
                    content = f.read()
                if file_ext.lower() == ".md":
                    content = markdown.markdown(content)
                output_format = file_ext
            else:
                continue

            processed_file_path = os.path.join(processed_folder, f"{file_name}{output_format}")

            if os.path.exists(processed_file_path):
                continue

            words = re.findall(r'\b\w+\b', content.lower())
            stemmed_words = [stemmer.stem(word) for word in words]
            lemmatized_words = [lemmatizer.lemmatize(word) for word in words]

            chunk_size = 5000
            chunk_limit = 15 * 1024  # 15kb

            for i in range(0, len(content), chunk_size):
                chunk = content[i:i + chunk_size]
                if len(chunk.encode('utf-8')) > chunk_limit:
                    chunk = chunk[:chunk_limit].rsplit(' ', 1)[0]

                chunk_file_path = os.path.join(processed_folder, f"{file_name}_{i}{output_format}")
                with io.open(chunk_file_path, 'w', encoding='utf8') as chunk_file:
                    chunk_file.write(chunk)

                # Generate n-grams (up to 5-grams)
                n_grams_words = words[i:i + chunk_size]

                n_grams = []
                for n in range(1, 6):
                    n_grams.extend([' '.join(n_grams_words[i:i+n]) for i in range(len(n_grams_words)-n+1)])

                document = {
                    "file_path": chunk_file_path,
                    "content": chunk,
                    "words": words[i:i + chunk_size],
                    "stemmed_words": stemmed_words[i:i + chunk_size],
                    "lemmatized_words": lemmatized_words[i:i + chunk_size],
                    "n_grams": n_grams
                }
                documents.append(document)

    # Sort the word lists in each document for binary search
    for document in documents:
        document["words"].sort()
        document["stemmed_words"].sort()
        document["lemmatized_words"].sort()
        document["n_grams"].sort()

    with open(processed_documents_file, 'w', encoding='utf-8') as f:
        f.write(str(documents))

    return documents

def build_inverted_index(documents):
    inverted_index = {}
    for doc_id, document in enumerate(documents):
        for n_gram in document["n_grams"]:
            if n_gram not in inverted_index:
                inverted_index[n_gram] = []
            inverted_index[n_gram].append(doc_id)
    return inverted_index
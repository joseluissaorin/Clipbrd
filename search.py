import re
import bisect

def search(query, inverted_index, documents):
    # Directly use the query to search in the inverted index
    query = query.lower().strip()
    relevant_doc_ids = set()

    # Check if the entire query is present in the inverted index (as a phrase)
    if query in inverted_index:
        relevant_doc_ids.update(inverted_index[query])

    # Optionally, you can also search for individual words in the query
    # This can be useful if the exact phrase isn't found
    else:
        query_words = re.findall(r'\b\w+\b', query)
        for word in query_words:
            if word in inverted_index:
                relevant_doc_ids.update(inverted_index[word])

    relevant_documents = []
    for doc_id in relevant_doc_ids:
        document = documents[doc_id]
        content = document["content"].lower()

        # Calculate relevance based on presence of the query/words
        # Here, we simply check if the query or the words are in the content
        # This can be further refined based on your specific needs
        matches = 0
        if query in content:
            matches += 1
        else:
            for word in query_words:
                if word in content:
                    matches += 1
        
        # print(f"{matches} matches for {query}")

        total_words = len(re.findall(r'\b\w+\b', content))
        relevance_score = matches / total_words if total_words > 0 else 0

        # Use a relevance threshold to filter out less relevant documents
        threshold = 0.005
        if relevance_score >= threshold:
            relevant_documents.append({
                "file_path": document["file_path"],
                "relevance_score": relevance_score
            })

    # Sort the documents by their relevance score in descending order
    relevant_documents.sort(key=lambda x: x["relevance_score"], reverse=True)

    # Return the file paths of the relevant documents
    return [doc["file_path"] for doc in relevant_documents[:2]]

def binary_search(words, word):
    index = bisect.bisect_left(words, word)
    if index != len(words) and words[index] == word:
        return index
    return -1
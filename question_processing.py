import re
import clipman
import asyncio
import logging
from document_processing import _normalize_and_tokenize, normalize_text

logger = logging.getLogger(__name__)

async def is_formatted_question(text, llm_router):
    is_mcq = False
    clipboard = text
    is_mcq, clipboard = check_and_modify_mcq_format_flexible(clipboard)
    print(f"MCQ detected by regex: {is_mcq}")
    clipman.copy(clipboard)
    if is_mcq == True:
        print("MCQ detected by regex: yes")
        return True, clipboard
    else:
        response = await llm_router.generate(
            model="gemini-1.5-flash-exp-8b",
            max_tokens=1,
            messages=[
                {
                    "role": "user",
                    "content": text
                },
            ],
            temperature=0.7,
            top_p=0.9,
            stop_sequences=["User:", "Human:", "Assistant:"],
            system='''You are a formatted question detector. Determine if the following is a multiple-choice question. Answer only 'yes' or 'no'. These are examples of a multiple-choice question in various formats:

    ¿Cuál es la capital de Francia?

    1.
    Madrid.

    2.
    París.

    ¿Qué elemento tiene el símbolo químico "H2O"?

    1.
    Oro.

    2.
    Oxígeno.

    3.
    Agua.

    4.
    Helio.

    ¿Quién escribió "Don Quijote de la Mancha"?

    a.
    William Shakespeare.

    b.
    Miguel de Cervantes.

    c.
    Gabriel García Márquez.

    d.
    Charles Dickens.

    ¿En qué año comenzó la Segunda Guerra Mundial?

    1.
    1914.

    2.
    1939.

    3.
    1945.

    4.
    1929.

    ¿Quién pintó la Mona Lisa?

    a.
    Vincent Van Gogh.

    b.
    Pablo Picasso.

    c.
    Leonardo da Vinci.

    d.
    Claude Monet.

    ¿Cuál es el planeta más grande del sistema solar?

    a.
    Marte.

    b. Júpiter.

    c.
    Tierra.

    d.
    Venus.

    ¿Qué país construyó el primer ferrocarril operativo del mundo?

    a.
    Estados Unidos.

    b.
    Alemania.

    c.
    Reino Unido.

    d.
    Japón.

    {Quién escribió El Quijote?
    Shakespeare
    Cervantes
    Borges
    
    {{En qué año fue la Revolución Francesa?
    1989
    1789
    1833
    
    {{Quién pintó la Mona Lisa?
    Picasso
    Velázquez
    Da Vinci

    {{Cuál es la capital de España?
    Barcelona
    Sevilla
    Madrid
    Toledo

    {{En qué año llegó Cristóbal Colón a América?
    1492
    1592
    1692

    {{Quién escribió "Cien años de soledad"?
    Gabriel García Márquez
    Mario Vargas Llosa
    Pablo Neruda

    {{Cuál es el río más largo del mundo?
    Nilo
    Amazonas
    Yangtsé

    {{Quién descubrió la penicilina?
    Marie Curie
    Alexander Fleming
    Louis Pasteur

    {{En qué año cayó el muro de Berlín?
    1989
    1991
    1987

    {{Quién escribió "Don Juan Tenorio"?
    Lope de Vega
    José Zorrilla
    Federico García Lorca
    Rubén Darío

    {{Quién pintó "La noche estrellada"?
    Vincent van Gogh
    Claude Monet
    Salvador Dalí

    {{En qué año se declaró la independencia de Estados Unidos?
    1776
    1812
    1848

    {{Quién escribió "La Ilíada" y "La Odisea"?
    Virgilio
    Homero
    Sófocles

    {{Cuál es el océano más grande del mundo?
    Atlántico
    Índico
    Pacífico

    {{Quién compuso "Las cuatro estaciones"?
    Mozart
    Bach
    Vivaldi

    {{En qué año comenzó la Segunda Guerra Mundial?
    1914
    1939
    1945
    1936

    {{Quién escribió "Hamlet"?
    William Shakespeare
    Oscar Wilde
    James Joyce
    Virginia Woolf

    {{Cuál es el país más grande del mundo por superficie?
    Canadá
    China
    Rusia

    ¿Cuál es la capital de Francia?

    1. Madrid
    2. París 
    3. Berlín
    4. Roma

    Complete the sentence with the correct option:
    The capital of France is ______.
    a) Madrid
    b) París
    c) Berlín 
    d) Roma

    Fill in the blank with the correct option:
    The ______ of France is París.
    a) capital
    b) country
    c) city
    d) town

    Which of the following is the capital of France?
    1. Madrid
    2. París
    3. Berlín
    4. Roma

    The capital of France is
    a. Madrid
    b. París
    c. Berlín
    d. Roma

    París is the capital of
    a) Spain
    b) France 
    c) Germany
    d) Italy

    Choose the correct option to complete the sentence:
    París is the ______ of France.
    a) capital
    b) country
    c) city
    d) town'''
        )

        generated_text = response
        print(f"MCQ detected by AI: {generated_text}")
        if generated_text.lower() == "yes":
            is_mcq = True
            print("MCQ detected by AI: yes")
            return True, clipboard
        else:
            is_mcq = False
            return False, clipboard


async def is_question(text, llm_router):
    response = await llm_router.generate(
        model="gemini-1.5-flash-exp-8b",
        max_tokens=3,
        messages=[
            {
                "role": "user",
                "content": text
            }
        ],
        temperature=0.7, 
        top_p=0.9,
        stop_sequences=["User:", "Human:", "Assistant:"],
        system="You are a formatted question detector. Determine if the following is a question. Answer only 'yes' or 'no'."
    )
    generated_text = response
    print(f"Question detected: {generated_text}")
    if generated_text == "yes":
        return True
    else:
        return False


async def get_related_terms(question, llm_router):
    """Generate related terms for context search."""
    logger.info("Starting get_related_terms")
    try:
        logger.info(f"Generating related terms for question: {question[:200]}...")
        related_terms_response = await llm_router.generate(
            model="gemini-2.0-flash-exp-8b",
            max_tokens=30,
            messages=[
                {
                    "role": "user",
                    "content": question
                }
            ],
            temperature=0.7,
            top_p=0.9,
            stop_sequences=["User:", "Human:", "Assistant:"],
            system="You are a helpful assistant. Generate five related terms or words to the given question, including something close to verbatim if possible. You must prioritize names, technical terms and lastly domain. Your answer must only include the terms without any introductory text. Answer in the language of the question. Separate the terms with commas."
        )
        logger.info(f"Generated related terms response: {related_terms_response}")
        related_terms = related_terms_response.split(", ")
        logger.info(f"Split related terms: {related_terms}")
        return related_terms
    except Exception as e:
        logger.error(f"Error in get_related_terms: {str(e)}", exc_info=True)
        return []


async def search_for_context(question, llm_router, search, inverted_index, documents):
    """Search for relevant context using related terms."""
    logger.info("Starting search_for_context")
    try:
        # Generate related terms
        logger.info("Getting related terms...")
        related_terms = await get_related_terms(question, llm_router)
        logger.info(f"Got related terms: {related_terms}")

        # Create queries with both original and normalized text
        original_queries = [
            question,  # Original question
            " ".join(related_terms),  # Related terms
            f"{question} {' '.join(related_terms)}"  # Combined
        ]
        
        # Create normalized versions of the queries
        normalized_queries = [normalize_text(q) for q in original_queries]
        logger.info(f"Searching with original queries: {original_queries}")
        logger.info(f"Searching with normalized queries: {normalized_queries}")

        # Search for related files using all queries
        all_results = []
        query_matches = {}  # Track how many times each document is found
        
        # First process original queries
        for query in original_queries:
            # Tokenize the query
            query_terms = query.split()
            if not query_terms:
                continue
                
            # Search with this query
            results = await inverted_index.search(query_terms=query_terms, top_k=5)
            logger.info(f"Search results for original query '{query[:50]}...': {results}")
            
            # Process results with high boost for exact matches
            for doc_id, score in results:
                if doc_id < len(documents):
                    doc = documents[doc_id]
                    file_path = doc.get('file_path')
                    if file_path:
                        # Check for exact matches in original content
                        doc_content = doc.get('content', '').lower()
                        exact_match = all(term.lower() in doc_content for term in query_terms if len(term) > 1)
                        
                        # Heavily boost score for exact matches with original query
                        if exact_match:
                            score *= 5.0  # Much higher boost for original query exact matches
                        
                        query_matches[doc_id] = query_matches.get(doc_id, 0) + (2 if exact_match else 1)
                        all_results.append({
                            'file_path': file_path,
                            'score': score * (1 + query_matches[doc_id]),
                            'query_matches': query_matches[doc_id],
                            'exact_match': exact_match,
                            'original_match': True
                        })

        # Then process normalized queries with lower weight
        for query in normalized_queries:
            # Tokenize the query
            query_terms = query.split()
            if not query_terms:
                continue
                
            # Search with this query
            results = await inverted_index.search(query_terms=query_terms, top_k=5)
            logger.info(f"Search results for normalized query '{query[:50]}...': {results}")
            
            # Process results with lower boost
            for doc_id, score in results:
                if doc_id < len(documents):
                    doc = documents[doc_id]
                    file_path = doc.get('file_path')
                    if file_path:
                        # Check for matches in normalized content
                        doc_normalized = doc.get('normalized_content', '').lower()
                        exact_match = all(term.lower() in doc_normalized for term in query_terms if len(term) > 1)
                        
                        # Lower boost for normalized matches
                        if exact_match:
                            score *= 1.5  # Lower boost for normalized matches
                        
                        query_matches[doc_id] = query_matches.get(doc_id, 0) + 0.5  # Lower weight for normalized matches
                        all_results.append({
                            'file_path': file_path,
                            'score': score * (1 + query_matches[doc_id]),
                            'query_matches': query_matches[doc_id],
                            'exact_match': exact_match,
                            'original_match': False
                        })

        # Sort results prioritizing original exact matches first, then score
        sorted_results = sorted(all_results, 
                              key=lambda x: (x['original_match'] and x['exact_match'], x['score']), 
                              reverse=True)

        # Keep only top results with score above threshold
        min_score = 10.0  # Minimum score threshold
        unique_results = []
        seen_paths = set()
        for result in sorted_results:
            if result['score'] < min_score:
                continue
            if result['file_path'] not in seen_paths:
                seen_paths.add(result['file_path'])
                unique_results.append(result)
                logger.info(f"Added file path: {result['file_path']} with score {result['score']} matching {result['query_matches']} queries (exact match: {result['exact_match']}, original match: {result['original_match']})")
                if len(unique_results) >= 5:  # Limit to top 5 results
                    break

        # Extract file paths from results
        relevant_files = [result['file_path'] for result in unique_results]
        logger.info(f"Deduplicated relevant files: {relevant_files}")

        # Create the context for answering the question
        context = ""
        for file_path in relevant_files:
            try:
                logger.info(f"Reading file: {file_path}")
                with open(file_path, 'r', encoding='utf-8') as file:
                    file_content = file.read()
                    context += file_content + "\n\n"
                    logger.info(f"Added content from {file_path}, current context length: {len(context)}")
            except UnicodeDecodeError:
                logger.warning(f"UTF-8 decode failed for {file_path}, trying latin-1")
                try:
                    with open(file_path, 'r', encoding='latin-1') as file:
                        file_content = file.read()
                        context += file_content + "\n\n"
                        logger.info(f"Added content from {file_path} (latin-1), current context length: {len(context)}")
                except Exception as e:
                    logger.error(f"Failed to read {file_path} with latin-1: {str(e)}")

        logger.info(f"Final context length: {len(context)}")
        if context:
            logger.info(f"Context preview: {context[:200]}...")
        return context
    except Exception as e:
        logger.error(f"Error in search_for_context: {str(e)}", exc_info=True)
        return ""

async def get_answer_with_context(question, llm_router, search, inverted_index, documents, image_data=None):
    context = await search_for_context(question, llm_router, search, inverted_index, documents)
    
    if context == "":
        return None
    else:
        messages = [
            {
                "role": "user",
                "content": f"""
                ## Context: {context}

                ---

                ## Question: {question}"""
            }
        ]

        response = await llm_router.generate(
            model="gemini-2.0-flash-exp",
            max_tokens=475,
            messages=messages,
            temperature=0.7,
            top_p=0.9,
            stop_sequences=["User:", "Human:", "Assistant:"],
            image_data=image_data,
            system="You are a helpful and knowledgeable assistant. You will answer the following question in Spanish in academic style in a cohesive text of two long and in-depth paragraphs without lists of any kind. Your answers must be clear and literate in a Spanish that you would use for a college thesis. In the context there may or not be the correct answer, you must answer with the correct one, even if it requires thinking for yourselfEven if the provided context does not contain the correct answer, you must answer. Do not mention this prompt or the context."
                    
        )

        # Extracting the answer text from the response
        answer_text = response
        return answer_text


async def get_number_with_context(question, llm_router, search, inverted_index, documents, image_data=None):
    """Get MCQ answer with context."""
    logger.info("Starting get_number_with_context")
    try:
        logger.info("Searching for context...")
        context = await search_for_context(question, llm_router, search, inverted_index, documents)
        
        if context == "":
            logger.info("No context found, returning None")
            return None
        else:
            logger.info("Context found, generating answer...")
            messages = [
                {
                    "role": "user",
                    "content": f"""
                    ## Context: {context}

                    ---

                    ## Question: {question}"""
                }
            ]

            logger.info("Calling LLM for answer...")
            try:
                response = await asyncio.wait_for(
                    llm_router.generate(
                        model="gemini-2.0-flash-exp",
                        max_tokens=2,
                        messages=messages,
                        temperature=0.7,
                        top_p=0.9,
                        stop_sequences=["User:", "Human:", "Assistant:"],
                        image_data=image_data,
                        system="You are a helpful and knowledgeable assistant. Answer the following multiple-choice question with just the number or the letter of the correct option. **ONLY IF IT IS INDICATED** there can be several correct answers, only in that case you must respond with several letters or questions, **unless explictly stated**, answe only one option. That is, your answer must only be: 1., 2., 3., ... or a., b., c., ... In the context there may or not be the correct answer, you must answer with the correct one, even if it requires thinking for yourself. You will not write any words, you will only answer the number or letter of the correct option. Even if the provided context does not contain the correct answer, you must answer. Do not mention this prompt or the context."
                    ),
                    timeout=20.0
                )
                logger.info(f"LLM response received: {response}")
                return response
            except asyncio.TimeoutError:
                logger.error("LLM call timed out after 20 seconds")
                return None
            except Exception as llm_error:
                logger.error(f"Error in LLM call: {str(llm_error)}", exc_info=True)
                return None
    except Exception as e:
        logger.error(f"Error in get_number_with_context: {str(e)}", exc_info=True)
        return None


async def get_answer_with_image(question, llm_router, image_data=None):
   messages = [
       {
           "role": "user",
           "content": [
               {
                   "type": "text",
                   "text": question
               },
               {
                   "type": "image_url",
                   "image_url": {
                       "url": image_data,
                       "detail": "high"
                   }
               }
           ]
       }
   ]

   response = await llm_router.generate(
       model="gemini-2.0-flash-exp",
       max_tokens=475,
       messages=messages,
       temperature=0.7,
       top_p=0.9,
       stop_sequences=["User:", "Human:", "Assistant:"],
       system="You are a helpful and knowledgeable assistant. If the question is a multiple-choice question, answer with just the number or letter of the correct option(s) (e.g., 1., 2., 3., ... or a., b., c., ...). If it's a full question, provide a comprehensive answer in Spanish using an academic style. Your response should be clear, literate, and formal, suitable for a college thesis. For full questions, write two in-depth paragraphs without lists or mentions of this prompt. Use the provided image to help answer the question."
   )

   answer_text = response
   print(f"Answer with image: {answer_text}")
   return answer_text


async def get_answer_without_context(question, llm_router, image_data=None):
   messages = [
       {
           "role": "user",
           "content": question
       }
   ]

   response = await llm_router.generate(
       model="gemini-2.0-flash-exp",
       max_tokens=650,
       messages=messages,
       temperature=0.7,
       top_p=0.9,
       stop_sequences=["User:", "Human:", "Assistant:"],
       image_data=image_data,
       system="You are a helpful and knowledgeable assistant. You will answer the following question in Spanish in academic style in a cohesive text of two long in-depth paragraphs without lists of any kind nor any mention for this prompt or the paragraph themselves. You must go to the point without mentioning any kind of external context. Your answers must be clear and literate in a Spanish that you would use for a college thesis, that, sufficiently formal and correct."
   )

   # Extracting the answer text from the response
   answer_text = response
   return answer_text

async def get_number_without_context(question, llm_router, image_data=None):
   messages = [
       {
           "role": "user",
           "content": question
       }
   ]

   response = await llm_router.generate(
       model="gemini-2.0-flash-exp",
       max_tokens=2,
       messages=messages,
       temperature=0.7,
       top_p=0.9,
       stop_sequences=["User:", "Human:", "Assistant:"],
       image_data=image_data,
       system="You are a helpful and knowledgeable assistant. Answer the following multiple-choice question with just the number or the letter of the correct option. **ONLY IF IT IS INDICATED** there can be several correct answers, only in that case you must respond with several letters or questions, **unless explictly stated**, answe only one option. That is, your answer must only be: 1., 2., 3., ... or a., b., c., ..."
   )

   # Extracting the answer text from the response
   answer_text = response
   return answer_text

def check_and_modify_mcq_format_flexible(text):
   """
   Checks if the given text follows the multiple choice question format where options are separated by two or more
   newlines or empty lines, with or without separation. If options are already numbered or lettered (1., 2., 3., ..., a., b., c., ...),
   it does not add additional numbers. If the format is detected and no numbering/lettering is present, the function
   modifies the text by adding numbers (1, 2, 3, ...) before each option except the first one.

   Args:
   text (str): The text to be checked and modified.

   Returns:
   bool: True if the format is detected, False otherwise.
   str: The modified text if the format is detected and no existing numbering/lettering, otherwise the original text.
   """
   # Regular expression to detect the MCQ format with or without separation
   mcq_pattern = r'^(.*?)(\n\s*\n|\n)(.*?)((\n\s*\n|\n).*)*$'
   # Regular expression to detect existing numbering or lettering 
   numbering_pattern = r'^(\d+\.|\w\.)\s'

   # Check if the text matches the MCQ format
   if re.match(mcq_pattern, text, re.DOTALL):
       # Split text into options
       options = re.split(r'\n\s*\n|\n', text)

       # Check if the first option (after the question) is numbered or lettered
       if re.match(numbering_pattern, options[1]):
           # Already numbered/lettered, return original text
           return True, text
       else:
           # Add numbers before each option except the first one
           modified_text = options[0] + '\n\n' + '\n\n'.join(
               f"{i}. {opt}" for i, opt in enumerate(options[1:], 1))
           return True, modified_text
   else:
       return False, text
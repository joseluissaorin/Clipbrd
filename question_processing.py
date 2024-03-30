import re
import clipman

def is_formatted_question(text, llm_router):
    is_mcq = False
    clipboard = text
    is_mcq, clipboard = check_and_modify_mcq_format_flexible(clipboard)
    print(f"MCQ detected by regex: {is_mcq}")
    clipman.copy(clipboard)
    if is_mcq == True:
        print("MCQ detected by regex: yes")
        return True, clipboard
    else:
        response = llm_router.generate(
            model="claude-3-haiku-20240307",
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


def is_question(text, llm_router):
    response = llm_router.generate(
        model="claude-3-haiku-20240307",
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


def get_related_terms(question, llm_router):
   related_terms_response = llm_router.generate(
       model="claude-3-haiku-20240307",
       max_tokens=100,
       messages=[
           {
               "role": "user",
               "content": question
           }
       ],
       temperature=0.7,
       top_p=0.9,
       stop_sequences=["User:", "Human:", "Assistant:"],
       system="You are a helpful assistant. Generate five related terms or phrases to the given question, including something close to verbatim if possible. You must prioritize names, technical terms and lastly domain. Your answer must only include the terms without any introductory text. Separate the terms with commas."
   )
   related_terms = related_terms_response.split(", ")
   return related_terms


def get_answer_with_context(question, llm_router, search, inverted_index, documents, image_data=None):
   # Generate related terms using Claude 3 Haiku
   related_terms = get_related_terms(question, llm_router)

   # Search for related files  
   relevant_files = []
   for term in related_terms:
       print(f"Term: {term}")
       results = search(term, inverted_index, documents)
       relevant_files.extend(results)

   relevant_files = list(set(relevant_files))
   print(f"Relevant files: {relevant_files}")

   # Create the context for answering the question
   context = ""
   for file_path in relevant_files:
       try:
           with open(file_path, 'r', encoding='utf-8') as file:
               context += file.read() + "\n\n"
       except UnicodeDecodeError:
           try:
               with open(file_path, 'r', encoding='latin-1') as file:
                   context += file.read() + "\n\n"
           except UnicodeDecodeError:
               print(f"Skipping file {file_path} due to encoding issues.")

   print(f"Context found: {'yes' if context else 'no'}")
   if context == "":
       return None
   else:
       messages = [
           {
               "role": "user",
               "content": f"""
               Context: {context}

               ---

               Question: {question}"""
           }
       ]

       response = llm_router.generate(
           model="claude-3-sonnet-20240229",
           max_tokens=650,
           messages=messages,
           temperature=0.7,
           top_p=0.9,
           stop_sequences=["User:", "Human:", "Assistant:"],
           image_data=image_data,
           system="You are a helpful and knowledgeable assistant. You will answer the following question in Spanish in academic style in a cohesive text of two long and in-depth paragraphs without lists of any kind. Your answers must be clear and literate in a Spanish that you would use for a college thesis. Use the provided context to help answer the question."
       )

       # Extracting the answer text from the response
       answer_text = response
       return answer_text


def get_number_with_context(question, llm_router, search, inverted_index, documents, image_data=None):
   # Generate related terms using Claude 3 Haiku
   related_terms = get_related_terms(question, llm_router)

   # Search for related files
   relevant_files = []
   for term in related_terms:
       print(f"Term: {term}")
       results = search(term, inverted_index, documents)
       relevant_files.extend(results)

   relevant_files = list(set(relevant_files))

   print(f"Relevant files: {relevant_files}")
   # Create the context for answering the question
   context = ""
   for file_path in relevant_files:
       try:
           with open(file_path, 'r', encoding='utf-8') as file:
               context += file.read() + "\n\n"
       except UnicodeDecodeError:
           try:
               with open(file_path, 'r', encoding='latin-1') as file:
                   context += file.read() + "\n\n"
           except UnicodeDecodeError:
               print(f"Skipping file {file_path} due to encoding issues.")

   print(f"Context found: {'yes' if context else 'no'}")
   if context == "":
       return None
   else:
       messages = [
           {
               "role": "user",
               "content": f"""
               Context: {context}

               ---

               Question: {question}"""
           }
       ]

       response = llm_router.generate(
           model="claude-3-haiku-20240307",
           max_tokens=2,
           messages=messages,
           temperature=0.7,
           top_p=0.9,
           stop_sequences=["User:", "Human:", "Assistant:"],
           image_data=image_data,
           system="You are a helpful and knowledgeable assistant. Answer the following multiple-choice question with just the number or the letter of the correct option, if it is indicated, there can be several correct answers, only in that case you must respond with several letters or questions. That is, your answer must only be: 1., 2., 3., ... or a., b., c., ... Use the provided context to help answer the question."
       )

       # Extracting just the number from the response
       answer_text = response
       print(f"MCQ answer with context: {answer_text}")
       return answer_text


def get_number_without_context(question, llm_router, image_data=None):
   messages = [
       {
           "role": "user",
           "content": f"""{question}"""
       }
   ]

   response = llm_router.generate(
       model="claude-3-haiku-20240307",
       max_tokens=5,
       messages=messages,
       temperature=0.7,
       top_p=0.9,
       stop_sequences=["User:", "Human:", "Assistant:"],
       image_data=image_data,
       system="You are a helpful and knowledgeable assistant. Answer the following multiple-choice question with just the number or the letter of the correct option, if it is indicated, there can be several correct answers, only in that case you must respond with several letters or questions. That is, your answer must only be: 1., 2., 3., ... or a., b., c., ... "
   )

   # Extracting just the number from the response
   answer_text = response
   print(f"MCQ answer without context: {answer_text}")
   return answer_text


def get_number_with_image(question, llm_router, image_data=None):
   messages = [
       {
           "role": "user",
           "content": question
       }
   ]

   response = llm_router.generate(
       model="gpt-4-vision-preview",
       max_tokens=2,
       messages=messages,
       temperature=0.7,
       top_p=0.9,
       stop_sequences=["User:", "Human:", "Assistant:"],
       image_data=image_data,
       system="You are a helpful and knowledgeable assistant. Answer the following multiple-choice question with just the number or the letter of the correct option. That is, your answer must only be: 1., 2., 3., ... or a., b., c., ... Use the provided context to help answer the question."
   )

   # Extracting just the number from the response
   answer_text = response
   print(f"MCQ answer with image: {answer_text}")
   return answer_text


def get_answer_without_context(question, llm_router, image_data=None):
   messages = [
       {
           "role": "user",
           "content": question
       }
   ]

   response = llm_router.generate(
       model="claude-3-sonnet-20240229",
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
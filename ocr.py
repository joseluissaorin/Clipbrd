import base64
import requests
import io
import uuid
import os
import logging
from PIL import Image
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)

def split_image_into_chunks(image_data, chunk_size=1024*1024):
    """Split image data into chunks of specified size."""
    logger.debug(f"Splitting image of size {len(image_data)} bytes into chunks of {chunk_size} bytes")
    total_size = len(image_data)
    chunks = []
    for i in range(0, total_size, chunk_size):
        chunk = image_data[i:i + chunk_size]
        chunks.append(base64.b64encode(chunk).decode('utf-8'))
    logger.debug(f"Image split into {len(chunks)} chunks")
    return chunks

def upload_image_chunks(image_data, lang='spa+eng'):
    """Upload large image in chunks to the OCR API."""
    logger.info("Starting chunked image upload for OCR")
    file_id = str(uuid.uuid4())
    logger.debug(f"Generated file ID: {file_id}")
    
    chunks = split_image_into_chunks(image_data)
    total_chunks = len(chunks)
    logger.info(f"Uploading {total_chunks} chunks to OCR API")
    
    api_url = 'https://tess.joseluissaorin.com'
    
    for i, chunk_data in enumerate(chunks):
        logger.debug(f"Uploading chunk {i+1}/{total_chunks}")
        payload = {
            'file_id': file_id,
            'chunk_index': i,
            'total_chunks': total_chunks,
            'chunk_data': chunk_data,
            'lang': lang
        }
        
        try:
            response = requests.post(
                f"{api_url}/ocr/upload-chunk", 
                json=payload,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            response_data = response.json()
            
            if response_data.get('error'):
                logger.error(f"API Error during chunk upload: {response_data['error']}")
                raise Exception(f"API Error: {response_data['error']}")
                
            if response_data.get('status') == 'complete':
                logger.info("OCR processing completed successfully")
                return response_data.get('text')
                
            logger.debug(f"Upload progress: {response_data.get('chunks_received')}/{total_chunks} chunks")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Chunk upload failed: {str(e)}", exc_info=True)
            raise
            
    logger.error("Upload completed but no OCR result received")
    raise Exception("Upload completed but no OCR result received")

def ocr_image(base64_image, lang='spa+eng', mime_type='image/png'):
    """Perform OCR on an image using the API."""
    logger.info("Starting OCR process")
    
    try:
        # Remove data URL header if present
        if base64_image.startswith('data:'):
            logger.debug("Removing data URL header")
            base64_image = base64_image.split(',', 1)[1]
        
        # Decode base64 to get raw image data
        try:
            logger.debug("Decoding base64 image data")
            image_data = base64.b64decode(base64_image)
        except Exception as e:
            logger.error(f"Failed to decode base64 data: {e}", exc_info=True)
            raise Exception(f"Invalid base64 data: {str(e)}")
        
        # Check file size
        file_size = len(image_data)
        logger.info(f"Image size: {file_size/1024/1024:.2f}MB")
        
        if file_size > 5 * 1024 * 1024:  # 5MB
            logger.info("Image exceeds 5MB, using chunked upload")
            return upload_image_chunks(image_data, lang)
        
        # For smaller files, use regular upload
        logger.info("Using direct upload for OCR")
        url = 'https://tess.joseluissaorin.com/ocr'
        
        data = {
            'image': f'data:{mime_type};base64,{base64_image}',
            'lang': lang
        }
        
        logger.debug("Sending OCR request")
        response = requests.post(
            url, 
            headers={'Content-Type': 'application/json'}, 
            json=data
        )
        response.raise_for_status()
        
        result = response.json()
        
        if 'error' in result:
            error_message = result['error']
            details = result.get('details', '')
            logger.error(f"API Error: {error_message}. Details: {details}")
            raise Exception(f"API Error: {error_message}. Details: {details}")
                
        if 'text' in result:
            text_length = len(result['text'])
            logger.info(f"OCR completed successfully. Extracted {text_length} characters")
            logger.debug(f"OCR result preview: {result['text'][:200]}...")
            return result['text']
            
        logger.error(f"Unexpected response format: {result}")
        raise Exception('Unexpected response format: ' + str(result))
        
    except requests.exceptions.RequestException as e:
        logger.error(f"OCR request failed: {str(e)}", exc_info=True)
        if hasattr(e, 'response'):
            logger.error(f"Response content: {e.response.content}")
        raise
    except Exception as e:
        logger.error(f"OCR processing failed: {str(e)}", exc_info=True)
        raise

async def is_question_with_image(image_url_or_base64, llm_router):
    """Determine if an image contains a question with an image."""
    logger.debug("Checking if content contains a question with an image using Gemini.")
    try:
        # Extract base64 data and mime type from input
        if image_url_or_base64.startswith('data:image/'):
            header, base64_data = image_url_or_base64.split(',', 1)
            mime_type = header.split(';')[0].split(':')[1] # e.g., image/png
            logger.debug(f"Extracted mime_type: {mime_type} from data URL.")
        else:
            # Assume raw base64, default to png? Or raise error?
            # Let's assume PNG for now if no header, but log a warning.
            base64_data = image_url_or_base64
            mime_type = "image/png"
            logger.warning("Input for is_question_with_image lacked data URL header, assuming image/png.")

        image_input_data = {
            "base64": base64_data,
            "mime_type": mime_type
        }

        messages = [
            {
                "role": "user",
                "content": "Does the following image contain both a question (text) AND a distinct graphical image/diagram relevant to the question? Answer only 'yes' or 'no'."
                 # Content doesn't need image here, it's passed via image_data
            }
        ]

        response = await llm_router.generate(
            model="gemini-1.5-flash", # Ensure this model supports vision
            max_tokens=3,
            messages=messages,
            temperature=0.1, # Low temp for classification
            top_p=0.9,
            # stop_sequences=["User:", "Human:", "Assistant:"], # Optional for Gemini
            image_data=image_input_data, # Pass the structured image data
            system="You are an assistant that determines if an image contains both significant text (like a question) AND a relevant graphical image/diagram. Ignore logos or simple formatting. Answer only 'yes' or 'no'."
        )

        result = response.strip().lower()
        logger.info(f"Question with image detection response: {result}")
        return result == "yes"

    except Exception as e:
        logger.error(f"Error in is_question_with_image: {e}", exc_info=True)
        return False # Default to False on error

def extract_text_from_image(image_url, llm_router):
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant that extracts the question from an image. I will provide you with a fullscreen screenshot of a test or exam, you will determine which is the most probable question that the user is asking for and respond with the question formatted in markdown so it can be answered."
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Extract the question from the following screenshot of a test or exam in markdown format."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_url,
                        "detail": "low"
                    }
                }
            ]
        }
    ]

    response = llm_router.generate(
        model="gemini-2.0-flash",
        max_tokens=300,
        messages=messages,
        temperature=0.7,
        top_p=0.9,
        stop_sequences=["User:", "Human:", "Assistant:"],
    )

    generated_text = response
    return generated_text

async def extract_question_from_image_gemini(image_url_or_base64: str, llm_router) -> Optional[str]:
    """Extract question from an image using Gemini vision, preserving formulas/layout."""
    logger.info("Attempting to extract question from image using Gemini Vision")

    try:
        # Extract base64 data and mime type from input
        if image_url_or_base64.startswith('data:image/'):
            header, base64_data = image_url_or_base64.split(',', 1)
            mime_type = header.split(';')[0].split(':')[1]
            logger.debug(f"Extracted mime_type: {mime_type} from data URL.")
        else:
            base64_data = image_url_or_base64
            mime_type = "image/png"
            logger.warning("Input for extract_question_from_image_gemini lacked data URL header, assuming image/png.")

        # Prepare image data in the format expected by the updated llmrouter.py
        image_input_data = {
            "base64": base64_data,
            "mime_type": mime_type
        }

        # System prompt can be passed separately now
        system_prompt = """You are an expert OCR and question extraction assistant. Extract all text content from the image accurately, paying close attention to preserving mathematical formulas, code snippets, and the layout/numbering of multiple-choice options. After extracting the full text, identify the primary question within the extracted text and return *only* the formatted question (including all its options if it's a multiple-choice question). Preserve markdown formatting. Do not add any introductory text, explanation, or commentary. If it is an MCQ, include all options verbatim.

Example MCQ Output:
What is the derivative of x^2?

a) 2x
b) x
c) x^3 / 3
d) 1

Example Long-Answer Output:
Explain the process of photosynthesis, including the chemical equation.
"""

        messages = [
            {
                "role": "user",
                "content": "Extract the primary question from the provided image based on the instructions."
                # Content doesn't include the image here
            }
        ]

        model_to_use = "gemini-1.5-flash" # Ensure vision support
        
        logger.debug(f"Sending request to Gemini with image data of size {len(base64_data)}, mime_type: {mime_type}")
        
        try:
            response = await llm_router.generate(
                model=model_to_use,
                max_tokens=1024,
                messages=messages,
                temperature=0.1,
                top_p=0.9,
                image_data=image_input_data, # Pass structured image data
                system=system_prompt
            )
            logger.debug("Successfully received response from Gemini.")
        except Exception as api_e:
            logger.error(f"API error during Gemini Vision call: {api_e}", exc_info=True)
            raise ValueError(f"Gemini Vision API error: {api_e}") from api_e

        extracted_question = response.strip()
        if extracted_question:
            logger.info(f"Successfully extracted question using Gemini Vision: {extracted_question[:200]}...")
            # Log full only in debug
            logger.debug("Full extracted question (Gemini):")
            logger.debug("------------------------")
            logger.debug(extracted_question)
            logger.debug("------------------------")
            return extracted_question
        else:
            logger.warning("Gemini Vision did not return any text for question extraction.")
            return None

    except Exception as e:
        logger.error(f"Error extracting question with Gemini Vision: {e}", exc_info=True)
        return None

async def extract_question_from_ocr(image_url_or_base64, llm_router):
    # This function uses the *text* from OCR, not the image directly with LLM
    logger.info("Starting standard OCR + LLM question extraction pipeline.")
    try:
        # Perform OCR using the existing function (expects base64 string)
        logger.debug("Performing OCR...")
        ocr_text = ocr_image(base64_image=image_url_or_base64) # Pass the base64 string
        if not ocr_text:
            logger.warning("OCR returned no text.")
            return None
        logger.info(f"OCR successful, extracted {len(ocr_text)} characters.")

        # Now, use LLM to extract and format the question from the OCR text
        system_prompt = """You are a helpful assistant that extracts questions from OCR text. The text is from a screenshot of a test or exam. A question will be EITHER an MCQ OR a long-answer question, never both.

DEFINITION OF MCQ (Multiple Choice Question):
An MCQ consists of two parts that MUST ALWAYS BE PRESERVED TOGETHER:
1. A question/statement part that:
   - Can end with a question mark (?)
   - Can end with ellipsis (...)
   - Can be an incomplete statement
   - Is followed by options

2. An options part that:
   - Contains 2 or more choices
   - Each option is on a separate line
   - Options can be marked with:
     * Letters (a), b), c), etc.)
     * Numbers (1., 2., 3., etc.)
     * Simple lines without markers
   - Options are typically short (one line each)
   - Options are mutually exclusive choices
   - MUST ALWAYS BE INCLUDED IN THE OUTPUT

DEFINITION OF LONG-ANSWER QUESTION:
A long-answer question consists of two parts:
1. A question/statement part that:
   - Usually ends with a question mark (?)
   - Can be a directive ("Explain...", "Describe...", etc.)
   - Can include multiple sentences
   - Asks for explanation, analysis, or description

2. A context part (optional) that:
   - Provides background information
   - Can include quotes or references
   - May contain multiple paragraphs
   - Helps frame the question

Your task is to:
1. Extract the COMPLETE question, including ALL options for MCQs
2. Preserve the EXACT format and structure
3. Format in markdown
4. Do not add any commentary, labels, or try to answer
5. Do not add "Question Type" or any other metadata

IMPORTANT: 
- For MCQs: You MUST include ALL options exactly as they appear
- Never omit or summarize the options
- Keep the exact format and numbering of options
- Maintain empty lines between question and options

Format examples:
1. MCQ with question mark:
¿Cuál fue la capital de Prusia?

a) Berlín
b) Hamburgo
c) Múnich
d) Frankfurt

2. MCQ with ellipsis:
La capital de Prusia era...

1. Berlín
2. Hamburgo
3. Múnich
4. Frankfurt

3. MCQ with simple options:
Selecciona el planeta más grande:

Júpiter
Saturno
Urano
Neptuno

4. Long-answer with context:
La Revolución Industrial marcó un punto de inflexión en la historia humana. Considera su impacto en la sociedad y el medio ambiente.

Explica cómo la Revolución Industrial transformó tanto las estructuras sociales como las condiciones ambientales en Europa durante el siglo XIX.

Remember: 
- NEVER omit options from MCQs
- Keep ALL formatting exactly as in original
- Do not add any labels or metadata
- Preserve empty lines between parts"""
        messages = [
             # ... (Existing system prompt definition) ...
             {
                "role": "user",
                "content": f"Extract and format the COMPLETE question from the following OCR text, preserving ALL options if it's an MCQ:\n\n{ocr_text}"
             }
        ]
        # Use a text-based model, or Gemini can handle text too
        model_to_use = "gemini-1.5-flash" # Or keep existing experimental model if preferred for text
        response = await llm_router.generate(
            model=model_to_use, # or "gemini-2.0-flash-exp"
            max_tokens=500,
            messages=messages,
            temperature=0.2,
            top_p=0.9,
            # No image_data passed here
            system=system_prompt
        )
        extracted_question = response.strip()
        logger.info(f"LLM extracted question from OCR text: {extracted_question[:200]}...")
        return extracted_question

    except Exception as e:
        logger.error(f"Error in extract_question_from_ocr pipeline: {e}", exc_info=True)
        return None # Return None on error

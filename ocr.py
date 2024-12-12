import base64
import requests
import io
import uuid
import os
import logging
from PIL import Image

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

async def is_question_with_image(image_url, llm_router):
    """Determine if an image contains a question with an image."""
    try:
        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant that determines if an image contains a question with an image or just text. If it is only text answer 'no', if it has both text and an image answer 'yes'. Answer only 'yes' or 'no'."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Does the following image contain a question with an image?"
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

        response = await llm_router.generate(
            model="gemini-2.0-flash-exp",
            max_tokens=3,
            messages=messages,
            temperature=0.7,
            top_p=0.9,
            stop_sequences=["User:", "Human:", "Assistant:"],
        )

        logger.info(f"Question with image detection response: {response}")
        return response.strip().lower() == "yes"
    except Exception as e:
        logger.error(f"Error in is_question_with_image: {e}", exc_info=True)
        return False

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

async def extract_question_from_ocr(image_url, llm_router):
    # First, perform OCR on the image
    ocr_text = ocr_image(base64_image=image_url)

    # Now, use LLM to extract and format the question from the OCR text
    messages = [
        {
            "role": "system",
            "content": """You are a helpful assistant that extracts questions from OCR text. The text is from a screenshot of a test or exam. A question will be EITHER an MCQ OR a long-answer question, never both.

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
        },
        {
            "role": "user",
            "content": f"Extract and format the COMPLETE question from the following OCR text, preserving ALL options if it's an MCQ:\n\n{ocr_text}"
        }
    ]

    try:
        response = await llm_router.generate(
            model="gemini-2.0-flash-exp",
            max_tokens=500,
            messages=messages,
            temperature=0.2,  # Further reduced for more consistent formatting
            top_p=0.9,
            stop_sequences=["User:", "Human:", "Assistant:"],
        )

        extracted_question = response.strip()
        
        # Log both preview and full question
        logger.info(f"Extracted question preview: {extracted_question[:200]}...")
        logger.info("Full extracted question:")
        logger.info("------------------------")
        logger.info(extracted_question)
        logger.info("------------------------")
        
        return extracted_question
    except Exception as e:
        logger.error(f"Error extracting question from OCR text: {e}", exc_info=True)
        raise

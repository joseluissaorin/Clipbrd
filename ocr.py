import base64
import requests
import io
import uuid
import os
from PIL import Image

def split_image_into_chunks(image_data, chunk_size=1024*1024):
    """Split image data into chunks of specified size.
    
    Args:
        image_data (bytes): The image data to split
        chunk_size (int): Maximum size of each chunk in bytes
        
    Yields:
        str: Base64 encoded chunk data
    """
    total_size = len(image_data)
    for i in range(0, total_size, chunk_size):
        chunk = image_data[i:i + chunk_size]
        yield base64.b64encode(chunk).decode('utf-8')

def upload_image_chunks(image_data, lang='spa+eng'):
    """Upload large image in chunks to the OCR API.
    
    Args:
        image_data (bytes): The image data to upload
        lang (str): Language code for OCR
        
    Returns:
        str: The OCRed text from the image
        
    Raises:
        Exception: If upload fails or API returns an error
    """
    # Generate unique file ID
    file_id = str(uuid.uuid4())
    
    # Get chunks
    chunks = list(split_image_into_chunks(image_data))
    total_chunks = len(chunks)
    
    # API endpoint
    api_url = 'https://tess.joseluissaorin.com'
    
    # Upload each chunk
    for i, chunk_data in enumerate(chunks):
        payload = {
            'file_id': file_id,
            'chunk_index': i,
            'total_chunks': total_chunks,
            'chunk_data': chunk_data,
            'lang': lang
        }
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(
                f"{api_url}/ocr/upload-chunk", 
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            response_data = response.json()
            
            if response_data.get('error'):
                raise Exception(f"API Error: {response_data['error']}")
                
            if response_data.get('status') == 'complete':
                return response_data.get('text')
                
            print(f"Upload progress: {response_data.get('chunks_received')}/{total_chunks} chunks")
            
        except requests.exceptions.RequestException as e:
            print(f"Chunk upload failed: {str(e)}")
            raise
            
    raise Exception("Upload completed but no OCR result received")

def ocr_image(base64_image, lang='spa+eng', mime_type='image/png'):
    """
    Perform OCR on an image using the API at https://tess.joseluissaorin.com/ocr
    
    Args:
        base64_image (str): Base64-encoded image data or data URL
        lang (str): Language code for OCR
        mime_type (str): MIME type of the image
        
    Returns:
        str: The OCRed text from the image
        
    Raises:
        Exception: If OCR fails or API returns an error
    """
    # Remove data URL header if present
    if base64_image.startswith('data:'):
        base64_image = base64_image.split(',', 1)[1]
    
    # Decode base64 to get raw image data
    try:
        image_data = base64.b64decode(base64_image)
    except Exception as e:
        raise Exception(f"Invalid base64 data: {str(e)}")
    
    # Check file size
    file_size = len(image_data)
    if file_size > 5 * 1024 * 1024:  # 5MB
        print(f"Image size ({file_size/1024/1024:.2f}MB) exceeds 5MB, using chunked upload")
        return upload_image_chunks(image_data, lang)
    
    # For smaller files, use regular upload
    url = 'https://tess.joseluissaorin.com/ocr'
    
    # Prepare the payload
    data = {
        'image': f'data:{mime_type};base64,{base64_image}',
        'lang': lang
    }
    
    # Set headers
    headers = {
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        result = response.json()
        
        if 'error' in result:
            error_message = result['error']
            details = result.get('details', '')
            if details:
                raise Exception(f"API Error: {error_message}. Details: {details}")
            else:
                raise Exception(f"API Error: {error_message}")
                
        if 'text' in result:
            print(f"OCRed text: {result['text']}")
            return result['text']
            
        raise Exception('Unexpected response format: ' + str(result))
        
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {str(e)}")
        if hasattr(e, 'response'):
            print(f"Response content: {e.response.content}")
        raise

def is_question_with_image(image_url, llm_router):
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

    response = llm_router.generate(
        model="gemini-1.5-flash",
        max_tokens=3,
        messages=messages,
        temperature=0.7,
        top_p=0.9,
        stop_sequences=["User:", "Human:", "Assistant:"],
    )

    generated_text = response
    print(f"Question with image detected: {generated_text}")
    return generated_text.strip().lower() == "yes"

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
        model="gemini-1.5-flash",
        max_tokens=300,
        messages=messages,
        temperature=0.7,
        top_p=0.9,
        stop_sequences=["User:", "Human:", "Assistant:"],
    )

    generated_text = response
    return generated_text

def extract_question_from_ocr(image_url, llm_router):
    # First, perform OCR on the image
    ocr_text = ocr_image(base64_image=image_url)

    # Now, use llama3 to extract the main question from the OCR text
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant that extracts the main question from OCR text. The text is from a screenshot of a test or exam. Determine the most probable question that the user is trying to answer and format it in markdown. You must not only include the question but also the options, it is most probably a multiple choice question and the content of the options, you must not add anything else or try to answer it"
        },
        {
            "role": "user",
            "content": f"Extract the main question and options from the following OCR text and format it in markdown:\n\n{ocr_text}"
        }
    ]

    response = llm_router.generate(
        model="gemini-1.5-flash",
        max_tokens=300,
        messages=messages,
        temperature=0.7,
        top_p=0.9,
        stop_sequences=["User:", "Human:", "Assistant:"],
    )

    print(f"Extracted question: {response.strip()[:200]}")
    return response.strip()

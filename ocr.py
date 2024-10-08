import base64
import requests
import io
from PIL import Image

def compress_image_to_size(input_data, target_size_kb, max_size_kb=None):
    """
    Compress an image to a desired size by resizing and converting to a lossy format (JPEG).
    
    Parameters:
    - input_data (str or bytes or io.BytesIO): Path to the input image or an in-memory bytes buffer.
    - target_size_kb (int): Desired file size in kilobytes.
    - max_size_kb (int, optional): Maximum size in kilobytes before compression is applied.
    
    Returns:
    - bytes: The compressed image as bytes or the original image data if below max_size.
    """
    target_size = target_size_kb * 1024  # Convert KB to Bytes
    max_size = max_size_kb * 1024 if max_size_kb else None  # Convert KB to Bytes if provided

    # Open the original image
    try:
        if isinstance(input_data, str):
            # input_data is a file path
            original_image = Image.open(input_data)
            with open(input_data, 'rb') as f:
                original_data = f.read()
        elif isinstance(input_data, bytes):
            # input_data is bytes
            original_data = input_data
            original_image = Image.open(io.BytesIO(input_data))
        elif isinstance(input_data, io.BytesIO):
            input_data.seek(0)  # Ensure we're at the start of the buffer
            original_data = input_data.getvalue()
            original_image = Image.open(input_data)
            input_data.seek(0)  # Reset the buffer position for potential reuse
        else:
            raise ValueError("input_data must be a file path, bytes, or BytesIO object.")
        
        # Check if the image was successfully opened
        if not original_image:
            raise IOError("Failed to open the image.")
        
    except (IOError, ValueError) as e:
        print(f"Error processing the image: {str(e)}")
        return None

    # Check if compression is needed
    if max_size and len(original_data) <= max_size:
        print(f"Image size ({len(original_data) / 1024:.2f} KB) is below or equal to max_size ({max_size_kb} KB). No compression needed.")
        return original_data

    # Step 1: Resize the image if height > 2160 pixels
    width, height = original_image.size
    if height > 2160:
        new_height = 2160
        new_width = int((new_height / height) * width)
        original_image = original_image.resize((new_width, new_height), Image.NEAREST)
        print(f"Image resized to {new_width}x{new_height} pixels.")

    # Step 2: Convert to RGB mode if necessary (JPEG requires 'RGB')
    if original_image.mode not in ('RGB', 'L'):
        original_image = original_image.convert('RGB')

    # Step 3: Adjust JPEG quality to meet target size
    # Initialize binary search parameters
    min_quality = 92
    max_quality = 95  # Pillow recommends not using quality > 95
    best_image_data = None
    best_size = None

    while min_quality <= max_quality:
        mid_quality = (min_quality + max_quality) // 2

        # Save the image to an in-memory bytes buffer with the current quality
        buffer = io.BytesIO()
        original_image.save(buffer, format='JPEG', quality=mid_quality, optimize=False)
        size = len(buffer.getvalue())

        # Debug statement (can be commented out in production)
        # print(f"Trying quality {mid_quality}: {size / 1024:.2f} KB")

        if size <= target_size:
            # Found a valid compression, try to decrease quality further for smaller size
            best_image_data = buffer.getvalue()
            best_size = size
            max_quality = mid_quality - 1
        else:
            # Size too large, increase quality to reduce file size
            min_quality = mid_quality + 1

    if best_image_data:
        print(f"Compression successful. Final size: {best_size / 1024:.2f} KB at quality {mid_quality}")
        return best_image_data
    else:
        # If no compression could meet the target size, return the image at minimum quality
        buffer = io.BytesIO()
        original_image.save(buffer, format='JPEG', quality=1, optimize=True)
        final_size = len(buffer.getvalue())
        print(f"Could not reach target size. Compressed to minimum quality. Final size: {final_size / 1024:.2f} KB")
        return buffer.getvalue()
    


def ocr_image(base64_image, lang='spa+eng', mime_type='image/png'):
    """
    Perform OCR on a base64-encoded image using the API at https://tess.joseluissaorin.com/ocr

    Parameters:
    - base64_image: str, base64-encoded image data. Can include the data URL header (e.g., 'data:image/png;base64,...').
                    If the header is missing, it will be added using the specified mime_type.
    - lang: str, optional, the language code for OCR (default is 'spa' for Spanish).
    - mime_type: str, optional, the MIME type of the image (default is 'image/png'). Only used if base64_image does not include the data URL header.

    Returns:
    - str, the OCRed text from the image.

    Raises:
    - Exception, if an error occurs.
    """
    url = 'https://tess.joseluissaorin.com/ocr'

    # Ensure the base64_image includes the data URL header
    if not base64_image.startswith('data:'):
        # Add the data URL header
        base64_image = f'data:{mime_type};base64,{base64_image}'

    # Prepare the payload
    data = {
        'image': base64_image,
        'lang': lang
    }

    # Set the headers to specify that we're sending JSON
    headers = {
        'Content-Type': 'application/json'
    }

    # Save the request to a .txt file
    with open('ocr_request.txt', 'a') as request_file:
        request_file.write(f"Request Data: {data}\n")

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()  # Raise an exception for HTTP errors

        # Parse the JSON response
        result = response.json()

        if 'error' in result:
            # The API returned an error
            error_message = result['error']
            # Include details if available
            details = result.get('details', '')
            if details:
                raise Exception(f"API Error: {error_message}. Details: {details}")
            else:
                raise Exception(f"API Error: {error_message}")
        elif 'text' in result:
            # Return the OCRed text
            print(f"OCRed text: {result['text']}")
            return result['text']
        else:
            # Unexpected response format
            raise Exception('Unexpected response format: ' + str(result))

    except requests.exceptions.HTTPError as http_err:
        # Handle HTTP errors
        raise Exception(f'HTTP error occurred: {http_err}')
    except Exception as err:
        print(f"An error occurred: {err}")
        if isinstance(err, requests.exceptions.RequestException):
            print(f"Response content: {err.response.content}")
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
        model="gpt-4o-mini",
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
        model="gpt-4o-mini",
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
        model="meta-llama/Meta-Llama-3.1-8B-Instruct",
        max_tokens=300,
        messages=messages,
        temperature=0.7,
        top_p=0.9,
        stop_sequences=["User:", "Human:", "Assistant:"],
    )

    print(f"Extracted question: {response.strip()[:200]}")
    return response.strip()

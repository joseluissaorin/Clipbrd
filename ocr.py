import base64
import requests

import requests

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
        # Handle other errors
        raise Exception(f'An error occurred: {err}')

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
            "content": "You are a helpful assistant that extracts the main question from OCR text. The text is from a screenshot of a test or exam. Determine the most probable question that the user is trying to answer and format it in markdown."
        },
        {
            "role": "user",
            "content": f"Extract the main question from the following OCR text and format it in markdown:\n\n{ocr_text}"
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

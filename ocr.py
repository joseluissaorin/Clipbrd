import platform
import pytesseract
import base64
from io import BytesIO
from PIL import Image
import requests
from fake_headers import Headers
from pix2text import Pix2Text

if platform.system() == 'Darwin':
    # macOS
    p2t = Pix2Text(languages=("es", "en"))
else:
    # Windows
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    custom_config = r'--oem 3 --psm 6 -l spa+eng'

def ocr_image(image_url=None, image_64=None):
    if image_url != None:
        headers = Headers(headers=False).generate()
        response = requests.get(image_url, headers=headers)
        image = Image.open(BytesIO(response.content))
    elif image_64 != None:
        im_bytes = base64.b64decode(image_64)   # im_bytes is a binary image
        im_file = BytesIO(im_bytes)  # convert image to file-like object
        image = Image.open(im_file)   # img is now PIL Image object

    if platform.system() == 'Darwin':
        ocr_text = p2t.recognize_text(image)
    else:
        ocr_text = pytesseract.image_to_string(image, config=custom_config)
    
    print(f"OCR Text: \n {ocr_text}")
    return ocr_text

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
        model="gpt-4-vision-preview",
        max_tokens=3,
        messages=messages,
        temperature=0.7,
        top_p=0.9,
        stop_sequences=["User:", "Human:", "Assistant:"],
    )

    generated_text = response
    print(f"Question with image detected: {generated_text}")
    return generated_text.strip().lower() == "yes"
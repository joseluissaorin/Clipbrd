# clipboard_processing.py
import base64
import io
import clipman
from ocr import is_question_with_image, ocr_image, extract_question_from_ocr
from question_processing import (get_answer_with_context, get_answer_without_context,
                                 get_number_with_context, get_answer_with_image,
                                 get_number_without_context, is_formatted_question)

def check_clipboard(app):
    current_clipboard = clipman.paste()
    if current_clipboard == app.last_clipboard or current_clipboard == app.question_clipboard:
        return

    app.last_clipboard = current_clipboard
    app.debug_info.append(f"Clipboard content: {current_clipboard}")

    if len(current_clipboard.split()) == 1:
        app.update_icon("Clipbrd")
        return

    is_mcq, clipboard = is_formatted_question(current_clipboard, app.llm_router)
    app.debug_info.append(f"MCQ detected: {is_mcq}")

    app.update_icon("Clipbrd: Working.")
    if is_mcq:
        process_mcq(app, clipboard)
    else:
        process_non_mcq(app, current_clipboard)

def check_screenshot(app):
    if app.screenshot is None:
        return

    print("Checking screenshot")
    base64_image = app.screenshot

    process_text_from_image(app, base64_image)

    app.screenshot = None

def process_image_question(app, base64_image):
    app.debug_info.append("Processing question with image")
    image_data = {
        "url": f"data:image/png;base64,{base64_image}",
        "detail": "high"
    }
    answer_number = get_answer_with_image("Answer the following question", app.llm_router, image_data=image_data)
    app.update_icon(f"Clipbrd: {answer_number}")
    app.debug_info.append(f"MCQ answer with image: {answer_number}")

def process_text_from_image(app, base64_image):
    base64_image_url = f"data:image/png;base64,{base64_image}"
    extracted_text = extract_question_from_ocr(base64_image, app.llm_router)
    
    if not extracted_text:
        extracted_text = ocr_image(image_64=base64_image)
    
    app.debug_info.append(f"Extracted Text: {extracted_text}")
    is_mcq, clipboard = is_formatted_question(extracted_text, app.llm_router)
    app.debug_info.append(f"MCQ detected: {is_mcq}")
    if is_mcq:
        process_mcq(app, clipboard)
    else:
        process_non_mcq(app, clipboard)

def process_mcq(app, text):
    answer_number = get_number_with_context(text, app.llm_router, app.search, app.inverted_index, app.documents)
    if answer_number is None:
        answer_number = get_number_without_context(text, app.llm_router)
    app.update_icon(f"Clipbrd: {answer_number}")
    app.debug_info.append(f"MCQ answer: {answer_number}")
    app.last_clipboard = text

def process_non_mcq(app, text):
    app.debug_info.append("Processing non-MCQ question")
    answer = get_answer_with_context(text, app.llm_router, app.search, app.inverted_index, app.documents)
    if answer is None:
        answer = get_answer_without_context(text, app.llm_router)
    app.question_clipboard = answer
    clipman.copy(answer)
    app.update_icon("Clipbrd: Done.")
    app.debug_info.append(f"Answer: {answer}")
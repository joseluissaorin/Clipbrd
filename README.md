# Clipbrd

Clipbrd is a powerful, AI-driven clipboard assistant designed to enhance your productivity by providing instant answers to questions directly from your clipboard. This cross-platform application offers a range of features to streamline your workflow and make information retrieval effortless.

## Key Features

### 1. AI-Powered Clipboard Assistance
- Automatically detects and processes questions from your clipboard.
- Provides quick answers using advanced AI models.
- Supports both multiple-choice questions (MCQs) and open-ended questions.

### 2. Local RAG (Retrieval-Augmented Generation) Processing
- Process and index your local documents for context-aware answers.
- Supports various file formats including .docx, .pptx, .pdf, .txt, and .md.
- Simple drag-and-drop functionality for adding documents to the Clipbrd folder.

### 3. OCR and Screenshot Processing
- Capture full-screen screenshots with customizable keyboard shortcuts.
- Extract text from images using OCR technology.
- Analyze and understand the content of screenshots to formulate questions.

### 4. Minimalist GUI
- Runs quietly in the system tray/menu bar.
- Displays concise answer indicators (e.g., MCQ option numbers) in the icon.

### 5. Multi-Model AI Integration
- Utilizes different AI models optimized for various tasks:
  - Question detection and formatting
  - Context retrieval
  - Answer generation
- Incorporates multimodal AI for image understanding and question extraction.

### 6. Cross-Platform Compatibility
- Works on both Windows and macOS.
- Shared codebase with platform-specific GUI implementations.

### 7. Lightweight and Self-Contained
- Minimal external dependencies for easy installation and execution.
- Includes necessary components like Pandoc for document processing.

### 8. Debug Information
- Built-in debug mode for troubleshooting and performance monitoring.

## Installation

[Provide installation instructions here]

## Usage

1. Launch the Clipbrd application.
2. Copy a question to your clipboard or take a screenshot containing a question.
3. Clipbrd will automatically process the input and provide an answer.
4. For MCQs, the answer will be displayed in the system tray/menu bar icon.
5. For open-ended questions, the answer will be copied to your clipboard.

## Configuration

- Access settings through the system tray/menu bar icon.
- Customize keyboard shortcuts for screenshot capture.
- Configure the Clipbrd folder location for document processing.

## Notes

- The current implementation is primarily in Python, which may present challenges for compilation on macOS. Future versions may consider using a different language for improved cross-platform compilation.
- The subscription-based service with Stripe integration and piracy prevention is not yet implemented in the provided code.
- LaTeX understanding, code generation, and execution for math questions are not currently implemented.

## Contributing

[Right now there is no contribution policy]

## License
Copyright (c) 2024 José Luis Saorín

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

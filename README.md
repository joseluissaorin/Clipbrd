# Clipbrd

Clipbrd is an advanced AI-powered clipboard manager that seamlessly integrates with your workflow to provide instant, context-aware answers using local documents and multiple AI models. The application is designed to be lightweight, efficient, and cross-platform compatible.

> **Note**: This is the open repository for the [Clipbrd subscription service](https://clipbrdapp.com). While the code includes subscription and licensing features, intermediate programmers can easily patch these components and build a version using their own API keys. The core functionality requires:
> - A Google Gemini API key 
> - An Anthropic API key for Claude (optional)
> - An OpenAI API key for GPT-4 (optional)
> - A DeepInfra API key (optional)

## Core Features

### Intelligent Clipboard Processing
- Real-time monitoring of clipboard changes
- Automatic question detection and classification (MCQ vs. open-ended)
- Support for both text and image-based inputs
- Asynchronous processing with rate limiting and caching
- Batch processing capabilities for improved performance

### Document Processing & RAG
- Local document indexing using AsyncBM25Index
- Support for multiple document formats (.txt, .md, .docx, .doc, .pptx, .ppt, .pdf)
- Efficient chunking and tokenization
- N-gram based search functionality
- Memory-efficient document processing with streaming capabilities

### AI Integration
- Multiple AI model support (Gemini, Claude, GPT-4, DeepInfra)
- Context-aware answer generation
- Image understanding and OCR processing
- Flexible prompt engineering for different question types
- Automatic model selection based on task requirements

### Screenshot & OCR Capabilities
- Global keyboard shortcuts for screenshot capture
- Image compression and optimization
- OCR text extraction with error handling
- Question detection from image content
- Support for copy-protected text through screenshots

### Platform Integration
- Cross-platform system tray/menu bar implementation
- Native notifications
- Custom keyboard shortcuts
- Automatic startup configuration
- Minimize to tray functionality

### Security & Licensing
- Secure license key storage using system keyring
- Encrypted local data storage
- License validation and verification
- Automatic updates and dependency management
- Offline operation support

## Technical Architecture

### Core Components
1. **Main Application (`clipbrd.py`)**
   - Application initialization and lifecycle management
   - Component coordination
   - Event handling

2. **Document Processing (`document_processing.py`)**
   - AsyncBM25Index implementation
   - Document chunking and indexing
   - Search functionality

3. **Clipboard Processing (`clipboard_processing.py`)**
   - Clipboard monitoring and content extraction
   - Question detection and routing
   - Rate limiting and caching

4. **Platform Interface (`platform_interface.py`)**
   - Cross-platform GUI abstraction
   - System tray/menu bar integration
   - Native notifications

### Supporting Modules
5. **Settings Manager (`settings_manager.py`)**
   - Configuration persistence
   - Settings UI
   - Debug logging

6. **License Manager (`license_manager.py`)**
   - License validation
   - Secure storage
   - Update checking

7. **Question Processing (`question_processing.py`)**
   - Question classification
   - Answer generation
   - Context retrieval

8. **Screenshot Management (`screenshot.py`)**
   - Screen capture
   - Image optimization
   - Shortcut handling

## Requirements

### System Requirements
- Windows 10+ or macOS 10.15+
- Python 3.10
- 4GB RAM minimum (8GB recommended)
- LibreOffice (for document processing)

### Dependencies
- Required Python packages are managed through `dependency_manager.py`
- External dependencies:
  - LibreOffice (document conversion)

## Installation

1. Clone the repository
2. Install LibreOffice
3. Run the dependency manager:
```python
python -m dependency_manager install
```
4. Launch the application:
```python
python clipbrd.py
```

## Configuration

### Environment Variables
```
ANTHROPIC_API_KEY=your_claude_api_key
OPENAI_API_KEY=your_gpt4_api_key
DEEPINFRA_API_KEY=your_deepinfra_key
GEMINI_API_KEY=your_gemini_api_key
```

### Settings
Access settings through the system tray/menu bar icon:
- Theme customization
- Keyboard shortcuts
- Debug mode
- Language selection
- Notification preferences

## Development

### Debug Mode
Enable debug mode through settings to access:
- Real-time log viewing
- Performance metrics
- Memory usage statistics
- Processing statistics

### Contributing
Currently, you may only fork this repository and use it as a base for your own projects, I am not accepting pull requests at this time. Maybe, in the future, I will change this.

## License
Copyright (c) 2024 José Luis Saorín
Licensed under MIT License. See LICENSE file for details.

## Known Limitations
- Python-based implementation may affect compilation on macOS
- LaTeX and code execution features planned for future releases

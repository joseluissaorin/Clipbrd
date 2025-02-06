#!/usr/bin/env python3
import os
import sys
import json
import shutil
import argparse
import subprocess
import re
import importlib
from importlib.metadata import version
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from dotenv import load_dotenv

class BuildConfig:
    def __init__(self):
        self.platform = sys.platform
        self.is_macos = self.platform == 'darwin'
        self.is_windows = self.platform == 'win32'
        self.root_dir = Path(__file__).parent
        self.builds_dir = self.root_dir / 'builds'
        self.version_file = self.root_dir / 'version.json'
        self.clipbrd_backup = self.root_dir / 'clipbrd.py.bak'
        self.env_file = self.root_dir / '.env'
        # Add build-specific paths
        self.build_dir = self.builds_dir / ('macos' if self.is_macos else 'windows')
        self.icons_dir = self.root_dir / 'assets' / 'icons'
        self.macos_icon = self.icons_dir / 'clipbrd_macos.icns'
        self.windows_icon = self.icons_dir / 'clipbrd_windows.ico'
        self.entitlements = self.root_dir / 'assets' / 'macos' / 'clipbrd.entitlements'
        self.env_vars = [
            'ANTHROPIC_API_KEY',
            'OPENAI_API_KEY',
            'DEEPINFRA_API_KEY',
            'GOOGLEAI_API_KEY'
        ]
        # Add validation-specific paths and requirements
        self.min_python_version = (3, 8)
        self.required_tools = {
            'all': ['python', 'pip', 'git'],
            'darwin': ['xcode-select', 'xcrun'],
            'win32': ['cl.exe']  # Visual C++ compiler
        }
        self.required_files = [
            'clipbrd.py',
            'requirements.txt',
            '.env',
            'assets/icons/clipbrd_macos.icns',
            'assets/icons/clipbrd_windows.ico'
        ]

class BuildSystem:
    def __init__(self, platform: Optional[str] = None, version: Optional[str] = None):
        self.config = BuildConfig()
        if platform:
            self.config.platform = platform
            self.config.is_macos = platform == 'darwin'
            self.config.is_windows = platform == 'win32'
        self.version = version
        self.current_version = self._load_version()
        # Packages that should bypass import check
        self.bypass_import_packages = {
            'annotated-types',  # Type annotation utilities
            'async-timeout',    # Async utilities
            'attrdict',        # Dictionary utilities
            'attrs',           # Class building utilities
            'typing-extensions', # Typing utilities
            'dataclasses',     # Dataclass utilities
            'idna',            # Internationalized domain names
            'multidict',       # Dictionary utilities
            'yarl',            # URL parsing utilities
            'frozenlist',      # Immutable list utilities
            'aiosignal',
            'bce-python-sdk',
            'boto3',
            'botocore',
            'requests',
            'urllib3',
            'pydantic',
            'pydantic-core',
            'pydantic-settings',
            'pydantic-extra-types',
            'pydantic-core',
            'pydantic-settings',
            'pydantic-extra-types',
            'beautifulsoup4',
            'bs4',
            'lxml',
            'lxml-stubs',
            'lxml-stubs-ext',
            'lxml-stubs-ext-py311',
            'lxml-stubs-ext-py312',
            'boto-session-manager',
            'boto3-session-manager',
            'boto3-session-manager-plugin',
            'boto3-session-manager-plugin-py311',
            'boto3-session-manager-plugin-py312',
            'charset-normalizer',
            'dbus-next',
            'deepsearch-glm',
            'deepsearch-llm',
            'deepsearch-llm-sdk',
            'deepsearch-llm-sdk-py311',
            'deepsearch-llm-sdk-py312',
            'deepsearch-llm-sdk-py313',
            'deepsearch-llm-sdk-py314',
            'docling-core',
            'docling-ibm-models',
            'docling-parse',
            'fairy-doc',
            'fast-langdetect',
            'fasttext-wheel',
            'flask-babel',
            'Flask-Cors',
            'Flask-JWT-Extended',
            'Flask-SQLAlchemy',
            'Flask-WTF',
            'flask-marshmallow',
            'Flask-Migrate',
            'Flask-Script',
            'Flask-RESTful',
            'fonttools',
            'func-args',
            'func-timeout',
            'google-ai-generativelanguage',
            'google-api-core',
            'google-api-python-client',
            'google-auth',
            'google-auth-oauthlib',
            'google-auth-httplib2',
            'google-auth-oauthlib-oauth2client',
            'google-auth-oauthlib-oauth2client-django',
            'google-auth-oauthlib-oauth2client-requests',
            'google-auth-oauthlib-oauth2client-requests-oauth2client',
            'google-auth-oauthlib-oauth2client-requests-oauth2client-django',
            'google-auth-oauthlib-oauth2client-requests-oauth2client-django-oauth2client',
            'googleapis-common-protos',
            'grpcio',
            'grpcio-status',
            'grpcio-tools',
            'huggingface-hub',
            'jsonschema-specifications',
            'lark-parser',
            'Levenshtein',
            'magic-pdf',
            'markdown-it-py',
            'markdown-it-py-plugins',
            'marshmallow-sqlalchemy',
            'mypy-extensions',
            'pypdfium2',
            'pypdfium2-core',
            'more-itertools',
            'opencv-contrib-python',
            'opencv-python',
            'opencv-python-headless',
            'opt-einsum',
            'ordered-set',
            'paddleocr',
            'paddleocr-core',
            'paddlepaddle',
            'pdfminer.six',
            'proto-plus',
            'protobuf',
            'py-asciimath',
            'pycryptodome',
            'pyinstaller',
            'pyinstaller-hooks-contrib',
            'PyJWT',
            'PyMuPDF',
            'PyMuPDFb',
            'pyparsing',
            'python-bidi',
            'python-dateutil',
            'python-docx',
            'python-dotenv',
            'python-pptx',
            'pytz',
            'pywin32',
            'pywin32-ctypes',
            'PyYAML',
            'rapidfuzz',
            'rarfile',
            'realtime',
            'referencing',
            'regex',
            'rich',
            'robust-downloader',
            'rpds-py',
            'scikit-image',
            'scikit-learn',
            'scikit-learn-intelex',
            'win32-setctime',
            'smart-open',
        }

    def _load_version(self) -> Dict:
        """Load version information from version.json"""
        if not self.config.version_file.exists():
            return {
                "version": "1.0.0",
                "last_build_date": datetime.now().strftime("%Y-%m-%d"),
                "build_number": 1
            }
        with open(self.config.version_file) as f:
            return json.load(f)

    def _save_version(self):
        """Save version information to version.json"""
        with open(self.config.version_file, 'w') as f:
            json.dump(self.current_version, f, indent=4)

    def _increment_version(self):
        """Increment the patch version and build number"""
        if not self.version:  # Only increment if version not manually specified
            major, minor, patch = self.current_version["version"].split('.')
            self.current_version["version"] = f"{major}.{minor}.{int(patch) + 1}"
        else:
            self.current_version["version"] = self.version
        self.current_version["build_number"] += 1
        self.current_version["last_build_date"] = datetime.now().strftime("%Y-%m-%d")
        self._save_version()

    def _backup_clipbrd(self):
        """Create a backup of clipbrd.py"""
        shutil.copy2(self.config.root_dir / 'clipbrd.py', self.config.clipbrd_backup)

    def _restore_clipbrd(self):
        """Restore clipbrd.py from backup"""
        if self.config.clipbrd_backup.exists():
            shutil.move(self.config.clipbrd_backup, self.config.root_dir / 'clipbrd.py')

    def _load_env_vars(self) -> Dict[str, str]:
        """Load environment variables from .env file"""
        if not self.config.env_file.exists():
            raise FileNotFoundError(f".env file not found at {self.config.env_file}")
        
        load_dotenv(self.config.env_file)
        env_vars = {}
        for var in self.config.env_vars:
            value = os.getenv(var)
            if value is None:
                raise ValueError(f"Required environment variable {var} not found in .env file")
            env_vars[var] = value
        return env_vars

    def _find_env_var_usage(self, content: str) -> List[str]:
        """Find environment variables used in the code"""
        used_vars = set()
        for var in self.config.env_vars:
            # Look for os.getenv('VAR') or os.environ['VAR'] or os.environ.get('VAR')
            patterns = [
                rf"os\.getenv\(['\"]({var})['\"]",
                rf"os\.environ\[['\"]({var})['\"]",
                rf"os\.environ\.get\(['\"]({var})['\"]"
            ]
            for pattern in patterns:
                if re.search(pattern, content):
                    used_vars.add(var)
        return list(used_vars)

    def _modify_clipbrd_with_env_vars(self):
        """Modify clipbrd.py to include hardcoded environment variables"""
        try:
            # Load environment variables
            env_vars = self._load_env_vars()
            
            # Read clipbrd.py content
            with open(self.config.root_dir / 'clipbrd.py', 'r') as f:
                content = f.read()
            
            # Find which variables are actually used
            used_vars = self._find_env_var_usage(content)
            
            # Prepare the environment variables initialization code
            env_init_code = "\n".join([
                f"    os.environ['{var}'] = '{env_vars[var]}'"
                for var in used_vars
            ])
            
            # Find the appropriate location to insert the initialization code
            # Look for the load_environment_variables function
            load_env_pattern = r"def load_environment_variables\(\):[^\n]*\n\s+\"\"\"[^\"]*\"\"\"\n\s+"
            if re.search(load_env_pattern, content):
                # Replace the function implementation while keeping the docstring
                modified_content = re.sub(
                    load_env_pattern + r"[^\n]+(\n\s+[^\n]+)*",
                    lambda m: m.group(0) + env_init_code + "\n    logging.info('Using hardcoded environment variables')",
                    content
                )
            else:
                # If function not found, add it after the imports
                import_section_end = re.search(r"^import[^\n]*(\n\s*(?:from|import)[^\n]*)*", content, re.MULTILINE)
                if not import_section_end:
                    raise ValueError("Could not find import section in clipbrd.py")
                
                env_function = f"\n\ndef load_environment_variables():\n    \"\"\"\n    Load environment variables.\n    \"\"\"\n{env_init_code}\n    logging.info('Using hardcoded environment variables')\n"
                pos = import_section_end.end()
                modified_content = content[:pos] + env_function + content[pos:]
            
            # Write the modified content back to clipbrd.py
            with open(self.config.root_dir / 'clipbrd.py', 'w') as f:
                f.write(modified_content)
            
            print(f"Successfully hardcoded {len(used_vars)} environment variables")
            
        except Exception as e:
            print(f"Error modifying clipbrd.py: {e}")
            self._restore_clipbrd()
            raise

    def _prepare_build_directory(self):
        """Prepare the build directory for the current version"""
        version_dir = self.config.build_dir / self.current_version["version"]
        version_dir.mkdir(parents=True, exist_ok=True)
        return version_dir

    def _get_nuitka_base_command(self) -> List[str]:
        """Get the base Nuitka command with common options"""
        return [
            sys.executable,
            "-m",
            "nuitka",
            "--standalone",
            "--assume-yes-for-downloads",
            "--disable-console",
            "--include-package=PIL",
            "--include-package=openai",
            "--include-package=anthropic",
            "--include-package=google.generativeai",
            "--include-package=pilmoji",
            "--include-package=pystray",
            "--include-package=numpy",
            "--include-package=keyring",
            "--include-package=clipman",
            "--include-package=docling",
            "--include-package=simplemma",
            "--include-package=aiofiles",
            "--include-package=markdown",
            "--include-package=pynput",
            "--include-package=pypdfium2",
        ]

    def _build_macos(self):
        """Build for macOS"""
        try:
            version_dir = self._prepare_build_directory()
            
            # Basic command with macOS specific options
            cmd = self._get_nuitka_base_command()
            cmd.extend([
                "--macos-create-app-bundle",
                f"--macos-app-icon={self.config.macos_icon}",
                f"--output-dir={version_dir}",
                "--macos-app-name=Clipbrd",
                f"--macos-app-version={self.current_version['version']}",
                "--macos-signed-app",  # Enable signing
                "--macos-disable-console"
            ])

            # Add version info
            cmd.extend([
                "--company-name=Saorin",
                f"--product-version={self.current_version['version']}",
                "--product-name=Clipbrd",
                "--file-description=AI-powered clipboard assistant",
                "--copyright=© 2024 Saorin",
            ])

            # Add entitlements if they exist
            if self.config.entitlements.exists():
                cmd.append(f"--macos-app-entitlements={self.config.entitlements}")

            # Add the main script
            cmd.append("clipbrd.py")

            print("Starting macOS build...")
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"Build successful! App bundle created at {version_dir}/Clipbrd.app")
                
                # Notarize the app if we're on macOS
                if sys.platform == 'darwin':
                    self._notarize_macos_app(f"{version_dir}/Clipbrd.app")
            else:
                print("Build failed!")
                print(result.stderr)
                raise Exception("Build failed")

        except subprocess.CalledProcessError as e:
            print(f"Build failed with error: {e.stderr}")
            raise
        except Exception as e:
            print(f"Build failed: {e}")
            raise

    def _notarize_macos_app(self, app_path: str):
        """Notarize the macOS app bundle"""
        try:
            # First, create a ZIP archive of the app
            zip_path = f"{app_path}.zip"
            subprocess.run(["ditto", "-c", "-k", "--keepParent", app_path, zip_path], check=True)

            # Submit for notarization
            print("Submitting app for notarization...")
            subprocess.run([
                "xcrun",
                "notarytool",
                "submit",
                zip_path,
                "--wait",
                "--keychain-profile",
                "AC_PASSWORD"  # Assumes you've set up notarytool with keychain profile
            ], check=True)

            # Staple the notarization ticket
            print("Stapling notarization ticket...")
            subprocess.run(["xcrun", "stapler", "staple", app_path], check=True)
            
            print("Notarization complete!")
            
            # Clean up
            os.remove(zip_path)
            
        except subprocess.CalledProcessError as e:
            print(f"Notarization failed: {e}")
            raise

    def _build_windows(self):
        """Build for Windows"""
        try:
            version_dir = self._prepare_build_directory()
            
            # Basic command with Windows specific options
            cmd = self._get_nuitka_base_command()
            cmd.extend([
                "--onefile",  # Windows uses onefile mode
                f"--windows-icon-from-ico={self.config.windows_icon}",
                f"--output-dir={version_dir}",
                "--windows-company-name=Saorin",
                f"--windows-product-version={self.current_version['version']}",
                "--windows-product-name=Clipbrd",
                "--windows-file-description=AI-powered clipboard assistant",
                "--windows-file-version=1.0.0.0",
                "--windows-disable-console",
                "--windows-uac-admin"  # Don't require admin privileges
            ])

            # Add Windows-specific dependencies
            if self.config.is_windows:
                cmd.extend([
                    "--include-package=win32api",
                    "--include-package=win32con",
                    "--include-package=win32gui"
                ])

            # Add the main script
            cmd.append("clipbrd.py")

            print("Starting Windows build...")
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"Build successful! Executable created at {version_dir}/clipbrd.exe")
            else:
                print("Build failed!")
                print(result.stderr)
                raise Exception("Build failed")

        except subprocess.CalledProcessError as e:
            print(f"Build failed with error: {e.stderr}")
            raise
        except Exception as e:
            print(f"Build failed: {e}")
            raise

    def _check_python_version(self) -> bool:
        """Check if Python version meets minimum requirements"""
        current_version = sys.version_info[:2]
        if current_version < self.config.min_python_version:
            print(f"Error: Python {'.'.join(map(str, self.config.min_python_version))} or higher is required")
            return False
        return True

    def _check_tool_availability(self, tool: str) -> bool:
        """Check if a specific tool is available in the system"""
        try:
            if tool == 'cl.exe' and self.config.is_windows:
                # Special check for Visual C++ compiler on Windows
                result = subprocess.run(['cl.exe'], capture_output=True, text=True)
                return 'Microsoft (R) C/C++ Optimizing Compiler' in result.stderr
            else:
                subprocess.run([tool, '--version'], capture_output=True, check=True)
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _check_nuitka_installation(self) -> bool:
        """Check if Nuitka is properly installed"""
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'nuitka', '--version', '--msvc=14.3'],
                capture_output=True,
                text=True,
                check=True
            )
            print(f"Found Nuitka version: {result.stdout.strip()}")
            return True
        except subprocess.SubprocessError:
            print("Error: Nuitka is not installed or not working properly")
            return False

    def _parse_package_requirement(self, req: str) -> Tuple[str, Optional[str]]:
        """Parse package requirement into name and version"""
        try:
            # Skip empty lines
            if not req or req.isspace():
                return "", None

            # Handle git repository URLs
            if req.startswith(('git+', 'git://', 'http://', 'https://')):
                # Extract package name from git URL
                if '@' in req:
                    # If there's a specific version/branch specified
                    url_part = req.split('@')[0]
                else:
                    url_part = req
                
                # Get the last part of the URL and remove .git if present
                pkg_name = url_part.split('/')[-1].replace('.git', '')
                return pkg_name, None
            
            # Handle normal package specifications
            if '==' in req:
                name, ver = req.split('==', 1)
                name = name.split(';')[0].strip()  # Remove platform specifiers
                ver = f"=={ver.strip()}"
                return name, ver
            elif '>=' in req:
                name, ver = req.split('>=', 1)
                name = name.split(';')[0].strip()
                ver = f">={ver.strip()}"
                return name, ver
            
            # Handle packages without version specification
            return req.split(';')[0].strip(), None
            
        except Exception as e:
            print(f"Warning: Error parsing requirement '{req}': {e}")
            return "", None

    def _check_package_installed(self, pkg_name: str, required_version: Optional[str] = None) -> bool:
        """Check if a package is installed and meets version requirements"""
        try:
            # Check if it's a GitHub package
            if '@' in pkg_name and any(prefix in pkg_name for prefix in ['git+', 'git://', 'http://', 'https://']):
                # For GitHub packages, extract the base package name
                # Handle cases like 'package @ git+https://...' and 'git+https://...@version'
                if ' @ ' in pkg_name:
                    base_pkg_name = pkg_name.split(' @ ')[0].strip()
                else:
                    # Extract from URL
                    url_part = pkg_name.split('@')[0].strip()
                    base_pkg_name = url_part.split('/')[-1].replace('.git', '')
                
                try:
                    importlib.import_module(base_pkg_name)
                    print(f"Successfully imported GitHub package '{base_pkg_name}'")
                    return True
                except ImportError:
                    print(f"GitHub package '{base_pkg_name}' cannot be imported")
                    return False
                except Exception as e:
                    print(f"Error checking GitHub package '{base_pkg_name}': {e}")
                    return False

            # Clean up package name (remove version if present)
            pkg_name = pkg_name.split("==")[0].split(">=")[0].strip()
            

            # Check if package should bypass import check
            if pkg_name in self.bypass_import_packages:
                # print(f"Bypassing import check for utility package '{pkg_name}'")
                return True
            
            # Handle special cases where import name differs from package name
            import_name = pkg_name.lower()
            pkg_name_for_version = pkg_name
            
            if import_name == 'pillow':
                import_name = 'PIL'
                pkg_name_for_version = 'Pillow'
            elif import_name == 'python-dotenv':
                import_name = 'dotenv'
                pkg_name_for_version = 'python-dotenv'
            elif import_name == 'google-generativeai':
                import_name = 'google.generativeai'
                pkg_name_for_version = 'google-generativeai'
            
            # First check if we can import the module
            importlib.import_module(import_name)
            
            # If version is specified, check it
            if required_version:
                try:
                    installed_version = version(pkg_name_for_version)
                    if required_version.startswith('>='):
                        req_version = required_version[2:]
                        if installed_version < req_version:
                            print(f"Package '{pkg_name}' version {installed_version} is less than required {required_version}")
                            return False
                    elif required_version.startswith('=='):
                        req_version = required_version[2:]
                        if installed_version != req_version:
                            print(f"Package '{pkg_name}' version {installed_version} does not match required {required_version}")
                            return False
                except Exception as e:
                    print(f"Error checking version for package '{pkg_name}': {e}")
                    return False
            
            return True
        except ImportError:
            print(f"Package '{pkg_name}' cannot be imported")
            return False
        except Exception as e:
            print(f"Error checking package '{pkg_name}': {e}")
            return False

    def _check_dependencies(self) -> bool:
        """Check if all required Python dependencies are installed"""
        try:
            # Core dependencies from requirements.txt
            raw_requirements = []
            encodings = ['utf-16']  # Try different encodings
            
            for encoding in encodings:
                try:
                    with open('requirements.txt', 'r', encoding=encoding) as f:
                        raw_requirements = f.read().splitlines()
                    print(f"Read requirements.txt with {encoding} encoding")
                    break  # If successful, break the loop
                except UnicodeDecodeError:
                    continue  # Try next encoding
                except Exception as e:
                    print(f"Error reading requirements.txt with {encoding} encoding: {e}")
                    continue
            
            if not raw_requirements:
                print("Error: Could not read requirements.txt with any encoding")
                return False
            
            # Filter out comments, empty lines, BOM symbols, and clean up package names
            requirements = []
            for r in raw_requirements:
                line = r.strip()
                # Skip empty lines, comments, and standalone BOM symbols
                if not line or line.startswith('#') or line in ['ÿþ', 'þ', 'ÿ']:
                    continue
                # Remove BOM symbols from anywhere in the line
                line = line.replace('ÿþ', '').replace('ÿ', '').replace('þ', '')
                # Remove any other invalid characters from the start
                cleaned = re.sub(r'^[^\w@.-]+', '', line)
                if cleaned:
                    requirements.append(cleaned)
            
            # Filter out platform-specific requirements that don't apply
            requirements = [
                req for req in requirements 
                if not (
                    (self.config.is_windows and '; sys_platform == "darwin"' in req) or
                    (self.config.is_macos and '; sys_platform == "win32"' in req)
                )
            ]
            
            # Check each requirement
            for req in requirements:
                try:
                    pkg_name, required_version = self._parse_package_requirement(req)
                    if not self._check_package_installed(pkg_name, required_version):
                        print(f"Error: Package '{pkg_name}' version requirement '{required_version}' not satisfied")
                        return False
                        
                except Exception as e:
                    print(f"Error checking package '{req}': {e}")
                    return False
            
            return True
            
        except Exception as e:
            print(f"Error checking dependencies: {e}")
            return False

    def _validate_environment(self) -> bool:
        """Validate build environment"""
        print("Validating build environment...")
        
        # Check Python version
        if not self._check_python_version():
            return False
        
        # Check Nuitka installation
        if not self._check_nuitka_installation():
            return False
        
        # Check required tools
        required_tools = self.config.required_tools['all']
        if self.config.is_macos:
            required_tools.extend(self.config.required_tools['darwin'])
        elif self.config.is_windows:
            required_tools.extend(self.config.required_tools['win32'])
        
        for tool in required_tools:
            if not self._check_tool_availability(tool):
                print(f"Error: Required tool '{tool}' is not available")
                return False
        
        # Check dependencies
        if not self._check_dependencies():
            return False
        
        print("Environment validation successful!")
        return True

    def _check_syntax(self, file_path: str) -> bool:
        """Check Python file syntax"""
        # List of encodings to try
        encodings = ['utf-8', 'utf-8-sig', 'utf-16', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                    compile(content, file_path, 'exec')
                    return True
            except UnicodeDecodeError:
                continue  # Try next encoding
            except SyntaxError as e:
                print(f"Syntax error in {file_path}: {e}")
                return False
            except Exception as e:
                if isinstance(e, UnicodeError):
                    continue  # Try next encoding
                print(f"Error checking syntax of {file_path}: {e}")
                return False
        
        print(f"Error: Could not read {file_path} with any supported encoding")
        return False

    def _check_required_files(self) -> bool:
        """Check if all required files exist"""
        for file_path in self.config.required_files:
            full_path = self.config.root_dir / file_path
            if not full_path.exists():
                print(f"Error: Required file '{file_path}' not found")
                return False
        return True

    def _check_icon_files(self) -> bool:
        """Validate icon files"""
        if self.config.is_macos and not self.config.macos_icon.exists():
            print(f"Error: macOS icon file not found at {self.config.macos_icon}")
            return False
        elif self.config.is_windows and not self.config.windows_icon.exists():
            print(f"Error: Windows icon file not found at {self.config.windows_icon}")
            return False
        return True

    def _validate_source(self) -> bool:
        """Validate source code and project structure"""
        print("Validating source code and project structure...")
        
        # Check required files
        if not self._check_required_files():
            return False
        
        # Check icon files
        if not self._check_icon_files():
            return False
        
        # Check Python syntax
        python_files = [
            self.config.root_dir / 'clipbrd.py',
            *self.config.root_dir.glob('**/*.py')
        ]
        
        for py_file in python_files:
            if not self._check_syntax(str(py_file)):
                return False
        
        print("Source code validation successful!")
        return True

    def build(self):
        """Main build process"""
        try:
            # Validation
            if not self._validate_environment():
                raise Exception("Environment validation failed")
            # if not self._validate_source():
            #     raise Exception("Source code validation failed")

            # Version management
            self._increment_version()

            # Environment variables handling
            self._backup_clipbrd()
            self._modify_clipbrd_with_env_vars()

            # Platform-specific build
            if self.config.is_macos:
                self._build_macos()
            elif self.config.is_windows:
                self._build_windows()
            else:
                raise Exception(f"Unsupported platform: {self.config.platform}")

        finally:
            # Cleanup
            self._restore_clipbrd()

def main():
    parser = argparse.ArgumentParser(description='Build Clipbrd application')
    parser.add_argument('--platform', choices=['macos', 'windows'],
                      help='Target platform (default: current platform)')
    parser.add_argument('--version', help='Specify version (default: auto-increment)')
    args = parser.parse_args()

    platform_map = {
        'macos': 'darwin',
        'windows': 'win32'
    }

    platform = platform_map.get(args.platform) if args.platform else None
    builder = BuildSystem(platform=platform, version=args.version)
    builder.build()

if __name__ == '__main__':
    main() 
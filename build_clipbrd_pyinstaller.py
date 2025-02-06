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
        self.spec_file = self.root_dir / 'clipbrd.spec'
        # Add build-specific paths
        self.build_dir = self.builds_dir / ('MacOS' if self.is_macos else 'Windows')
        self.icons_dir = self.root_dir / 'assets' / 'icons'
        self.macos_icon = self.icons_dir / 'clipbrd_macos.icns'
        self.windows_icon = self.icons_dir / 'clipbrd_windows.ico'
        self.entitlements = self.root_dir / 'assets' / 'macos' / 'clipbrd.entitlements'
        self.env_vars = [
            'ANTHROPIC_API_KEY',
            'OPENAI_API_KEY',
            'DEEPINFRA_API_KEY',
            'GOOGLEAI_API_KEY',
            'SUPABASE_URL',
            'SUPABASE_KEY'
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
            'assets/icons/clipbrd_windows.ico',
            'clipbrd.spec'
        ]
        self.python_files = [
            'clipbrd.py',
            'license_manager.py'
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
           'annotated-types', 'async-timeout', 'attrdict', 'attrs', 'typing-extensions', 'dataclasses', 'idna', 'multidict', 'yarl', 'frozenlist', 'aiosignal', 'bce-python-sdk', 'boto3', 'botocore', 'requests', 'urllib3', 
           'pydantic', 'pydantic-core', 'pydantic-settings', 'pydantic-extra-types', 'pydantic-core', 'pydantic-settings', 'pydantic-extra-types', 'beautifulsoup4', 'bs4', 'lxml', 'lxml-stubs', 'lxml-stubs-ext', 
           'lxml-stubs-ext-py311', 'lxml-stubs-ext-py312', 'boto-session-manager', 'boto3-session-manager', 'boto3-session-manager-plugin', 'boto3-session-manager-plugin-py311', 'boto3-session-manager-plugin-py312', 
           'charset-normalizer', 'dbus-next', 'deepsearch-glm', 'deepsearch-llm', 'deepsearch-llm-sdk', 'deepsearch-llm-sdk-py311', 'deepsearch-llm-sdk-py312', 'deepsearch-llm-sdk-py313', 'deepsearch-llm-sdk-py314', 
           'docling-core', 'docling-ibm-models', 'docling-parse', 'fairy-doc', 'fast-langdetect', 'fasttext-wheel', 'flask-babel', 'Flask-Cors', 'Flask-JWT-Extended', 'Flask-SQLAlchemy', 'Flask-WTF', 'flask-marshmallow', 
           'Flask-Migrate', 'Flask-Script', 'Flask-RESTful', 'fonttools', 'func-args', 'func-timeout', 'google-ai-generativelanguage', 'google-api-core', 'google-api-python-client', 'google-auth', 'google-auth-oauthlib', 
           'google-auth-httplib2', 'google-auth-oauthlib-oauth2client', 'google-auth-oauthlib-oauth2client-django', 'google-auth-oauthlib-oauth2client-requests', 'google-auth-oauthlib-oauth2client-requests-oauth2client', 
           'google-auth-oauthlib-oauth2client-requests-oauth2client-django', 'google-auth-oauthlib-oauth2client-requests-oauth2client-django-oauth2client', 'googleapis-common-protos', 'grpcio', 'grpcio-status', 
           'grpcio-tools', 'huggingface-hub', 'jsonschema-specifications', 'lark-parser', 'Levenshtein', 'magic-pdf', 'markdown-it-py', 'markdown-it-py-plugins', 'marshmallow-sqlalchemy', 'mypy-extensions', 'pypdfium2', 
           'pypdfium2-core', 'more-itertools', 'opencv-contrib-python', 'opencv-python', 'opencv-python-headless', 'opt-einsum', 'ordered-set', 'paddleocr', 'paddleocr-core', 'paddlepaddle', 'pdfminer.six', 'proto-plus', 
           'protobuf', 'py-asciimath', 'pycryptodome', 'pyinstaller', 'pyinstaller-hooks-contrib', 'PyJWT', 'PyMuPDF', 'PyMuPDFb', 'pyparsing', 'python-bidi', 'python-dateutil', 'python-docx', 'python-dotenv', 
           'python-pptx', 'pytz', 'pywin32', 'pywin32-ctypes', 'PyYAML', 'rapidfuzz', 'rarfile', 'realtime', 'referencing', 'regex', 'rich', 'robust-downloader', 'rpds-py', 'scikit-image', 'scikit-learn', 
           'scikit-learn-intelex', 'win32-setctime', 'smart-open',
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
            patterns = [
                rf"os\.getenv\(['\"]({var})['\"]",
                rf"os\.environ\[['\"]({var})['\"]",
                rf"os\.environ\.get\(['\"]({var})['\"]"
            ]
            for pattern in patterns:
                if re.search(pattern, content):
                    used_vars.add(var)
        return list(used_vars)

    def _modify_python_file_with_env_vars(self, file_path: Path) -> None:
        """Modify a Python file to include hardcoded environment variables"""
        try:
            env_vars = self._load_env_vars()
            
            with open(file_path, 'r') as f:
                content = f.read()
            
            used_vars = self._find_env_var_usage(content)
            if not used_vars:
                return  # Skip if no environment variables are used
            
            env_init_code = "\n".join([
                f"    os.environ['{var}'] = '{env_vars[var]}'"
                for var in used_vars
            ])
            
            load_env_pattern = r"def load_environment_variables\(\):[^\n]*\n\s+\"\"\"[^\"]*\"\"\"\n\s+"
            if re.search(load_env_pattern, content):
                modified_content = re.sub(
                    load_env_pattern + r"[^\n]+(\n\s+[^\n]+)*",
                    lambda m: m.group(0) + env_init_code + "\n    logging.info('Using hardcoded environment variables')",
                    content
                )
            else:
                # For files without load_environment_variables, add initialization at the start
                import_section_end = re.search(r"^import[^\n]*(\n\s*(?:from|import)[^\n]*)*", content, re.MULTILINE)
                if not import_section_end:
                    raise ValueError(f"Could not find import section in {file_path}")
                
                # For license_manager.py, we'll add the initialization right after imports
                if file_path.name == 'license_manager.py':
                    env_init = "\n# Initialize environment variables\n" + "\n".join([
                        f"os.environ['{var}'] = '{env_vars[var]}'"
                        for var in used_vars
                    ]) + "\n"
                else:
                    env_init = f"\n\ndef load_environment_variables():\n    \"\"\"\n    Load environment variables.\n    \"\"\"\n{env_init_code}\n    logging.info('Using hardcoded environment variables')\n"
                
                pos = import_section_end.end()
                modified_content = content[:pos] + env_init + content[pos:]
            
            # Create a backup
            backup_path = file_path.with_suffix('.py.bak')
            shutil.copy2(file_path, backup_path)
            
            # Log modifications
            log_file = self.config.root_dir / f'modified_{file_path.stem}.log'
            with open(log_file, 'w') as f:
                f.write(f"=== Original Environment Variables Found in {file_path.name} ===\n")
                f.write("Variables used in script:\n")
                f.write("\n".join(used_vars))
                f.write("\n\n=== Generated Environment Initialization Code ===\n")
                f.write(env_init_code)
                f.write("\n\n=== Modified Script Content ===\n")
                f.write(modified_content)
            
            print(f"\nModified script has been logged to: {log_file}")
            print(f"Found and processed {len(used_vars)} environment variables in {file_path.name}")
            
            # Write the modified content
            with open(file_path, 'w') as f:
                f.write(modified_content)
            
        except Exception as e:
            print(f"Error modifying {file_path}: {e}")
            # Restore from backup if it exists
            backup_path = file_path.with_suffix('.py.bak')
            if backup_path.exists():
                shutil.move(backup_path, file_path)
            raise

    def _prepare_build_directory(self):
        """Prepare the build directory for the current version"""
        version_dir = self.config.build_dir / self.current_version["version"]
        version_dir.mkdir(parents=True, exist_ok=True)
        return version_dir

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
                result = subprocess.run(['cl.exe'], capture_output=True, text=True)
                return 'Microsoft (R) C/C++ Optimizing Compiler' in result.stderr
            else:
                subprocess.run([tool, '--version'], capture_output=True, check=True)
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _check_pyinstaller_installation(self) -> bool:
        """Check if PyInstaller is properly installed"""
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'PyInstaller', '--version'],
                capture_output=True,
                text=True,
                check=True
            )
            print(f"Found PyInstaller version: {result.stdout.strip()}")
            return True
        except subprocess.SubprocessError:
            print("Error: PyInstaller is not installed or not working properly")
            return False

    def _parse_package_requirement(self, req: str) -> Tuple[str, Optional[str]]:
        """Parse package requirement into name and version"""
        try:
            if not req or req.isspace():
                return "", None

            if req.startswith(('git+', 'git://', 'http://', 'https://')):
                if '@' in req:
                    url_part = req.split('@')[0]
                else:
                    url_part = req
                pkg_name = url_part.split('/')[-1].replace('.git', '')
                return pkg_name, None
            
            if '==' in req:
                name, ver = req.split('==', 1)
                name = name.split(';')[0].strip()
                ver = f"=={ver.strip()}"
                return name, ver
            elif '>=' in req:
                name, ver = req.split('>=', 1)
                name = name.split(';')[0].strip()
                ver = f">={ver.strip()}"
                return name, ver
            
            return req.split(';')[0].strip(), None
            
        except Exception as e:
            print(f"Warning: Error parsing requirement '{req}': {e}")
            return "", None

    def _check_package_installed(self, pkg_name: str, required_version: Optional[str] = None) -> bool:
        """Check if a package is installed and meets version requirements"""
        try:
            if '@' in pkg_name and any(prefix in pkg_name for prefix in ['git+', 'git://', 'http://', 'https://']):
                if ' @ ' in pkg_name:
                    base_pkg_name = pkg_name.split(' @ ')[0].strip()
                else:
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

            pkg_name = pkg_name.split("==")[0].split(">=")[0].strip()
            
            if pkg_name in self.bypass_import_packages:
                return True
            
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
            
            importlib.import_module(import_name)
            
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
            raw_requirements = []
            encodings = ['utf-16']
            
            for encoding in encodings:
                try:
                    with open('requirements.txt', 'r', encoding=encoding) as f:
                        raw_requirements = f.read().splitlines()
                    print(f"Read requirements.txt with {encoding} encoding")
                    break
                except UnicodeDecodeError:
                    continue
                except Exception as e:
                    print(f"Error reading requirements.txt with {encoding} encoding: {e}")
                    continue
            
            if not raw_requirements:
                print("Error: Could not read requirements.txt with any encoding")
                return False
            
            requirements = []
            for r in raw_requirements:
                line = r.strip()
                if not line or line.startswith('#') or line in ['ÿþ', 'þ', 'ÿ']:
                    continue
                line = line.replace('ÿþ', '').replace('ÿ', '').replace('þ', '')
                cleaned = re.sub(r'^[^\w@.-]+', '', line)
                if cleaned:
                    requirements.append(cleaned)
            
            requirements = [
                req for req in requirements 
                if not (
                    (self.config.is_windows and '; sys_platform == "darwin"' in req) or
                    (self.config.is_macos and '; sys_platform == "win32"' in req)
                )
            ]
            
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
        
        if not self._check_python_version():
            return False
        
        if not self._check_pyinstaller_installation():
            return False
        
        required_tools = self.config.required_tools['all']
        if self.config.is_macos:
            required_tools.extend(self.config.required_tools['darwin'])
        elif self.config.is_windows:
            required_tools.extend(self.config.required_tools['win32'])
        
        for tool in required_tools:
            if not self._check_tool_availability(tool):
                print(f"Error: Required tool '{tool}' is not available")
                return False
        
        if not self._check_dependencies():
            return False
        
        print("Environment validation successful!")
        return True

    def _check_syntax(self, file_path: str) -> bool:
        """Check Python file syntax"""
        encodings = ['utf-8', 'utf-8-sig', 'utf-16', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                    compile(content, file_path, 'exec')
                    return True
            except UnicodeDecodeError:
                continue
            except SyntaxError as e:
                print(f"Syntax error in {file_path}: {e}")
                return False
            except Exception as e:
                if isinstance(e, UnicodeError):
                    continue
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
        
        if not self._check_required_files():
            return False
        
        if not self._check_icon_files():
            return False
        
        python_files = [
            self.config.root_dir / 'clipbrd.py',
            *self.config.root_dir.glob('**/*.py')
        ]
        
        for py_file in python_files:
            if not self._check_syntax(str(py_file)):
                return False
        
        print("Source code validation successful!")
        return True

    def _build_with_pyinstaller(self):
        """Build the application using PyInstaller"""
        try:
            version_dir = self._prepare_build_directory()
            
            # Verify entitlements file for macOS
            if self.config.is_macos:
                if not self.config.entitlements.exists():
                    raise FileNotFoundError(f"Entitlements file not found at {self.config.entitlements}")
                print(f"Found entitlements file: {self.config.entitlements}")
            
            # Only use options that work with spec files
            cmd = [
                sys.executable,
                '-m',
                'PyInstaller',
                'clipbrd.spec',
                '--distpath', str(version_dir),
                '--workpath', str(version_dir / 'build'),
                '--noconfirm',
                '--clean',  # Clean PyInstaller cache
                '--log-level', 'INFO'
            ]

            # Add debug flag if needed
            if os.getenv('DEBUG') or os.getenv('DEV'):
                cmd.extend(['--', '--debug'])
            elif os.getenv('DEV'):
                cmd.extend(['--', '--dev'])

            print(f"Starting {'macOS' if self.config.is_macos else 'Windows'} build...")
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                if self.config.is_macos:
                    app_path = f"{version_dir}/Clipbrd.app"
                    print(f"Build successful! App bundle created at {app_path}")
                    
                    # First, sign with hardened runtime
                    print("Signing app bundle with hardened runtime...")
                    subprocess.run([
                        "codesign",
                        "--force",
                        "--sign", "Developer ID Application",
                        "--deep",
                        "--options", "runtime",
                        app_path
                    ], check=True)
                    
                    # Then, sign with entitlements
                    print("Signing app bundle with entitlements...")
                    subprocess.run([
                        "codesign",
                        "--force",
                        "--sign", "Developer ID Application",
                        "--deep",
                        "--entitlements", str(self.config.entitlements),
                        "--options", "runtime",
                        app_path
                    ], check=True)
                    
                    # Verify signature and entitlements
                    print("Verifying signature and entitlements...")
                    subprocess.run([
                        "codesign",
                        "--verify",
                        "--deep",
                        "--strict",
                        "--verbose=2",
                        app_path
                    ], check=True)
                    
                    subprocess.run([
                        "codesign",
                        "--display",
                        "--entitlements", ":-",
                        app_path
                    ], check=True)
                    
                    self._notarize_macos_app(app_path)
                else:
                    print(f"Build successful! Executable created at {version_dir}/Clipbrd.exe")
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
            print("Creating ZIP archive for notarization...")
            zip_path = f"{app_path}.zip"
            subprocess.run([
                "ditto",
                "-c",
                "-k",
                "--keepParent",
                app_path,
                zip_path
            ], check=True)

            print("Submitting app for notarization...")
            subprocess.run([
                "xcrun",
                "notarytool",
                "submit",
                zip_path,
                "--keychain-profile", "AC_PASSWORD",
                "--wait"
            ], check=True)

            print("Checking notarization status...")
            subprocess.run([
                "xcrun",
                "notarytool",
                "history",
                "--keychain-profile", "AC_PASSWORD"
            ], check=True)

            print("Stapling notarization ticket...")
            subprocess.run([
                "xcrun",
                "stapler",
                "staple",
                app_path
            ], check=True)

            print("Verifying stapled notarization...")
            subprocess.run([
                "stapler",
                "validate",
                app_path
            ], check=True)
            
            # Final verification of all signatures and entitlements
            print("Performing final verification...")
            subprocess.run([
                "spctl",
                "--assess",
                "--verbose=4",
                "--type", "execute",
                app_path
            ], check=True)
            
            print("Notarization complete!")
            
            # Clean up
            os.remove(zip_path)
            
        except subprocess.CalledProcessError as e:
            print(f"Notarization failed: {e}")
            raise

    def build(self):
        """Main build process"""
        try:
            if not self._validate_environment():
                raise Exception("Environment validation failed")
            # if not self._validate_source():
            #     raise Exception("Source code validation failed")

            self._increment_version()

            # Process all Python files that might use environment variables
            for py_file in self.config.python_files:
                file_path = self.config.root_dir / py_file
                if file_path.exists():
                    self._modify_python_file_with_env_vars(file_path)

            self._build_with_pyinstaller()

        finally:
            # Restore all modified files
            for py_file in self.config.python_files:
                file_path = self.config.root_dir / py_file
                backup_path = file_path.with_suffix('.py.bak')
                if backup_path.exists():
                    shutil.move(backup_path, file_path)

def main():
    parser = argparse.ArgumentParser(description='Build Clipbrd application with PyInstaller')
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
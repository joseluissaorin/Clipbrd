# -*- mode: python ; coding: utf-8 -*-

import os
import sys
import argparse
import subprocess
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Ensure cffi and pywin32-ctypes are properly handled
if sys.platform == 'win32':
    import cffi
    import win32ctypes
    cffi_path = os.path.dirname(cffi.__file__)
    win32ctypes_path = os.path.dirname(win32ctypes.__file__)

# Pre-cache emojis
print("Pre-caching common emojis...")
try:
    result = subprocess.run([sys.executable, 'build_emoji_cache.py'], check=True)
    print("Emoji pre-cache completed successfully")
except subprocess.CalledProcessError as e:
    print(f"Warning: Emoji pre-cache failed with exit code {e.returncode}")
except Exception as e:
    print(f"Warning: Failed to run emoji pre-cache: {e}")

# Parse command line arguments after --
parser = argparse.ArgumentParser()
parser.add_argument('--debug', action='store_true', help='Build in debug mode')
parser.add_argument('--dev', action='store_true', help='Build in development mode')
options = parser.parse_args()

# Platform detection
is_windows = sys.platform == 'win32'
is_macos = sys.platform == 'darwin'

# Load version from version.json
version_file = Path('version.json')
if version_file.exists():
    import json
    with open(version_file) as f:
        version_info = json.load(f)
        version = version_info['version']
        version_tuple = tuple(map(int, version.split('.'))) + (0,)
else:
    version = '1.0.0'
    version_tuple = (1, 0, 0, 0)

# Verify entitlements file for macOS
if is_macos:
    entitlements_path = Path('assets/macos/clipbrd.entitlements')
    if not entitlements_path.exists():
        raise FileNotFoundError(f"Entitlements file not found at {entitlements_path}")
    print(f"Found entitlements file: {entitlements_path}")

# Initialize collections
datas = []
binaries = []
hiddenimports = []

# Add assets and configuration files
datas.extend([
    ('assets/icons/*', 'assets/icons'),
    ('cache/emojis', 'cache/emojis'),  # Add emoji cache directory
])
if is_macos:
    datas.append(('assets/macos/clipbrd.entitlements', 'assets/macos'))

# Core dependencies that need special handling
core_packages = [
    'PIL',
    'openai',
    'anthropic',
    'google.generativeai',
    'pilmoji',
    'pystray',
    'numpy',
    'keyring',
    'keyring.backends.Windows',
    'clipman',
    'docling',
    'simplemma',
    'aiofiles',
    'markdown',
    'pynput',
    'pypdfium2',
    'emoji',
    'cffi',
    'win32ctypes',
]

# Core hidden imports
hiddenimports.extend([
    'PIL._tkinter_finder',
    'tkinter',
    'pkg_resources.py2_warn',
    'pkg_resources.markers',
    'docling.pipeline',
    'docling.datamodel',
    'keyring.backends',
    'keyring.backends.Windows',
    'keyring.backends.null',
    'keyring.credentials',
    'keyring.errors',
    'keyring.util',
    'keyring.util.platform_',
    'win32ctypes.core',
    'win32ctypes.pywin32',
    'win32ctypes.core.cffi',
    'win32ctypes.core.cffi._common',
    'win32ctypes.core.cffi._util',
    'win32ctypes.core.cffi._win32cred',
    'win32ctypes.core.cffi._authentication',
    'win32ctypes.core.cffi._system_information',
    'emoji.unicode_codes',
    'emoji.core',
    'cffi._cffi_backend',
    'cffi.api',
    'cffi.backend_ctypes',
    'cffi.commontypes',
    'cffi.cparser',
    'cffi.error',
    'cffi.ffiplatform',
    'cffi.lock',
    'cffi.model',
    'cffi.recompiler',
    'cffi.setuptools_ext',
    'cffi.vengine_cpy',
    'cffi.vengine_gen',
    'cffi.verifier',
    '_cffi_backend',
])

# Platform-specific configurations
if is_macos:
    hiddenimports.extend([
        'pynput.keyboard._darwin',
        'pynput.mouse._darwin'
    ])
elif is_windows:
    hiddenimports.extend([
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'keyring.backends.Windows',
        'win32api',
        'win32con',
        'win32gui',
        'win32ctypes',
        'win32ctypes.core',
        'win32ctypes.pywin32',
    ])
    
    # Add Visual C++ Runtime DLLs for Windows
    import glob
    python_dir = os.path.dirname(sys.executable)
    for pattern in ['vcruntime*.dll', 'msvcp*.dll']:
        for dll in glob.glob(os.path.join(python_dir, pattern)):
            binaries.append((dll, '.'))

    # Add keyring DLLs
    import site
    site_packages = site.getsitepackages()[0]
    keyring_path = os.path.join(site_packages, 'keyring')
    if os.path.exists(keyring_path):
        for root, _, files in os.walk(keyring_path):
            for file in files:
                if file.endswith('.dll'):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(root, keyring_path)
                    binaries.append((full_path, os.path.join('keyring', rel_path)))

# Add pypdfium2 dependencies
venv_path = os.path.join(os.getcwd(), 'venv' if not is_windows else 'windows_venv', 'Lib', 'site-packages')
pypdfium2_files = [
    (os.path.join(venv_path, 'pypdfium2_raw', 'pdfium.dll'), 'pypdfium2_raw'),
    (os.path.join(venv_path, 'pypdfium2_raw', 'version.json'), 'pypdfium2_raw'),
    (os.path.join(venv_path, 'pypdfium2', 'version.json'), 'pypdfium2')
]
for src, dst in pypdfium2_files:
    if os.path.exists(src):
        datas.append((src, dst))
        print(f"Found pypdfium2 file: {src}")
    else:
        print(f"Warning: Required pypdfium2 file not found: {src}")

# Collect package data and modules
for package in core_packages:
    try:
        pkg_datas = collect_data_files(package)
        pkg_imports = collect_submodules(package)
        
        # Filter out unnecessary data files to reduce size
        filtered_datas = [(src, dst) for src, dst in pkg_datas 
                         if not any(exclude in src.lower() 
                                  for exclude in ['test', 'example', 'doc'])]
        
        datas.extend(filtered_datas)
        hiddenimports.extend(pkg_imports)
    except Exception as e:
        print(f"Warning: Error collecting {package}: {e}")

# Add emoji data files explicitly
import site
import os
site_packages = site.getsitepackages()[0]
emoji_data = os.path.join(site_packages, 'emoji', 'unicode_codes', 'emoji.json')
if os.path.exists(emoji_data):
    datas.append((emoji_data, 'emoji/unicode_codes'))
    print(f"Found emoji data file: {emoji_data}")
else:
    print(f"Warning: emoji.json not found at {emoji_data}")

# Create emoji cache directory if it doesn't exist
emoji_cache_dir = os.path.join(os.getcwd(), 'cache', 'emojis')
os.makedirs(emoji_cache_dir, exist_ok=True)

# Create the Analysis object with optimized settings
a = Analysis(
    ['clipbrd.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=list(set(hiddenimports)),  # Remove duplicates
    hookspath=[os.path.abspath('.')],  # Use absolute path
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter.test'],  # Exclude unnecessary modules
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

# Remove duplicates while preserving order
def remove_duplicates(lst):
    seen = set()
    result = []
    for item in lst:
        if item[0] not in seen:
            seen.add(item[0])
            result.append(item)
    return result

# Import binaries from hook-keyring.py if on Windows
if is_windows:
    try:
        import hook_keyring
        if hasattr(hook_keyring, 'binaries'):
            binaries.extend(hook_keyring.binaries)
    except ImportError:
        print("Warning: Could not import hook_keyring module")

a.binaries = remove_duplicates(a.binaries)
a.datas = remove_duplicates(a.datas)

# Create the PYZ archive with optimized compression
pyz = PYZ(a.pure, a.zipped_data)

# Set debug options
debug_mode = options.debug or options.dev
console_enabled = debug_mode

# Create the EXE with optimized settings
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Clipbrd',
    debug=debug_mode,
    bootloader_ignore_signals=False,
    strip=not debug_mode,
    upx=not debug_mode,
    console=debug_mode,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join('assets', 'icons', 'clipbrd_windows.ico') if is_windows else None,
    version='file_version_info.txt' if is_windows else None,
    uac_admin=False,
    icon_resources=[
        (1, os.path.join('assets', 'icons', 'clipbrd_windows.ico'))
    ] if is_windows else [],
)

# Create the collection with optimized settings
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=not debug_mode,
    upx=not debug_mode,
    upx_exclude=[
        'vcruntime*.dll',
        'msvcp*.dll',
        'python*.dll',
        'api-ms-*.dll'
    ],
    name='Clipbrd',
)

# macOS specific bundle configuration
if is_macos:
    app = BUNDLE(
        coll,
        name='Clipbrd.app',
        icon='assets/icons/clipbrd_macos.icns',
        bundle_identifier='com.saorin.clipbrd',
        info_plist={
            'CFBundleShortVersionString': version,
            'CFBundleVersion': version,
            'LSMinimumSystemVersion': '10.12.0',
            'NSHighResolutionCapable': True,
            'NSRequiresAquaSystemAppearance': False,
            'CFBundleDisplayName': 'Clipbrd',
            'CFBundleName': 'Clipbrd',
            'CFBundlePackageType': 'APPL',
            'CFBundleSignature': '????',
            'LSApplicationCategoryType': 'public.app-category.productivity',
            'NSAppleEventsUsageDescription': 'Clipbrd needs access to control other applications to provide clipboard functionality.',
            'NSAppleScriptEnabled': True,
            'NSSystemAdministrationUsageDescription': 'Clipbrd needs administrative access for certain clipboard operations.',
            'com.apple.security.automation.apple-events': True,
            # Additional Info.plist keys for permissions
            'LSUIElement': True,  # Hide from dock
            'NSRequiresAquaSystemAppearance': False,  # Support dark mode
            'NSSupportsAutomaticGraphicsSwitching': True,
        },
        # Code signing settings
        codesign_identity='Developer ID Application',
        entitlements_file=str(entitlements_path),
    ) 
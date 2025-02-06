from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs
import sys

# Collect all submodules
hiddenimports = collect_submodules('keyring')

# Add Windows specific backend and dependencies
hiddenimports.extend([
    'keyring.backends',
    'keyring.backends.Windows',
    'keyring.backends.null',
    'keyring.credentials',
    'keyring.errors',
    'keyring.util',
    'keyring.util.platform_',
    'win32ctypes',
    'win32ctypes.core',
    'win32ctypes.pywin32',
    'win32ctypes.core._authentication',
    'win32ctypes.core._authorization',
    'win32ctypes.core._common',
    'win32ctypes.core._dll',
    'win32ctypes.core._resource',
    'win32ctypes.core._system_information',
])

# Collect data files
datas = collect_data_files('keyring')

# Collect dynamic libraries for Windows
if sys.platform == 'win32':
    binaries = collect_dynamic_libs('win32ctypes')
    binaries.extend(collect_dynamic_libs('keyring'))
else:
    binaries = [] 
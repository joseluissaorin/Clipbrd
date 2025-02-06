from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import os
import cffi

# Collect all submodules
hiddenimports = ['_cffi_backend'] + collect_submodules('cffi')

# Get the cffi backend binary
cffi_path = os.path.dirname(cffi.__file__)
cffi_backend = os.path.join(cffi_path, '_cffi_backend.pyd')

# Add the binary if it exists
binaries = []
if os.path.exists(cffi_backend):
    binaries.append((cffi_backend, '.')) 
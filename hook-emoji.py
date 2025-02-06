from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect all submodules
hiddenimports = collect_submodules('emoji')

# Collect all data files
datas = collect_data_files('emoji', include_py_files=True)

# Make sure we get the unicode_codes data
datas.extend(collect_data_files('emoji.unicode_codes', include_py_files=True)) 
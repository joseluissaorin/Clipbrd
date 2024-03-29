# -*- mode: python ; coding: utf-8 -*-
import sys

block_cipher = None

a = Analysis(['clipbrd.py'],
             pathex=[],
             binaries=[],
             datas=[('.env', '.')],  # Include the .env file
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='clipbrd',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,  # Ensure UPX is installed if this is set to True, or set it to False
          console=False,  # Set to True for a console window, or False for no console  # Adjust according to your platform: '.icns' for MacOS or '.ico' for Windows
          target_arch=None)

if sys.platform == 'darwin':
    app = BUNDLE(exe,
                 name='clipbrd.app',
                 icon='icon.icns',  # Specify your icon file here
                 bundle_identifier='com.saorinstudios.clipbrd',
                 info_plist={
                        'NSPrincipalClass': 'NSApplication',
                        'NSAppleScriptEnabled': False,
                        'NSHighResolutionCapable': 'True'
                    },
                )
elif sys.platform == 'win32':
    exe = EXE(pyz,
              a.scripts,
              a.binaries,
              a.zipfiles,
              a.datas,
              [],
              name='clipbrd',
              debug=False,
              bootloader_ignore_signals=False,
              strip=False,
              upx=True,  # Ensure UPX is installed if this is set to True, or set it to False
              exclude_binaries=False,
              console=False,  # Set to True for a console window, or False for no console
              icon='icon.ico',  # For Windows it is a .ico file
              target_arch=None)
else:
    raise ValueError("Unsupported operating system.")
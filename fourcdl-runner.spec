# -*- mode: python -*-

block_cipher = None


a = Analysis(['fourcdl-runner.py', 'extension_companion\\extension_comm.py'],

             pathex=[
                 'N:\\coding\\4chdl', 'extension_companion\\',
                 # tell pyinstaller where Universal CRT dlls are (needed for >py3.5 on <win10 -> see https://pyinstaller.readthedocs.io/en/v3.3.1/usage.html#windows
                 '..\\UniversalCRTDLLs\\x86', '..\\UniversalCRTDLLs\\x64'],             
             binaries=[],
             datas=[],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='4CDownloader',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='fourcdl')

# -*- mode: python -*-

block_cipher = None

a = Analysis(['run_manga_db.py'],
             pathex=['N:\\coding\\tsu-info', 'manga_db\\extractor',
                     # tell pyinstaller where Universal CRT dlls are (needed for >py3.5 on <win10 -> see https://pyinstaller.readthedocs.io/en/v3.3.1/usage.html#windows
                     '..\\UniversalCRTDLLs\\x86', '..\\UniversalCRTDLLs\\x64'],
             binaries=[],
             # 2-tuple of (path/to/filer-to-include, dir/at/runtime)
             datas=[("manga_db\\extractor\\*.py", "manga_db\\extractor\\"),
             ],
             hiddenimports=[],
             # we need to include extractor files here since they're dynamically imported
             # at runtime -> hook-manga_db.extractor in same dir as spec file -> so "."
             # pyinstaller will call hook if it encounter manga_db.extractor import
             # doesnt seem to work with path since we expect an actual dir and are using
             # os.listdir etc on it -> include as data files
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

# extra data files needed for webGUI
webgui_extras = Tree("manga_db\\webGUI\\", prefix="manga_db\\webGUI\\", excludes=["*.py", "*.pyc"],
                     typecode="DATA")
# add Tree of data to analaysis datas
a.datas += webgui_extras

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='MangaDB',
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
               name='manga_db')

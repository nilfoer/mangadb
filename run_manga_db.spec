# -*- mode: python -*-

block_cipher = None

a = Analysis(['run_manga_db.py'],
             pathex=['.', 'manga_db\\extractor',
                     # tell pyinstaller where Universal CRT dlls are (needed for >py3.5 on <win10 -> see https://pyinstaller.readthedocs.io/en/v3.3.1/usage.html#windows
                     '..\\UniversalCRTDLLs\\x86', '..\\UniversalCRTDLLs\\x64'],
             binaries=[],
             # 2-tuple of (path/to/filer-to-include, dir/at/runtime)
             datas=[("manga_db\\extractor\\*.py", "manga_db\\extractor\\"),
                    ("manga_db/webGUI/static", "manga_db/webGUI/static"),
                    ("manga_db/webGUI/templates", "manga_db/webGUI/templates"),
                    ],
             # since we inlcude extractors only as data files and import the dynamically
             # we need to manually identify their imports and add them here
             # A list of module names (relative or absolute) that should be part of the bundled app.
             hiddenimports=['bs4'],
             # we need to include extractor files here since they're dynamically imported
             # at runtime -> hook-manga_db.extractor in same dir as spec file -> so ["."]
             # pyinstaller will call hook if it encounter manga_db.extractor import
             # NOTE
             # does NOT work with since we expect an actual dir and are using
             # os.listdir etc on it while the found python imports are stored in the
             # exe as a compressed archive -> include as data files which also enables
             # users to create extractor files that can get loaded (but they cannot use
             # other third-party imports; stdlib is fine [assumption!])
             #
             # could use collect_data_files( package, include_py_files=True )
             # to discover all extractor files in a hook
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
          # exe name
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
               # folder name
               name='manga_db')

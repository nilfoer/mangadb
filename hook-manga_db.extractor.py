from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# collect_submodels returns list of strings of all submodules contained in manga_db.extractor
hiddenimports = collect_submodules('manga_db.extractor')

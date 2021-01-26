import sys
import os
import subprocess
import zipfile
import tarfile

from multiprocessing import Process

MODULE_DIR = os.path.dirname(os.path.realpath(__file__))
# normpath to remove pardir/..
PROJECT_ROOT = os.path.normpath(os.path.join(MODULE_DIR, os.pardir))

sys.path.append(PROJECT_ROOT)
from manga_db import VERSION


def bundle_standalone_dir(standalone_dir, linux=False):
    out_zip_file = os.path.join(
            PROJECT_ROOT, 'dist',
            f"manga_db_v{VERSION}_standalone_{'lin' if linux else 'win'}-x64"
            f".{'tar.gz' if linux else 'zip'}")

    if os.path.isfile(out_zip_file):
        print("Removing:", out_zip_file)
        os.remove(out_zip_file)

    if not linux:
        with zipfile.ZipFile(out_zip_file, 'x', compression=zipfile.ZIP_DEFLATED) as myzip:
            for dir_path, dirs, files in os.walk(standalone_dir):
                # will have same relative path as fn in archive
                # normalize so we don't have weird '..' in the path
                for fn in files:
                    fpath = os.path.join(dir_path, fn)
                    # need to use relpath since dir_path includes standalone_dir
                    # relpath as name in archive
                    myzip.write(
                            fpath,
                            os.path.normpath(os.path.relpath(fpath, start=standalone_dir)))
                    # print("Added:", os.path.normpath(os.path.relpath(fpath, start=standalone_dir)))
    else:
        with tarfile.open(out_zip_file, 'x:gz') as mytar:
            # tarfile.add works for files and dirs
            # dirs are added recursively by default
            files = os.listdir(standalone_dir)
            for fn in files:
                # fn is relative to standalone_dir
                mytar.add(os.path.join(standalone_dir, fn), fn)

    print("Bundled", standalone_dir, "into", out_zip_file)


# NOTE: for use with multiprocessing objects have to be pickelable
# which Popen apparently isn't - pass just the args to the worker instead
src_zip_fn = os.path.join(PROJECT_ROOT, 'dist', f"manga_db_v{VERSION}.zip")
build_zip_src_dist_args = ['python', os.path.join(MODULE_DIR, 'build_zip_dist.py'), PROJECT_ROOT,
                           src_zip_fn, '--noconfirm']
# build_zip_src_dist = subprocess.Popen(
#         ['python', 'build_dir_dist.py', PROJECT_ROOT, src_zip_fn],
#         stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# will overwrite dist/manga_db !!!
build_win_exe_args = ['pyinstaller', 'run_manga_db.spec', '--noconfirm']
# build_win_exe = subprocess.Popen(
#         ['pyinstaller', 'run_manga_db.spec', '--noconfirm'],
#         stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def worker(subproc_args):
    proc = subprocess.Popen(subproc_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    print('** WORKER DONE **')
    print('** RET:', proc.returncode, '      **')
    if stderr:
        print('** ERRORS **')
        print(stderr.decode('utf-8'))
        print('************')
    print(stdout.decode('utf-8'))

# On Windows the subprocesses will import (i.e. execute) the main module at
# start. You need to insert an if __name__ == '__main__': guard in the main
# module to avoid creating subprocesses recursively. 

if __name__ == '__main__':
    if sys.platform.startswith('linux'):
        build_lin_exe = subprocess.Popen(
                ['pyinstaller', 'run_manga_db_linux.spec', '--noconfirm'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = build_lin_exe.communicate()
        if err:
            print("ERRORS:", err.decode('utf-8'))
        print(out.decode('utf-8'))

        bundle_standalone_dir(os.path.join(PROJECT_ROOT, 'dist', 'manga_db_linux'), linux=True)
    else:

        p_src = Process(target=worker, args=(build_zip_src_dist_args,))
        p_exe = Process(target=worker, args=(build_win_exe_args,))

        p_src.start()
        p_exe.start()
        p_src.join()
        p_exe.join()

        bundle_standalone_dir(os.path.join(PROJECT_ROOT, 'dist', 'manga_db'))

    print("\n========== MADE VERSION", VERSION, "==========")

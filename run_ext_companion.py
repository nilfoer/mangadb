#!python3 -u
# we could either just run extenion_comm directly and add the parent dir to sys.path
# (so python import can find fourchandl package) or we just use this script runner
# that is alrdy at the parent dir which means fourchandl package is alrdy in py path
from extension_companion.extension_comm import main

if __name__ == "__main__":
    main()

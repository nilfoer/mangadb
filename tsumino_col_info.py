import sys
import os
import json
import re

import pyperclip

def export_obj_to_json(obj, filename):
    json_exp_str = json.dumps(obj, indent=4, sort_keys=True)
    with open(filename, "w", encoding="UTF-8") as w:
        w.write(json_exp_str)


def import_obj_from_json(filename):
    with open(filename, "r", encoding="UTF-8") as f:
        json_str = f.read()

    # json serializes ints that are dict keys as strings (cause thats how it is in js)
    # 1) just us str(fsize) as lookup or convert them to int
    # 2) converting dictionary to a list of [(k1,v1),(k2,v2)] format while encoding it using json, and converting it back to dictionary after decoding it back
    # 3) add option for dict to decoder func:
    # if isinstance(x, dict):
    #         return {int(k):v for k,v in x.items()}
    # 4) use pickle -> better/faster for only python anyways but unsecure, which doesnt matter here since only b64_md5s and int/float sizes will be stored or use YAML
    files_info = json.loads(json_str)
    return files_info


# always two spaces between eng and asian title when using tsu zip
# tsu_eng_zip_re = re.compile(r"^\[.+\]\s{1,2}(.+)  ")
# eng_dir_re = re.compile(r"^\[.+\] (.+)")
file_line_re = re.compile(r"(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\s+([0-9\.]+)\s+([^\n\r:<>|?*\\\/\"]+)\.(\w+)")
fn_number_re = re.compile(r".*?_?(\d+)$")
brackets_re = re.compile(r"^\[.+\]")
remove_tsu_asn_re = re.compile(r"  .+$")
def create_info_from_dirlist(fn):
    with open(fn, "r", encoding="UTF-8") as f:
        inp = f.read()

    tsu_col_info = {}

    base_path = None
    cur_dir_dict = {}
    imgs = 0
    for ln in inp.splitlines():
        if "<DIR>" in ln:
            continue
        elif "Verzeichnis von " in ln:
            rel_path, cur_dir = ln.split(":\\", 1)[-1].rsplit("\\", 1)
            if base_path is None:
                base_path = ln.strip().split(":\\", 1)[-1]
            else:
                cur_dir_dict["rel_path"] = rel_path.replace(base_path, "")
            cur_dir_dict["dirname"] = cur_dir
        elif "Datei(en)," in ln:
            nr_files, dirsize_str = ln.split("Datei(en),")
            cur_dir_dict["nr_files"] = int(nr_files.strip())
            cur_dir_dict["dirsize"] = int(dirsize_str.strip().split(" ", 1)[0].replace(".", ""))
            cur_dir_dict["img_files_nr"] = imgs
            imgs = 0

            # ^^ dict summary -> add finished dict folder to tsu_col_info
            dirname = cur_dir_dict["dirname"]
            # writing regex(s) to get english title so i get exact match when trying to access
            # info with title_eng from tsu_info_getter doesnt really work, since there are too
            # many combinations of title patterns
            # try anyway -> but later try searching keys for partial match if KeyError

            title_eng = None
            if "TSUMINO.COM" in dirname:
                title_eng = re.sub(remove_tsu_asn_re, "", dirname)
            # remove brackets and content
            title_eng = re.sub(brackets_re, "", title_eng if title_eng else dirname).strip()

            tsu_col_info[title_eng] = cur_dir_dict
            # reset cur_dir_dict
            cur_dir_dict = {}
        elif "Anzahl der angezeigten Dateien:" in ln:
            # end reached
            assert(not cur_dir_dict)
            break
        else:
            file_grps = re.match(file_line_re, ln)
            if not file_grps:
                continue
            date, clock, size, fname, ext = file_grps.groups()
            size = int(size.replace(".", ""))
            if ext in ("jpg", "png", "gif"):
                try:
                    pg_nr = int(re.search(fn_number_re, fname).group(1))
                except AttributeError:
                    # no match
                    continue
                cur_dir_dict["image_datetime"] = f"{date} {clock}"
                cur_dir_dict["max_pg_nr"] = max(pg_nr, cur_dir_dict.get("max_pg_nr", 0))
                imgs += 1
            elif fname == "tags":
                cur_dir_dict["info_txt"] = f"{date}: tags.txt"
            elif fname.endswith("_info"):
                cur_dir_dict["info_txt"] = f"{date}: _info.txt"

    return tsu_col_info


def build_dict_str(d):
    lns = []
    for k, v in d.items():
        pad_k = len(k)+5
        lns.append(f"{k:>{pad_k}}: {v}")
    return "\n".join(lns)


def get_info_by_title(title, tsu_col_info):
    lns = []
    try:
        folder_dic = tsu_col_info[title]
        # convert to MB
        folder_dic["dirsize"] = round(folder_dic["dirsize"]/1024**2, 2)
        lns.append(title)
        lns.append(build_dict_str(folder_dic))
    except KeyError:
        matching_keys = [k for k in tsu_col_info.keys() if title in k]
        for k in matching_keys:
            folder_dic = tsu_col_info[k]
            # convert to MB
            folder_dic["dirsize"] = round(folder_dic["dirsize"]/1024**2, 2)
            lns.append(title)
            lns.append(build_dict_str(folder_dic))

    return "\n".join(lns)



if __name__ == "__main__":
    # d = create_info_from_dirlist(os.path.join("N", os.sep, "!HDDCol", "tsumino-dir-2018-03-13.txt"))
    # export_obj_to_json(d, "tsumino_dir_info.json")
    d = import_obj_from_json("tsumino_dir_info.json")


    if sys.argv[1] == "watch":
        try:
            recent_value = ""
            while True:
                tmp_value = pyperclip.paste()
                if tmp_value != recent_value:
                    recent_value = tmp_value
                    inf_str = get_info_by_title(recent_value, d)
                    if inf_str:
                        print(inf_str)
                    else:
                        print("Not found!")
        except KeyboardInterrupt:
            pass
    else:
        inf_str = get_info_by_title(sys.argv[1], d)
        if inf_str:
            print(inf_str)
        else:
            print("Not found!")



    # import manga_db as mb
    # conn, c = mb.load_or_create_sql_db("manga_db.sqlite")
    # c.execute("SELECT title_eng FROM TSUMINO")
    # for title_eng in c.fetchall():
    #     get_info_by_title(title_eng[0], d)
    




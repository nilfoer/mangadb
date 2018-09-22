
def cli_yes_no(question_str):
    ans = input(f"{question_str} y/n:\n")
    while True:
        if ans == "n":
            return False
        elif ans == "y":
            return True
        else:
            ans = input(f"\"{ans}\" was not a valid answer, type in \"y\" or \"n\":\n")

# TODO(m): let users create lists and query them dynamically
LISTS = [
    "li_to-read", "li_downloaded", "li_prob-good", "li_femdom", "li_good",
    "li_good futa", "li_monster", "li_straight shota", "li_trap", "li_vanilla",
    "li_best"
]
# create list with lines where one line contains 3 elements from list with corresponding
# indexes as string
# use two fstrings to first format index and value and then pad the resulting string to
# the same length
# is there a way just using one f string? -> no not without using variables, which doesnt work
# here (at least i dont think so)
DESCR = [
    " ".join([
        f"{f'[{i+n}] {LISTS[i+n]}':20}"
        for n in range(3 if (len(LISTS) - i) >= 3 else len(LISTS) - i)
    ]) for i in range(0, len(LISTS), 3)
]


# or pad index and value independently?
# DESCR = [" ".join([f"[{i+n:>2}] {LISTS[I+N]:15}" for n in range(3 if (len(LISTS)-I) >= 3 else len(LISTS)-I)]) for i in range(0, len(LISTS), 3)]
def enter_manga_lists(i):
    # only print available LISTS every fifth time
    if i % 5 == 0:
        print("\n".join(DESCR))

    while True:
        result = []
        inp = input(
            "Enter indexes (displayed in [i]) of lists the manga should be in seperated "
            "by commas:\n"
        )
        if inp:
            for ind in inp.split(","):
                try:
                    lname = LISTS[int(ind)]
                    result.append(lname)
                # (Error1, Erro2) is needed to except multiple exceptions in one except statement
                except (ValueError, IndexError):
                    logger.error(
                        "\"%s\" was not a valid list index, please re-enter list indexes",
                        ind)
                    break
            # keep looping (while) till all list names are recognized -> for doesnt break -> return
            else:
                logger.info("The following lists were selected %s", result)
                return result
        else:
            logger.info("No lists were selected!")
            # no input -> dont add to any lists
            return None

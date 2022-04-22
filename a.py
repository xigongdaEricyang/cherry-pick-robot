import re

if __name__ == "__main__":
    label_name = "v13.12-cherry-pick"
    version_label_re = re.compile(r"^v[0-9]*\.[0-9]*")
    baseBranch = version_label_re.match(label_name).group(0)
    print(baseBranch)

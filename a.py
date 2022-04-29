import re

def add(*args):
    return sum(args)

if __name__ == "__main__":
    version_label_re = re.compile(r"^v[0-9]*\.[0-9]*(.[0-9])?")
    label = "v3.0.0-cherry-pick"
    print(version_label_re.match(label).group(0)[1:])
    # print(len(list(filter(lambda x: x == '10', arr))))


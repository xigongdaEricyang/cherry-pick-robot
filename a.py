import functools
import re


# def sort_cmp(number1, number2):
#     if number1 not in pr_sorted_list: 
#       return 1
#     if number2 not in pr_sorted_list:
#       return -1
#     pr1_index = pr_sorted_list.index(number1)
#     pr2_index = pr_sorted_list.index(number2)
#     if pr1_index < pr2_index:
#         return -1
#     if pr1_index > pr2_index:
#         return 1
#     return 0 

def getFullVersion(label):
  if label.startswith('cherry-pick-'):
    return label[len('cherry-pick-'):][1:]
  if label.endswith('-cherry-pick'):
    return label[:-len('-cherry-pick')][1:]

if __name__ == "__main__":
    # label_regex = '^cherry-pick-v[0-9]*\.[0-9]*(.[0-9])?$'
    # label_regex = '^v[0-9]*\.[0-9]*(.[0-9])?-cherry-pick$'
    # version_label_re = re.compile(r"v[0-9]*\.[0-9]*(.[0-9])?")
    # # label_regex = 'cherry-pick-v3.1'
    # label = 'cherry-pick-v3.1-hwpoc'
    # label1 = 'v3.1-cherry-pick'
    # print(getFullVersion(label))
    
    # version_label_re = re.compile(r"^v[0-9]*\.[0-9]*(.[0-9])?")
    # version_label = "v2.2.0"  
    # print(version_label_re.match(version_label))
    
    # pr_sorted_list = [13, 1, 5, 7, 4, 19]
    # pr_list = [1, 5, 7, 13, 19, 8]
    # print(sorted(pr_list, key=functools.cmp_to_key(sort_cmp)))
    # print(len(list(filter(lambda x: x == '10', arr))))

    a = [1,2,3]
    a.append(4)
    print(a)
    # print(">>> pr total: {}".format([(pr.number, commit_ci.commit.title) for (pr, commit_ci) in a.reverse()]))

